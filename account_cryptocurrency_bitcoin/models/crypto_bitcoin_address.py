# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class CryptoBitcoinAddress(models.Model):
    _name = 'crypto.bitcoin.address'
    _description = 'Crypto Bitcoin Address'
    _rec_name = 'display_name'

    address = fields.Char(string='Address', required=True)
    label = fields.Char(string='Label')
    wallet_id = fields.Many2one('crypto.bitcoin.wallet', string='Wallet')
    type = fields.Selection([
        ('receive', 'Receive'),
        ('change', 'Change'),
    ], string='Type', required=True)
    used = fields.Boolean(string='Used', default=False)
    notes = fields.Text(string='Notes')
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('label', 'address')
    def _compute_display_name(self):
        for record in self:
            if record.label:
                record.display_name = f"{record.label} ({record.address[:12]}...)"
            else:
                record.display_name = f"{record.address[:12]}..."
