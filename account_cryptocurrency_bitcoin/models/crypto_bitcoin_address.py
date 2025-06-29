# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class CryptoBitcoinAddress(models.Model):
    _name = 'crypto.bitcoin.address'
    _description = 'Crypto Bitcoin Address'
    _rec_name = 'display_name'

    address = fields.Char(string='Address', required=True)
    label = fields.Char(string='Label')
    wallet_id = fields.Many2one('crypto.bitcoin.wallet', string='Wallet')
    type = fields.Selection([
        ('receive', 'Receive'),
        ('change', 'Change'),
    ], string='Type', required=True)
    used = fields.Boolean(string='Used', default=False)
    notes = fields.Text(string='Notes')
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    
    # Transaction-related computed fields
    transaction_count = fields.Integer(string='Transactions', compute='_compute_transaction_stats', store=False)
    last_transaction_date = fields.Datetime(string='Last Transaction', compute='_compute_transaction_stats', store=False)
    balance = fields.Float(string='Balance (BTC)', compute='_compute_transaction_stats', store=False, digits=(16, 8))
    related_transaction_ids = fields.Many2many('crypto.bitcoin.transaction', string='Related Transactions', 
                                             compute='_compute_related_transactions', store=False)

    @api.depends('label', 'address')
    def _compute_display_name(self):
        for record in self:
            if record.label:
                record.display_name = f"{record.label} ({record.address[:12]}...)"
            else:
                record.display_name = f"{record.address[:12]}..."
    
    def _compute_transaction_stats(self):
        """Compute transaction statistics for this address"""
        for record in self:
            # Find all transactions involving this address
            transactions = self.env['crypto.bitcoin.transaction'].search([
                '|',
                ('input_line_ids.address_id', '=', record.id),
                ('output_line_ids.address_id', '=', record.id)
            ])
            
            record.transaction_count = len(transactions)
            
            if transactions:
                # Get the most recent transaction
                latest_tx = transactions.sorted('date', reverse=True)[0]
                record.last_transaction_date = latest_tx.date
                
                # Calculate balance (received - sent)
                received = sum(
                    line.amount for tx in transactions
                    for line in tx.output_line_ids
                    if line.address_id.id == record.id
                )
                sent = sum(
                    line.amount for tx in transactions
                    for line in tx.input_line_ids
                    if line.address_id.id == record.id
                )
                record.balance = received - sent
            else:
                record.last_transaction_date = False
                record.balance = 0.0
    
    def _compute_related_transactions(self):
        """Compute all transactions related to this address"""
        for record in self:
            # Find all transactions involving this address
            transactions = self.env['crypto.bitcoin.transaction'].search([
                '|',
                ('input_line_ids.address_id', '=', record.id),
                ('output_line_ids.address_id', '=', record.id)
            ], order='date desc')
            
            record.related_transaction_ids = transactions
    
    def action_fetch_transactions(self):
        """Fetch transactions for this specific address"""
        self.ensure_one()
        
        if not self.address:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Address',
                    'message': 'Cannot fetch transactions: no address specified.',
                    'type': 'warning'
                }
            }
        
        # Queue background job for transaction fetch
        job = self.with_delay(description=f"Fetch transactions for address {self.address[:12]}...")._fetch_transactions_background()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Transaction Fetch Started',
                'message': f'Transaction fetch has been queued as background job. Check Bitcoin Job Queue for progress.',
                'type': 'info'
            }
        }
    
    def _fetch_transactions_background(self):
        """Fetch transactions in background job"""
        import logging
        _logger = logging.getLogger(__name__)
        
        try:
            _logger.info(f"Starting background transaction fetch for address: {self.address}")
            
            if not self.address:
                raise ValueError("No address specified for transaction fetch")
                
            # Validate address format before attempting fetch
            if not self.env['crypto.bip32.utils'].validate_bitcoin_address(self.address):
                error_msg = f"Invalid Bitcoin address format: {self.address}"
                self.env.user.notify_warning(
                    message=error_msg,
                    title="Invalid Address"
                )
                raise ValueError(f"Address validation failed: {self.address} is not a valid Bitcoin address format")
            
            _logger.info(f"Address validation passed, fetching transactions for: {self.address}")
            
            # Get Bitcoin services configuration
            services_config = self.env['bitcoin.settings'].get_services_config()
            
            result = self.env['crypto.bitcoin.transaction'].fetch_address_transactions(
                self.address,
                network=services_config['network']
            )
            
            _logger.info(f"Transaction fetch completed with result: {result}")
            
            # Send completion notification to user
            message = f"Address transaction fetch complete!\n• {result['created']} new transactions\n• {result['updated']} updated transactions\n• {result['total']} total found\n\nAddress: {self.address}"
            
            self.env.user.notify_success(
                message=message,
                title="Transaction Fetch Complete"
            )
            
            # Mark address as used if transactions were found
            if result['total'] > 0 and not self.used:
                self.used = True
            
            # Return result summary for job queue display
            return f"✅ Address fetch completed: {result['created']} new, {result['updated']} updated, {result['total']} total transactions for {self.address[:12]}..."
            
        except Exception as e:
            _logger.error(f"Transaction fetch failed for address {self.address}: {str(e)}", exc_info=True)
            error_msg = f'Failed to fetch transactions for address {self.address}: {str(e)}'
            
            # Provide more helpful error messages based on common issues
            if "HTTP 400" in str(e):
                error_msg += "\n\nPossible causes:\n• Invalid address format\n• Address not recognized by API\n• API rate limiting"
            elif "HTTP 429" in str(e):
                error_msg += "\n\nAPI rate limit exceeded. Please try again later."
            elif "HTTP 503" in str(e):
                error_msg += "\n\nAPI service temporarily unavailable. Please try again later."
            
            self.env.user.notify_danger(
                message=error_msg,
                title="Transaction Fetch Failed"
            )
            
            # Re-raise the exception so the job is marked as failed
            raise
