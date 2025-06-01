# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
import base58
import hashlib


class CryptoBitcoinWallet(models.Model):
    _name = 'crypto.bitcoin.wallet'
    _description = 'Crypto Bitcoin Wallet'

    name = fields.Char(string='Name', required=True)
    xpub = fields.Char(string='XPUB')
    owner_id = fields.Many2one('res.partner', string='Owner')
    notes = fields.Text(string='Notes')

    address_ids = fields.One2many('crypto.bitcoin.address', 'wallet_id', string='Addresses')
    sent_tx_ids = fields.One2many('crypto.bitcoin.transaction', 'from_wallet_id', string='Sent Transactions', compute='_compute_sent_tx_ids')
    rcvd_tx_ids = fields.One2many('crypto.bitcoin.transaction', 'to_wallet_id', string='Received Transactions', compute='_compute_rcvd_tx_ids')

    # Transient fields to display parsed XPUB details
    xpub_version = fields.Char(string='XPUB Version', compute='_compute_xpub_details', store=False)
    xpub_depth = fields.Integer(string='Depth', compute='_compute_xpub_details', store=False)
    xpub_parent_fingerprint = fields.Char(string='Parent Fingerprint', compute='_compute_xpub_details', store=False)
    xpub_child_number = fields.Integer(string='Child Number', compute='_compute_xpub_details', store=False)
    xpub_chain_code = fields.Char(string='Chain Code', compute='_compute_xpub_details', store=False)
    xpub_public_key = fields.Char(string='Public Key', compute='_compute_xpub_details', store=False)

    @api.depends('xpub')
    def _compute_xpub_details(self):
        for wallet in self:
            if not wallet.xpub:
                # Clear fields if xpub is empty
                wallet.xpub_version = ''
                wallet.xpub_depth = 0
                wallet.xpub_parent_fingerprint = ''
                wallet.xpub_child_number = 0
                wallet.xpub_chain_code = ''
                wallet.xpub_public_key = ''
                continue

            try:
                # Decode the base58 xpub
                decoded = base58.b58decode_check(wallet.xpub)

                # Extract the details
                wallet.xpub_version = decoded[:4].hex()
                wallet.xpub_depth = decoded[4]
                wallet.xpub_parent_fingerprint = decoded[5:9].hex()
                wallet.xpub_child_number = int.from_bytes(decoded[9:13], 'big')
                wallet.xpub_chain_code = decoded[13:45].hex()
                wallet.xpub_public_key = decoded[45:78].hex()
            except Exception:
                # If parsing fails, clear the fields
                wallet.xpub_version = ''
                wallet.xpub_depth = 0
                wallet.xpub_parent_fingerprint = ''
                wallet.xpub_child_number = 0
                wallet.xpub_chain_code = ''
                wallet.xpub_public_key = ''


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

