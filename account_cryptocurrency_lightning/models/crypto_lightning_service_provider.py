# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
import uuid


class CryptoLightningServiceProvider(models.Model):
    _name = 'crypto.lightning.service.provider'
    _description = 'Lightning Service Provider'
    _sql_constraints = [
        ('token_uuid_unique', 'unique(token_uuid)', 'Token UUID must be unique')
    ]

    name = fields.Char(string='Name', required=True)
    grpc_url = fields.Char(string='gRPC URL')
    macaroon = fields.Char(string='Macaroon', compute='_compute_vault_values', 
                          inverse='_inverse_vault_values', store=False, readonly=False)
    pubkey = fields.Char(string='Public key')
    clearnet_url = fields.Char(string='Clearnet URL')
    tor_url = fields.Char(string='TOR URL')
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')
    token_uuid = fields.Char(string='Token UUID', required=True, default=lambda self: str(uuid.uuid4()), 
                            copy=False, index=True)
    vault_status = fields.Char(string='Vault Status', compute='_compute_vault_values', store=False)

    def _inverse_vault_values(self):
        """Store macaroon data in vault"""
        for record in self:
            if record.token_uuid and record.macaroon:
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

    def action_refresh_vault_status(self):
        """Manually refresh vault status and data"""
        self.ensure_one()
        self._compute_vault_values()
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }