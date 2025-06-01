# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class CryptoLightningAddress(models.Model):
    _name = 'crypto.lightning.address'
    _description = "Lightning Address"

    owner_id = fields.Many2one('res.partner', string='Owner')
    address = fields.Char(string='Lightning Address', required=True)
    type = fields.Selection([
        ('bolt11', 'BOLT11'),
        ('bolt12', 'BOLT12'),
        ('other', 'Other'),
    ], string='Type', required=True, default='bolt11')
    notes = fields.Text(string='Notes')

    def _compute_display_name(self):
        for address in self:
            address.display_name = f'{address.address} ({address.owner_id.name})'

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
