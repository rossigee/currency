# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class ResCurrencyCryptocurrency(models.Model):
    _name = 'res.currency.cryptocurrency'
    _description = 'Cryptocurrency'

    _inherit = 'res.currency'

    blockchain = fields.Char(string='Blockchain')
    address_format = fields.Char(string='Address Format')
    xpub_supported = fields.Boolean(string='XPUB Supported', default=False)
    decimal_places = fields.Integer(string='Decimal Places')