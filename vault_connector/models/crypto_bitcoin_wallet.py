# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
import base58
import hashlib


class CryptoBitcoinWallet(models.Model):
    _name = 'crypto.bitcoin.wallet'
    _description = 'Crypto Bitcoin Wallet'

    name = fields.Char(string='Name', required=True)
    owner_id = fields.Many2one('res.partner', string='Owner')
    notes = fields.Text(string='Notes')

    xpub_ids = fields.One2many('crypto.bitcoin.public.key', 'wallet_id', string='XPUBs')
    address_ids = fields.One2many('crypto.bitcoin.address', 'wallet_id', string='Addresses')
    sent_tx_ids = fields.One2many('crypto.bitcoin.transaction', 'from_wallet_id', string='Sent Transactions', compute='_compute_sent_tx_ids')
    rcvd_tx_ids = fields.One2many('crypto.bitcoin.transaction', 'to_wallet_id', string='Received Transactions', compute='_compute_rcvd_tx_ids')


    def _compute_sent_tx_ids(self):
        for wallet in self:
            address_ids = wallet.address_ids.ids
            transactions = self.env['crypto.bitcoin.transaction'].search([
                ('outputs', 'in', address_ids)
            ], order='date desc')
            wallet.sent_tx_ids = transactions

    def _compute_rcvd_tx_ids(self):
        for wallet in self:
            address_ids = wallet.address_ids.ids
            transactions = self.env['crypto.bitcoin.transaction'].search([
                ('inputs', 'in', address_ids)
            ], order='date desc')
            wallet.rcvd_tx_ids = transactions

    def action_create_multisig_wallet(self):
        action = self.env.ref('crypto_bitcoin_wallet_action_create_multisig').read()[0]
        action['context'] = {
            'default_type': 'multisig',
            'default_wallets': self.ids,
        }
        return action
