# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
import base58
import hashlib
import time
import logging

_logger = logging.getLogger(__name__)


class CryptoBitcoinWallet(models.Model):
    _name = 'crypto.bitcoin.wallet'
    _description = 'Crypto Bitcoin Wallet'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True, tracking=True)
    owner_id = fields.Many2one('res.partner', string='Owner', tracking=True)
    notes = fields.Text(string='Notes')

    xpub_ids = fields.One2many('crypto.bitcoin.public.key', 'wallet_id', string='XPUBs')
    address_ids = fields.One2many('crypto.bitcoin.address', 'wallet_id', string='Addresses')
    sent_tx_ids = fields.Many2many('crypto.bitcoin.transaction', string='Sent Transactions', compute='_compute_sent_tx_ids')
    rcvd_tx_ids = fields.Many2many('crypto.bitcoin.transaction', string='Received Transactions', compute='_compute_rcvd_tx_ids')


    def _compute_sent_tx_ids(self):
        for wallet in self:
            address_ids = wallet.address_ids.ids
            # Find transactions where wallet addresses appear in outputs (money sent to this wallet)
            transactions = self.env['crypto.bitcoin.transaction'].search([
                ('output_line_ids.address_id', 'in', address_ids)
            ], order='date desc')
            wallet.sent_tx_ids = transactions

    def _compute_rcvd_tx_ids(self):
        for wallet in self:
            address_ids = wallet.address_ids.ids
            # Find transactions where wallet addresses appear in inputs (money spent from this wallet)
            transactions = self.env['crypto.bitcoin.transaction'].search([
                ('input_line_ids.address_id', 'in', address_ids)
            ], order='date desc')
            wallet.rcvd_tx_ids = transactions

    def action_create_multisig_wallet(self):
        action = self.env.ref('crypto_bitcoin_wallet_action_create_multisig').read()[0]
        action['context'] = {
            'default_type': 'multisig',
            'default_wallets': self.ids,
        }
        return action

    def action_import_transactions(self):
        """Import transactions for all addresses in this wallet"""
        self.ensure_one()
        
        # Prevent concurrent imports
        import_key = f"wallet_import_{self.id}"
        if hasattr(self.env, '_wallet_imports_running'):
            if import_key in self.env._wallet_imports_running:
                _logger.warning(f"Import already running for wallet {self.id}, skipping")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Import In Progress',
                        'message': 'Transaction import is already running for this wallet.',
                        'type': 'warning'
                    }
                }
        else:
            self.env._wallet_imports_running = set()
        
        # Queue background job for transaction import
        job = self.with_delay(description=f"Import transactions for wallet {self.name}")._import_transactions_background()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Transaction Import Started',
                'message': f'Transaction import has been queued as background job. You will be notified when complete.',
                'type': 'info'
            }
        }

    def _import_transactions_background(self):
        """Import transactions in background job"""
        try:
            if not self.address_ids:
                self.env.user.notify_warning(
                    message='This wallet has no addresses to fetch transactions for.',
                    title="No Addresses"
                )
                return
        
            # Main import logic
            total_created = 0
            total_updated = 0
            total_transactions = 0
            chunk_size = 5  # Show progress every 5 addresses
            
            # Limit to first 50 addresses to prevent runaway processes
            addresses_to_check = self.address_ids[:50]
            if len(self.address_ids) > 50:
                _logger.warning(f"Wallet has {len(self.address_ids)} addresses, limiting to first 50 for transaction import")
            
            # Track processed addresses to detect duplicates
            processed_addresses = set()
            
            for i, address in enumerate(addresses_to_check, 1):
                # Check for duplicate addresses
                if address.address in processed_addresses:
                    _logger.error(f"Duplicate address detected: {address.address} - skipping")
                    continue
                processed_addresses.add(address.address)
                _logger.info(f"Processing wallet address {i}/{len(addresses_to_check)}: {address.address}")
                
                result = self.env['crypto.bitcoin.transaction'].fetch_address_transactions(
                    address.address, 
                    network='mainnet'  # TODO: Make this configurable
                )
                total_created += result['created']
                total_updated += result['updated']
                total_transactions += result['total']
                
                _logger.info(f"Address {address.address} complete: {result['created']} new, {result['updated']} updated, {result['total']} total")
                
                
                # Add a small delay between addresses to avoid overwhelming the API
                if i < len(addresses_to_check):  # Don't delay after the last address
                    time.sleep(0.5)
            
            # Send completion notification to user
            message = f"Wallet transaction import complete!\n• {total_created} new transactions\n• {total_updated} updated transactions\n• {total_transactions} total found\n• {len(addresses_to_check)} addresses scanned"
            
            self.env.user.notify_success(
                message=message,
                title="Transaction Import Complete"
            )
            
            _logger.info(f"Background transaction import completed for wallet {self.name}: {total_created} new, {total_updated} updated")
            
        except Exception as e:
            error_msg = f'Failed to import wallet transactions: {str(e)}'
            _logger.error(f"Background transaction import failed for wallet {self.name}: {str(e)}")
            
            self.env.user.notify_danger(
                message=error_msg,
                title="Transaction Import Failed"
            )
            raise
