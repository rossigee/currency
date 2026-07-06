# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class CryptoLightningMacaroonPermission(models.Model):
    _name = 'crypto.lightning.macaroon.permission'
    _description = 'Lightning Macaroon Permission'
    _order = 'service, permission'

    service_provider_id = fields.Many2one(
        'crypto.lightning.service.provider',
        string='Service Provider',
        required=True,
        ondelete='cascade'
    )
    service = fields.Char(string='Service', required=True)
    permission = fields.Char(string='Permission', required=True)
    description = fields.Char(string='Description')

    def name_get(self):
        """Override name_get to display service: permission"""
        result = []
        for record in self:
            name = f"{record.service}: {record.permission}"
            if record.description:
                name += f" ({record.description})"
            result.append((record.id, name))
        return result