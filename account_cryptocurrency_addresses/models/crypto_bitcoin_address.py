# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class CryptoBitcoinAddress(models.Model):
    _name = 'crypto.bitcoin.address'
    _description = 'Crypto Bitcoin Address'

    address = fields.Char(string='Address', required=True)
    label = fields.Char(string='Label')
    wallet_id = fields.Many2one('crypto.bitcoin.wallet', string='Wallet')
    type = fields.Selection([
        ('receive', 'Receive'),
        ('change', 'Change'),
    ], string='Type', required=True)
    used = fields.Boolean(string='Used', default=False)
    notes = fields.Text(string='Notes')
