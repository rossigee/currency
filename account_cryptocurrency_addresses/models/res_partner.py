# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    bitcoin_wallet_ids = fields.One2many('crypto.bitcoin.wallet', 'owner_id', string='Bitcoin Wallets')
    lightning_address_ids = fields.One2many('crypto.lightning.address', 'owner_id', string='Lightning Addresses', compute='_compute_crypto_lightning_address_ids', store=True, readonly=False)

    def _compute_lightning_address_ids(self):
        for partner in self:
            partner.lightning_address_ids = self.env['crypto.lightning.address'].search([('owner_id', '=', partner.id)])