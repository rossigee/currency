# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import uuid
import base64
from .macaroon_utils import MacaroonUtils, MacaroonValidationError
from .lnd_rest_client import LndRestClient


class CryptoLightningServiceProvider(models.Model):
    _name = 'crypto.lightning.service.provider'
    _description = 'Lightning Service Provider'
    _sql_constraints = [
        ('token_uuid_unique', 'unique(token_uuid)', 'Token UUID must be unique')
    ]

    name = fields.Char(string='Name', required=True)
    rest_url = fields.Char(string='REST URL')
    macaroon = fields.Char(string='Macaroon', compute='_compute_vault_values',
                          inverse='_inverse_vault_values', store=False, readonly=False)
    pubkey = fields.Char(string='Public key')
    clearnet_url = fields.Char(string='Clearnet URL')
    tor_url = fields.Char(string='TOR URL')
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')
    mail_channel_id = fields.Many2one('mail.channel', string='Notification Channel',
                                     help='Mail channel for payment notifications')
    token_uuid = fields.Char(string='Token UUID', required=True, default=lambda self: str(uuid.uuid4()),
                            copy=False, index=True)
    vault_status = fields.Char(string='Vault Status', compute='_compute_vault_values', store=False)
    macaroon_info = fields.Text(string='Macaroon Info', compute='_compute_macaroon_info', store=False)
    macaroon_format = fields.Char(string='Format', compute='_compute_macaroon_info', store=False)
    macaroon_location = fields.Char(string='Location', compute='_compute_macaroon_info', store=False)
    macaroon_identifier = fields.Char(string='Identifier', compute='_compute_macaroon_info', store=False)
    macaroon_caveat_count = fields.Integer(string='Permission Count', compute='_compute_macaroon_info', store=False)
    macaroon_permissions = fields.Text(string='Permissions', compute='_compute_macaroon_info', store=False)
    macaroon_permission_lines = fields.Text(
        string='Macaroon Permissions',
        compute='_compute_macaroon_info',
        store=False
    )

    # LND Status fields
    lnd_status_last_updated = fields.Datetime(string='Last Updated', readonly=True)
    lnd_node_alias = fields.Char(string='Node Alias', readonly=True)
    lnd_node_version = fields.Char(string='LND Version', readonly=True)
    lnd_block_height = fields.Integer(string='Block Height', readonly=True)
    lnd_synced_to_chain = fields.Boolean(string='Synced to Chain', readonly=True)
    lnd_num_active_channels = fields.Integer(string='Active Channels', readonly=True)
    lnd_num_pending_channels = fields.Integer(string='Pending Channels', readonly=True)
    lnd_total_balance_sat = fields.Integer(string='Total Balance (sats)', readonly=True)
    lnd_confirmed_balance_sat = fields.Integer(string='Confirmed Balance (sats)', readonly=True)
    lnd_unconfirmed_balance_sat = fields.Integer(string='Unconfirmed Balance (sats)', readonly=True)
    lnd_channel_balance_sat = fields.Integer(string='Channel Balance (sats)', readonly=True)
    lnd_num_peers = fields.Integer(string='Connected Peers', readonly=True)
    lnd_status_error = fields.Text(string='Status Error', readonly=True)

    def _inverse_vault_values(self):
        """Store macaroon data in vault with validation"""
        for record in self:
            if record.token_uuid and record.macaroon:
                record._validate_macaroon(record.macaroon)
                vault_data = {'macaroon': record.macaroon}
                self.env['vault.connector'].set_secret(record.token_uuid, vault_data)

    @api.depends('token_uuid')
    def _compute_vault_values(self):
        """Retrieve macaroon data from vault"""
        for record in self:
            if record.token_uuid:
                vault_result = self._get_data_from_vault(record.token_uuid)
                record.macaroon = vault_result.get('macaroon', '')
                record.vault_status = vault_result.get('status', '❌ Unknown error')
            else:
                record.macaroon = ''
                record.vault_status = '⚪ No token UUID'

    def _get_data_from_vault(self, token_uuid):
        """
        Centralized method to get data from vault
        Returns: {'macaroon': str, 'status': str}
        """
        try:
            vault_connector = self.env['vault.connector']
            vault_data = vault_connector.get_secret(token_uuid)

            if vault_data:
                has_macaroon = bool(vault_data.get('macaroon'))

                if has_macaroon:
                    return {
                        'macaroon': vault_data.get('macaroon', ''),
                        'status': '✅ Connected - Macaroon available'
                    }
                else:
                    return {
                        'macaroon': '',
                        'status': '⚠️ No macaroon data in vault'
                    }
            else:
                return {
                    'macaroon': '',
                    'status': '⚠️ Secret not found in vault'
                }

        except Exception as e:
            error_msg = str(e)
            # Categorize errors for user-friendly display
            if 'sealed' in error_msg.lower():
                status = '🔒 Vault is sealed - unseal required'
            elif 'not accessible' in error_msg or 'environment variables' in error_msg:
                status = '❌ Vault not configured'
            elif 'not found' in error_msg:
                status = '⚠️ Secret not found in vault'
            elif 'access denied' in error_msg or 'token' in error_msg:
                status = '❌ Vault access denied'
            else:
                status = f'❌ Vault error: {error_msg}'

            return {
                'macaroon': '',
                'status': status
            }

    @api.model
    def create(self, vals):
        """Enhanced create method with vault storage"""
        record = super(CryptoLightningServiceProvider, self).create(vals)
        record._inverse_vault_values()
        return record

    def _validate_macaroon(self, macaroon_str):
        """Validate macaroon format and structure"""
        try:
            MacaroonUtils.validate_macaroon(macaroon_str)
        except MacaroonValidationError as e:
            raise ValidationError(str(e))

    def _parse_macaroon(self, macaroon_str):
        """Parse macaroon and extract information"""
        return MacaroonUtils.parse_macaroon(macaroon_str)

    @api.depends('token_uuid')
    def _compute_macaroon_info(self):
        """Compute macaroon information for display"""
        for record in self:
            # Force computation of macaroon field first
            record._compute_vault_values()

            if record.macaroon:
                parsed_info = MacaroonUtils.parse_macaroon(record.macaroon)

                record.macaroon_format = parsed_info.get('format', '').upper()
                record.macaroon_location = parsed_info.get('location', '')
                record.macaroon_identifier = parsed_info.get('identifier', '')
                record.macaroon_caveat_count = parsed_info.get('caveat_count', 0)

                # Format permissions as readable text
                caveats = parsed_info.get('caveats', [])
                if caveats:
                    record.macaroon_permissions = '\n'.join([f"• {caveat}" for caveat in caveats])

                    # Create HTML table for permission lines
                    html_lines = ['<table class="table table-sm">']
                    html_lines.append('<thead><tr><th>Service</th><th>Permission</th><th>Description</th></tr></thead>')
                    html_lines.append('<tbody>')

                    for caveat in caveats:
                        if ':' in caveat:
                            service, permission_part = caveat.split(':', 1)
                            service = service.strip()
                            permission_part = permission_part.strip()

                            # Handle multiple permissions
                            perm_list = [p.strip() for p in permission_part.split(',')]
                            for perm in perm_list:
                                html_lines.append(f'<tr><td>{service}</td><td>{perm}</td><td>{service} {perm} access</td></tr>')
                        else:
                            html_lines.append(f'<tr><td>general</td><td>{caveat.strip()}</td><td>General permission</td></tr>')

                    html_lines.append('</tbody></table>')
                    record.macaroon_permission_lines = ''.join(html_lines)
                else:
                    record.macaroon_permissions = "No permissions detected"
                    record.macaroon_permission_lines = "<p>No permissions detected</p>"

                # Keep the formatted text version for backward compatibility
                record.macaroon_info = MacaroonUtils.format_macaroon_info(record.macaroon)
            else:
                record.macaroon_format = ''
                record.macaroon_location = ''
                record.macaroon_identifier = ''
                record.macaroon_caveat_count = 0
                record.macaroon_permissions = ''
                record.macaroon_permission_lines = ''
                record.macaroon_info = "No macaroon available"


    def action_refresh_vault_status(self):
        """Manually refresh vault status and data"""
        self.ensure_one()
        self._compute_vault_values()
        self._compute_macaroon_info()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_get_lnd_status(self):
        """Fetch current status from LND node"""
        self.ensure_one()

        if not self.rest_url:
            raise ValidationError("REST URL is required to connect to LND node")

        if not self.macaroon:
            # Force macaroon computation
            self._compute_vault_values()
            if not self.macaroon:
                raise ValidationError("No macaroon available. Please ensure macaroon is stored in vault.")

        try:
            # Decode macaroon to hex format
            if len(self.macaroon) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in self.macaroon):
                # Already hex format
                macaroon_hex = self.macaroon
            else:
                # Base64 format, convert to hex
                macaroon_bytes = base64.b64decode(self.macaroon)
                macaroon_hex = macaroon_bytes.hex()

            # Create LND client
            client = LndRestClient(self.rest_url, macaroon_hex)
            client.connect()

            # Fetch data from LND
            self._fetch_lnd_status(client)

        except Exception as e:
            self.lnd_status_error = f"Error connecting to LND: {str(e)}"
            self.lnd_status_last_updated = fields.Datetime.now()

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def _fetch_lnd_status(self, client: LndRestClient):
        """Fetch actual status from LND node"""
        try:
            # Clear any previous errors
            self.lnd_status_error = False

            # Get basic node info
            info = client.get_info()
            self.lnd_node_alias = info.get('alias', self.name or 'Unknown')
            self.lnd_node_version = info.get('version', 'Unknown')
            self.lnd_block_height = int(info.get('block_height', 0))
            self.lnd_synced_to_chain = info.get('synced_to_chain', False)

            # Get wallet balance
            wallet_balance = client.get_wallet_balance()
            self.lnd_total_balance_sat = int(wallet_balance.get('total_balance', 0))
            self.lnd_confirmed_balance_sat = int(wallet_balance.get('confirmed_balance', 0))
            self.lnd_unconfirmed_balance_sat = int(wallet_balance.get('unconfirmed_balance', 0))

            # Get channel balance
            channel_balance = client.get_channel_balance()
            self.lnd_channel_balance_sat = int(channel_balance.get('balance', 0))

            # Get channels info
            channels = client.list_channels()
            channels_list = channels.get('channels', [])
            self.lnd_num_active_channels = len([c for c in channels_list if c.get('active', False)])
            self.lnd_num_pending_channels = len([c for c in channels_list if not c.get('active', True)])

            # Get peers info
            peers = client.list_peers()
            self.lnd_num_peers = len(peers.get('peers', []))

            # Update timestamp
            self.lnd_status_last_updated = fields.Datetime.now()

        except Exception as e:
            raise Exception(f"Failed to fetch LND status: {str(e)}")
        finally:
            client.close()

    def debug_permissions(self):
        """Debug method to check permissions"""
        self.ensure_one()
        self._compute_vault_values()
        _logger.debug(f"Macaroon exists: {bool(self.macaroon)}")
        if self.macaroon:
            parsed_info = MacaroonUtils.parse_macaroon(self.macaroon)
            caveats = parsed_info.get('caveats', [])
            _logger.debug(f"Found {len(caveats)} caveats: {caveats}")
        return True