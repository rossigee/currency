# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class CryptoLightningServiceProvider(models.Model):
    _name = 'crypto.lightning.service.provider'
    _description = 'Lightning Service Provider'

    name = fields.Char(string='Name', required=True)
    grpc_url = fields.Char(string='gRPC URL')
    macaroon = fields.Char(string='Macaroon')
    pubkey = fields.Char(string='Public key')
    clearnet_url = fields.Char(string='Clearnet URL')
    tor_url = fields.Char(string='TOR URL')
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')