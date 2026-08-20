# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import uuid
import base64
import json
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
    mail_channel_id = fields.Many2one('discuss.channel', string='Notification Channel',
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

    # Transaction-related fields (computed)
    transaction_data = fields.Text(string='Transaction Data', compute='_compute_transaction_data', store=False)
    transaction_html = fields.Html(string='Transaction Table', compute='_compute_transaction_html', store=False)
    last_transaction_fetch = fields.Datetime(string='Last Fetch', readonly=True)

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

    @api.depends('rest_url')
    def _compute_transaction_data(self):
        """Compute transaction data by fetching from LND service"""
        for record in self:
            if record.rest_url and record.macaroon:
                try:
                    transactions = record._fetch_transactions_from_lnd()
                    record.transaction_data = json.dumps(transactions, indent=2)
                except Exception as e:
                    record.transaction_data = f"Error fetching transactions: {str(e)}"
            else:
                record.transaction_data = "No REST URL or macaroon configured"

    @api.depends('rest_url')
    def _compute_transaction_html(self):
        """Compute transaction data as formatted HTML table"""
        for record in self:
            if not record.rest_url or not record.macaroon:
                record.transaction_html = "<p class='text-muted'>No REST URL or macaroon configured</p>"
                continue
                
            try:
                transactions = record._fetch_transactions_from_lnd()
                record.transaction_html = record._format_transactions_as_html(transactions)
            except Exception as e:
                record.transaction_html = f"<div class='alert alert-danger'>Error fetching transactions: {str(e)}</div>"

    def _fetch_transactions_from_lnd(self):
        """Fetch all transactions from this LND node"""
        if not self.rest_url:
            raise ValidationError("No REST URL configured for this service provider")

        # Get macaroon from vault if not already loaded
        if not self.macaroon:
            self._compute_vault_values()
            
        vault_data = self._get_data_from_vault(self.token_uuid)
        macaroon = vault_data.get('macaroon')
        if not macaroon:
            raise ValidationError("No macaroon available for service provider")

        # Convert macaroon to hex if needed
        if len(macaroon) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in macaroon):
            macaroon_hex = macaroon
        else:
            import base64
            macaroon_bytes = base64.b64decode(macaroon)
            macaroon_hex = macaroon_bytes.hex()

        # Create LND client and fetch data
        client = LndRestClient(self.rest_url, macaroon_hex)
        client.connect()

        try:
            # Fetch invoices and payments
            invoices_data = client.list_invoices(100)
            payments_data = client.list_payments(100)

            # Process all transactions
            transactions = self._process_all_transactions(invoices_data, payments_data)

            return transactions
        finally:
            client.close()

    def _process_all_transactions(self, invoices_data, payments_data):
        """Process all transactions from LND node"""
        transactions = []

        # Process invoices (incoming payments)
        for invoice in invoices_data.get('invoices', []):
            transactions.append({
                'type': 'invoice',
                'payment_hash': invoice.get('r_hash'),
                'amount_sat': invoice.get('value'),
                'settled': invoice.get('settled', False),
                'creation_date': invoice.get('creation_date'),
                'settle_date': invoice.get('settle_date'),
                'memo': invoice.get('memo', ''),
                'payment_request': invoice.get('payment_request', '')
            })

        # Process payments (outgoing payments)
        for payment in payments_data.get('payments', []):
            transactions.append({
                'type': 'payment',
                'payment_hash': payment.get('payment_hash'),
                'amount_sat': payment.get('value_sat'),
                'status': payment.get('status'),
                'creation_time': payment.get('creation_time_ns'),
                'fee_sat': payment.get('fee_sat'),
                'payment_request': payment.get('payment_request', '')
            })

        # Sort by date (most recent first)
        transactions.sort(key=lambda x: x.get('creation_date') or x.get('creation_time', 0), reverse=True)

        return transactions[:100]  # Return latest 100 transactions

    def _format_transactions_as_html(self, transactions):
        """Format transactions list as HTML table"""
        if not transactions:
            return "<p class='text-muted'>No transactions found</p>"
        
        html = """
        <div class="table-responsive">
            <table class="table table-striped table-sm">
                <thead class="table-dark">
                    <tr>
                        <th>Type</th>
                        <th>Date</th>
                        <th>Amount (sats)</th>
                        <th>Status</th>
                        <th>Fee (sats)</th>
                        <th>Memo/Hash</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        for tx in transactions:
            tx_type = tx.get('type', '').title()
            
            # Format date
            if tx.get('creation_date'):
                import datetime
                date_str = datetime.datetime.fromtimestamp(int(tx['creation_date'])).strftime('%Y-%m-%d %H:%M')
            elif tx.get('settle_date'):
                import datetime
                date_str = datetime.datetime.fromtimestamp(int(tx['settle_date'])).strftime('%Y-%m-%d %H:%M')
            elif tx.get('creation_time'):
                import datetime
                # Convert nanoseconds to seconds
                timestamp = int(tx['creation_time']) / 1000000000
                date_str = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')
            else:
                date_str = 'Unknown'
            
            # Format amount
            amount = tx.get('amount_sat', tx.get('value', 0))
            try:
                amount_int = int(amount) if amount else 0
                amount_str = f"{amount_int:,}"
            except (ValueError, TypeError):
                amount_str = str(amount) if amount else "0"
            
            # Format status/settled
            if tx_type == 'Invoice':
                status = "✅ Settled" if tx.get('settled') else "⏳ Pending"
                status_class = "text-success" if tx.get('settled') else "text-warning"
            else:
                status = tx.get('status', 'Unknown').replace('_', ' ').title()
                status_class = "text-success" if status == 'Succeeded' else "text-warning"
            
            # Format fee
            fee = tx.get('fee_sat', 0)
            try:
                fee_int = int(fee) if fee else 0
                fee_str = f"{fee_int:,}" if fee_int > 0 else "-"
            except (ValueError, TypeError):
                fee_str = str(fee) if fee else "-"
            
            # Format memo/hash
            memo = tx.get('memo', '')
            payment_hash = tx.get('payment_hash', '')
            if memo:
                memo_display = memo[:30] + "..." if len(memo) > 30 else memo
            elif payment_hash:
                memo_display = payment_hash[:12] + "..."
            else:
                memo_display = "-"
            
            # Add row color based on type
            row_class = "table-success" if tx_type == 'Invoice' else "table-info"
            
            html += f"""
                    <tr class="{row_class}">
                        <td><span class="badge badge-{'success' if tx_type == 'Invoice' else 'primary'}">{tx_type}</span></td>
                        <td>{date_str}</td>
                        <td class="text-end font-weight-bold">{amount_str}</td>
                        <td><span class="{status_class}">{status}</span></td>
                        <td class="text-end">{fee_str}</td>
                        <td class="text-muted small">{memo_display}</td>
                    </tr>
            """
        
        html += """
                </tbody>
            </table>
        </div>
        """
        
        return html

    def action_fetch_transactions(self):
        """Manual action to fetch and update transaction data"""
        self.ensure_one()
        try:
            self._compute_transaction_data()
            self._compute_transaction_html()
            self.last_transaction_fetch = fields.Datetime.now()
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
        except Exception as e:
            raise ValidationError(f"Failed to fetch transactions: {str(e)}")

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