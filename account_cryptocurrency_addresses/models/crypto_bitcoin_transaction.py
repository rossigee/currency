# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class CryptoBitcoinTransactionLine(models.Model):
    _name = 'crypto.bitcoin.transaction.line'
    _description = 'Crypto Bitcoin Transaction Line'

    transaction_id = fields.Many2one('crypto.transaction', "Transaction")
    line_hash = fields.Char(string="Line hash", required=True)
    address_id = fields.Many2one('crypto.address', string='Address')
    amount = fields.Float(string='Amount', required=True)


class CryptoBitcoinTransaction(models.Model):
    _name = 'crypto.bitcoin.transaction'
    _description = 'Crypto Bitcoin Transaction'

    date = fields.Datetime(string='Date')
    tx_hash = fields.Char(string='Transaction Hash', required=True)
    notes = fields.Text(string='Notes')
    size = fields.Integer(string="Size (vb)")
    inputs = fields.Many2one('crypto.bitcoin.transaction.line', string='Input TXs')
    outputs = fields.Many2one('crypto.bitcoin.transaction.line', string='Output TXs')
    amount = fields.Float(string='Amount', required=True)
    fee = fields.Float(string='Fee', required=True)
    status = fields.Selection([
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
    ], string='Status', required=True)
    rbf_enabled = fields.Boolean(string="Replace by fee enabled")
    lock_time = fields.Integer(string="Lock time (height)")
    mined_block = fields.Integer(string="Mined in block")

    from_wallet_id = fields.Many2one('crypto.bitcoin.wallet', string='From Wallet')
    to_wallet_id = fields.Many2one('crypto.bitcoin.wallet', string='To Wallet')
