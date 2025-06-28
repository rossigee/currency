# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import json
from .lnd_rest_client import LndRestClient


class CryptoLightningAddress(models.Model):
    _name = 'crypto.lightning.address'
    _description = "Lightning Address"

    owner_id = fields.Many2one('res.partner', string='Owner')
    address = fields.Char(string='Lightning Address', required=True)
    active = fields.Boolean(string='Active', default=True)
    type = fields.Selection([
        ('bolt11', 'BOLT11'),
        ('bolt12', 'BOLT12'),
        ('other', 'Other'),
    ], string='Type', required=True, default='bolt11')
    service_provider_id = fields.Many2one('crypto.lightning.service.provider', string='Service Provider',
                                        help='LND service provider to fetch transaction data from')
    notes = fields.Text(string='Notes')

    # Transaction-related fields (computed)
    transaction_data = fields.Text(string='Transaction Data', compute='_compute_transaction_data', store=False)
    last_transaction_fetch = fields.Datetime(string='Last Fetch', readonly=True)

    def _compute_display_name(self):
        for address in self:
            if address.owner_id:
                address.display_name = f'{address.address} ({address.owner_id.name})'
            else:
                address.display_name = address.address

    def name_get(self):
        """Custom name_get for better display in selection fields"""
        result = []
        for record in self:
            if record.owner_id:
                name = f'{record.address} ({record.owner_id.name})'
            else:
                name = record.address or 'Unnamed Address'
            result.append((record.id, name))
        return result

    @api.depends('service_provider_id', 'address')
    def _compute_transaction_data(self):
        """Compute transaction data by fetching from LND service"""
        for record in self:
            if record.service_provider_id:
                try:
                    transactions = record._fetch_transactions_from_lnd()
                    record.transaction_data = json.dumps(transactions, indent=2)
                except Exception as e:
                    record.transaction_data = f"Error fetching transactions: {str(e)}"
            else:
                record.transaction_data = "No service provider configured"

    def _fetch_transactions_from_lnd(self):
        """Fetch transactions related to this address from LND"""
        if not self.service_provider_id:
            raise ValidationError("No service provider configured for this address")

        # Get service provider details
        service_provider = self.service_provider_id
        if not service_provider.rest_url:
            raise ValidationError("Service provider has no REST URL configured")

        # Get macaroon from vault
        vault_data = service_provider._get_data_from_vault(service_provider.token_uuid)
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
        client = LndRestClient(service_provider.rest_url, macaroon_hex)
        client.connect()

        try:
            # Fetch invoices and payments
            invoices_data = client.list_invoices(100)
            payments_data = client.list_payments(100)

            # Filter transactions related to this address
            related_transactions = self._filter_transactions_for_address(invoices_data, payments_data)

            return related_transactions
        finally:
            client.close()

    def _filter_transactions_for_address(self, invoices_data, payments_data):
        """Filter transactions to find those related to this Lightning address"""
        transactions = []

        # Process invoices (incoming payments)
        for invoice in invoices_data.get('invoices', []):
            # For Lightning addresses, we'd need to check if the invoice
            # is related to this address (this is simplified)
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

        return transactions[:50]  # Return latest 50 transactions

    def action_fetch_transactions(self):
        """Manual action to fetch and update transaction data"""
        self.ensure_one()
        try:
            self._compute_transaction_data()
            self.last_transaction_fetch = fields.Datetime.now()
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
        except Exception as e:
            raise ValidationError(f"Failed to fetch transactions: {str(e)}")

    def create_payment(self):
        """
        Create a new payment form for the current Lightning address.
        """
        payment_form = self.env['crypto.lightning.payment.form'].create({
            'address_id': self.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crypto.lightning.payment.form',
            'res_id': payment_form.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_address_id': self.id},
        }
