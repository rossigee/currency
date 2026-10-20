# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    bitcoin_wallet_ids = fields.One2many('crypto.bitcoin.wallet', 'owner_id', string='Bitcoin Wallets')
