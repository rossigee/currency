# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import json
from .lnd_rest_client import LndRestClient


class CryptoLightningAddress(models.Model):
    _name = 'crypto.lightning.address'
    _description = "Lightning Address"
    _inherit = ['mail.thread', 'mail.activity.mixin']

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
    
    # Related payments
    payment_ids = fields.One2many('crypto.lightning.payment', 'address_id', string='Lightning Payments')
    payment_count = fields.Integer(string='Payment Count', compute='_compute_payment_count')
    
    # Attachments
    attachment_count = fields.Integer(string='Attachment Count', compute='_compute_attachment_count')


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

    @api.depends('payment_ids')
    def _compute_payment_count(self):
        """Compute the number of payments for this address"""
        for record in self:
            record.payment_count = len(record.payment_ids)

    def _compute_attachment_count(self):
        """Compute the number of attachments for this address"""
        for record in self:
            record.attachment_count = self.env['ir.attachment'].search_count([
                ('res_model', '=', self._name),
                ('res_id', '=', record.id)
            ])

    def action_view_payments(self):
        """Open payments related to this lightning address"""
        self.ensure_one()
        action = self.env.ref('account_cryptocurrency_lightning.crypto_lightning_payment_action').read()[0]
        action['domain'] = [('address_id', '=', self.id)]
        action['context'] = {'default_address_id': self.id}
        return action

    def action_view_attachments(self):
        """Open attachments related to this lightning address"""
        self.ensure_one()
        return {
            'name': 'Attachments',
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'tree,form',
            'domain': [('res_model', '=', self._name), ('res_id', '=', self.id)],
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            }
        }

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
