# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import base64
import logging

_logger = logging.getLogger(__name__)


class CryptoBitcoinTransactionLine(models.Model):
    _name = 'crypto.bitcoin.transaction.line'
    _description = 'Crypto Bitcoin Transaction Line'

    transaction_id = fields.Many2one('crypto.bitcoin.transaction', string='Transaction', required=True, ondelete='cascade')
    line_type = fields.Selection([
        ('input', 'Input'),
        ('output', 'Output')
    ], string='Line Type', required=True)
    
    # Output fields
    address_id = fields.Many2one('crypto.bitcoin.address', string='Address Record', help="Bitcoin address record (for outputs)")
    address = fields.Char(related='address_id.address', string='Address', readonly=True, store=True)
    amount = fields.Float(string='Amount (BTC)', required=True, digits=(16, 8))
    amount_sat = fields.Integer(string='Amount (sat)', compute='_compute_amount_sat', store=False)
    
    # Input fields (for future use)
    prev_tx_hash = fields.Char(string='Previous TX Hash', help="Previous transaction hash (for inputs)")
    prev_output_index = fields.Integer(string='Previous Output Index', help="Output index in previous transaction")
    
    # Common fields
    sequence = fields.Integer(string='Sequence', default=10)
    description = fields.Char(string='Description')

    @api.depends('amount')
    def _compute_amount_sat(self):
        """Convert BTC amount to satoshis"""
        for record in self:
            record.amount_sat = int(record.amount * 100000000) if record.amount else 0


class CryptoBitcoinTransaction(models.Model):
    _name = 'crypto.bitcoin.transaction'
    _description = 'Crypto Bitcoin Transaction'
    _rec_name = 'tx_hash_display'

    date = fields.Datetime(string='Date')
    imported_date = fields.Datetime(string='Imported Date', default=fields.Datetime.now, readonly=True)
    tx_hash = fields.Char(string='Transaction Hash', help="Transaction hash (set when broadcast)", required=True, default='[Pending]')
    notes = fields.Text(string='Notes')
    size = fields.Integer(string="Size (vb)")
    transaction_line_ids = fields.One2many('crypto.bitcoin.transaction.line', 'transaction_id', string='Transaction Lines')
    input_line_ids = fields.One2many('crypto.bitcoin.transaction.line', 'transaction_id', 
                                     string='Inputs', domain=[('line_type', '=', 'input')])
    output_line_ids = fields.One2many('crypto.bitcoin.transaction.line', 'transaction_id', 
                                      string='Outputs', domain=[('line_type', '=', 'output')])
    amount = fields.Float(string='Amount', required=True)
    fee = fields.Float(string='Fee', required=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('unsigned_psbt', 'Unsigned PSBT'),
        ('partial_psbt', 'Partially Signed PSBT'),
        ('signed_psbt', 'Fully Signed PSBT'),
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
    ], string='Status', required=True)
    rbf_enabled = fields.Boolean(string="Replace by fee enabled")
    lock_time = fields.Integer(string="Lock time (height)")
    mined_block = fields.Integer(string="Mined in block")
    confirmations = fields.Integer(string="Confirmations", compute='_compute_confirmations', store=False)

    from_wallet_id = fields.Many2one('crypto.bitcoin.wallet', string='From Wallet')
    to_wallet_id = fields.Many2one('crypto.bitcoin.wallet', string='To Wallet')
    
    # PSBT-specific fields
    multisig_wallet_id = fields.Many2one('crypto.bitcoin.multisig.wallet', string='Multisig Wallet')
    psbt_base64 = fields.Text(string='PSBT (Base64)', help="Partially Signed Bitcoin Transaction in base64 format")
    raw_transaction = fields.Text(string='Raw Transaction (Hex)', help="Final transaction in hex format")
    
    # Signing tracking
    required_signatures = fields.Integer(string='Required Signatures', help="M threshold from multisig wallet")
    current_signatures = fields.Integer(string='Current Signatures', compute='_compute_signature_count', store=False)
    signatures_complete = fields.Boolean(string='Signatures Complete', compute='_compute_signature_count', store=False)
    
    # Transaction creation metadata
    created_by_id = fields.Many2one('res.partner', string='Created By')
    target_fee_rate = fields.Float(string='Target Fee Rate (sat/vB)', help="Target fee rate for transaction")
    
    # PSBT summary
    psbt_summary = fields.Text(string='PSBT Summary', compute='_compute_psbt_summary', store=False)
    
    # Display fields
    tx_hash_display = fields.Char(string='Transaction Hash', compute='_compute_tx_hash_display', store=False)
    
    # Legacy compatibility fields (to avoid view errors)
    inputs = fields.Char(string='Legacy Inputs', compute='_compute_legacy_fields', store=False)
    outputs = fields.Char(string='Legacy Outputs', compute='_compute_legacy_fields', store=False)

    @api.depends('psbt_base64', 'required_signatures')
    def _compute_signature_count(self):
        """Compute current signature count from PSBT"""
        for record in self:
            if not record.psbt_base64:
                record.current_signatures = 0
                record.signatures_complete = False
                continue
                
            try:
                # Use PSBT parsing utility
                bip32_utils = self.env['crypto.bip32.utils']
                sig_info = bip32_utils.parse_psbt_signatures(record.psbt_base64)
                
                record.current_signatures = sig_info['signature_count']
                record.signatures_complete = (
                    record.required_signatures > 0 and 
                    record.current_signatures >= record.required_signatures
                )
            except Exception as e:
                _logger.warning(f"Failed to parse PSBT signatures: {str(e)}")
                record.current_signatures = 0
                record.signatures_complete = False

    @api.depends('psbt_base64', 'output_line_ids', 'multisig_wallet_id', 'amount', 'fee', 'current_signatures', 'required_signatures')
    def _compute_psbt_summary(self):
        """Generate user-friendly PSBT summary"""
        for record in self:
            if not record.psbt_base64:
                record.psbt_summary = ""
                continue
                
            summary_lines = []
            
            # Transaction details
            summary_lines.append("📄 PSBT Transaction Summary")
            summary_lines.append("=" * 40)
            
            if record.multisig_wallet_id:
                summary_lines.append(f"🏦 Wallet: {record.multisig_wallet_id.name}")
                summary_lines.append(f"🔐 Multisig: {record.multisig_wallet_id.m_of_n_threshold}-of-{record.multisig_wallet_id.total_cosigners}")
            
            summary_lines.append(f"💰 Total Amount: {record.amount:.8f} BTC")
            summary_lines.append(f"⚡ Fee: {record.fee:.8f} BTC")
            if record.target_fee_rate:
                summary_lines.append(f"📊 Fee Rate: {record.target_fee_rate} sat/vB")
            
            # Signing status
            summary_lines.append("")
            summary_lines.append("✍️ Signing Status:")
            progress = f"{record.current_signatures}/{record.required_signatures}"
            if record.signatures_complete:
                summary_lines.append(f"   ✅ Complete ({progress} signatures)")
            else:
                summary_lines.append(f"   ⏳ Pending ({progress} signatures)")
            
            # Outputs
            if record.output_line_ids:
                summary_lines.append("")
                summary_lines.append("📤 Outputs:")
                for i, output in enumerate(record.output_line_ids, 1):
                    summary_lines.append(f"   {i}. {output.amount:.8f} BTC → {output.address}")
                    if output.description:
                        summary_lines.append(f"      ({output.description})")
            
            # Instructions
            summary_lines.append("")
            summary_lines.append("🔧 Next Steps:")
            if record.signatures_complete:
                summary_lines.append("   • Transaction is fully signed and ready to broadcast")
            else:
                summary_lines.append("   • Download PSBT file and sign with your wallet software")
                summary_lines.append("   • Import the signed PSBT when ready")
            
            record.psbt_summary = "\n".join(summary_lines)

    @api.depends('input_line_ids', 'output_line_ids')
    def _compute_legacy_fields(self):
        """Compute legacy fields for backward compatibility"""
        for record in self:
            record.inputs = ""
            record.outputs = ""

    @api.depends('mined_block')
    def _compute_confirmations(self):
        """Compute real-time confirmations using Bitcoin connector - OPTIMIZED for batch processing"""
        # Group records by whether they need confirmation calculation
        unconfirmed_records = self.filtered(lambda r: not r.mined_block)
        confirmed_records = self.filtered(lambda r: r.mined_block)
        
        # Set unconfirmed to 0
        for record in unconfirmed_records:
            record.confirmations = 0
        
        if not confirmed_records:
            return
            
        try:
            # Get Bitcoin settings from config parameters
            use_local_node = self.env['ir.config_parameter'].sudo().get_param('bitcoin.use_local_node', True)
            
            if not use_local_node:
                # All confirmed records get 0 confirmations if not using local node
                for record in confirmed_records:
                    record.confirmations = 0
                return
            
            # Get current block height ONCE for all transactions
            current_height = self._get_cached_current_block_height()
            if not current_height:
                _logger.warning("Could not get current block height, setting all confirmations to 0")
                for record in confirmed_records:
                    record.confirmations = 0
                return
            
            # Calculate confirmations for all confirmed records using the single block height fetch
            for record in confirmed_records:
                record.confirmations = max(0, current_height - record.mined_block + 1)
                
        except Exception as e:
            _logger.warning(f"Failed to compute confirmations: {str(e)}")
            for record in confirmed_records:
                record.confirmations = 0

    def _get_cached_current_block_height(self):
        """Get current block height with caching to avoid multiple Bitcoin node calls"""
        import time
        
        # Use class-level cache with 60 second TTL
        cache_key = 'current_block_height'
        current_time = time.time()
        
        if not hasattr(self.__class__, '_block_height_cache'):
            self.__class__._block_height_cache = {}
        
        cache_data = self.__class__._block_height_cache.get(cache_key)
        if cache_data and (current_time - cache_data['timestamp']) < 60:
            _logger.info(f"Using cached block height: {cache_data['height']}")
            return cache_data['height']
        
        # Cache miss or expired - fetch from Bitcoin node
        try:
            connector = self.env['bitcoin.connector'].get_default_connector()
            if connector:
                current_height = connector.get_current_block_height()
                self.__class__._block_height_cache[cache_key] = {
                    'height': current_height,
                    'timestamp': current_time
                }
                _logger.info(f"Fetched and cached new block height: {current_height}")
                return current_height
        except Exception as e:
            _logger.error(f"Failed to get current block height: {str(e)}")
        
        return None

    @api.depends('tx_hash')
    def _compute_tx_hash_display(self):
        """Format transaction hash for display: first6...last6"""
        for record in self:
            if not record.tx_hash or record.tx_hash == '[Pending]':
                record.tx_hash_display = record.tx_hash or ''
            else:
                # Format as first6...last6
                record.tx_hash_display = f"{record.tx_hash[:6]}...{record.tx_hash[-6:]}"

    def action_create_psbt(self):
        """Create unsigned PSBT for this transaction"""
        self.ensure_one()
        
        if not self.multisig_wallet_id:
            raise ValidationError("Multisig wallet required for PSBT creation")
            
        if not self.multisig_wallet_id.is_complete:
            raise ValidationError("Multisig wallet configuration incomplete")
        
        # For now, create a simple test output
        # In a real implementation, this would come from user input
        test_outputs = [
            {
                'address': 'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh',
                'amount': 100000  # 0.001 BTC in satoshis
            }
        ]
        
        try:
            # Use PSBT creation utility
            bip32_utils = self.env['crypto.bip32.utils']
            psbt_result = bip32_utils.create_psbt(
                self.multisig_wallet_id, 
                test_outputs, 
                self.target_fee_rate
            )
            
            # Update transaction with PSBT data
            self.write({
                'psbt_base64': psbt_result['psbt_base64'],
                'required_signatures': self.multisig_wallet_id.m_of_n_threshold,
                'amount': psbt_result['total_output'] / 100000000,  # Convert to BTC
                'fee': psbt_result['estimated_fee'] / 100000000,    # Convert to BTC
                'target_fee_rate': psbt_result['fee_rate'],
                'status': 'unsigned_psbt'
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'PSBT Created',
                    'message': f'Created PSBT with {psbt_result["total_output"]} sat output + {psbt_result["estimated_fee"]} sat fee',
                    'type': 'success'
                }
            }
            
        except Exception as e:
            raise ValidationError(f"PSBT creation failed: {str(e)}")

    def action_export_psbt(self):
        """Export BIP-174 compliant PSBT file for external signing"""
        self.ensure_one()
        
        if not self.psbt_base64:
            raise ValidationError("No PSBT available for export")
        
        try:
            # The psbt_base64 field should already contain proper BIP-174 PSBT data
            # encoded as base64 from the embit library
            
            # Generate filename
            filename = f"transaction_{self.id}.psbt"
            
            # Create attachment - Odoo expects base64 data for binary attachments
            attachment = self.env['ir.attachment'].create({
                'name': filename,
                'type': 'binary',
                'datas': self.psbt_base64,  # Use the base64 data directly
                'res_model': self._name,
                'res_id': self.id,
                'mimetype': 'application/octet-stream',
            })
            
            return {
                'type': 'ir.actions.act_url',
                'url': f'/web/content/{attachment.id}?download=true',
                'target': 'self',
            }
            
        except Exception as e:
            _logger.error(f"PSBT export failed: {str(e)}")
            raise ValidationError(f"Failed to export PSBT: {str(e)}")

    def action_import_psbt(self):
        """Import signed PSBT"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Import Signed PSBT',
            'res_model': 'wizard.import.psbt',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_transaction_id': self.id,
            }
        }

    def action_fetch_from_blockchain(self):
        """Fetch transaction details from blockchain"""
        self.ensure_one()
        
        if not self.tx_hash or self.tx_hash == '[Pending]':
            raise ValidationError("Transaction hash is required to fetch from blockchain")
        
        try:
            # Try Electrum first, fallback to Bitcoin Core if available
            tx_data = None
            
            # Try Electrum
            try:
                electrum_client = self.env['electrum.client'].get_default_client()
                tx_data = electrum_client.get_transaction(self.tx_hash)
            except Exception as e:
                _logger.warning(f"Electrum fetch failed, trying Bitcoin Core: {str(e)}")
            
            # If Electrum failed, try Bitcoin Core
            if not tx_data:
                try:
                    bitcoin_connector = self.env['bitcoin.connector'].get_configured_connector()
                    tx_data = bitcoin_connector.get_transaction_details(self.tx_hash)
                except Exception as e:
                    _logger.warning(f"Bitcoin Core fetch also failed: {str(e)}")
            
            if not tx_data:
                raise ValidationError("No Bitcoin services available or all services failed to fetch transaction")
            
            # Update transaction with blockchain data
            self._update_from_blockchain_data(tx_data)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Transaction Updated',
                    'message': f'Updated transaction {self.tx_hash[:16]}... from blockchain',
                    'type': 'success'
                }
            }
            
        except Exception as e:
            _logger.error(f"Failed to fetch transaction {self.tx_hash}: {str(e)}")
            raise ValidationError(f"Failed to fetch transaction: {str(e)}")

    def _update_from_blockchain_data(self, tx_data):
        """Update transaction fields from blockchain data"""
        self.ensure_one()
        
        update_vals = {}
        
        # Update basic transaction data
        if tx_data.get('size'):
            update_vals['size'] = tx_data['size']
        if tx_data.get('fee'):
            update_vals['fee'] = tx_data['fee'] / 100000000  # Convert satoshis to BTC
        if tx_data.get('block_time'):
            from datetime import datetime
            import pytz
            
            # Bitcoin timestamps are in UTC
            utc_datetime = datetime.fromtimestamp(tx_data['block_time'], tz=pytz.UTC)
            # Convert to naive datetime for Odoo (Odoo expects naive datetime in UTC)
            update_vals['date'] = utc_datetime.replace(tzinfo=None)
            _logger.info(f"Updating transaction {self.tx_hash[:16]}... - Block time: {tx_data['block_time']}, converted date: {update_vals['date']} UTC")
        
        # Update amount with address-specific value (same logic as _prepare_transaction_from_blockchain_data)
        if tx_data.get('value') is not None:
            address_specific_value_sats = tx_data['value']
            address_specific_value_btc = address_specific_value_sats / 100000000 if address_specific_value_sats > 0 else 0
            update_vals['amount'] = address_specific_value_btc
            _logger.info(f"Updating transaction {self.tx_hash[:16]}... - Address-specific value: {address_specific_value_sats} sats ({address_specific_value_btc} BTC)")
        
        # Update wallet linking if not already set and context provides wallet info
        if not self.multisig_wallet_id and not self.from_wallet_id:
            multisig_wallet = self.env.context.get('multisig_wallet')
            wallet = self.env.context.get('wallet')
            if multisig_wallet:
                update_vals['multisig_wallet_id'] = multisig_wallet.id
                _logger.info(f"Linking existing transaction {self.tx_hash[:16]}... to multisig wallet {multisig_wallet.name}")
            elif wallet:
                update_vals['from_wallet_id'] = wallet.id
                _logger.info(f"Linking existing transaction {self.tx_hash[:16]}... to wallet {wallet.name}")
        
        # Update status and block information
        if tx_data.get('confirmations', 0) > 0:
            update_vals['status'] = 'confirmed'
        else:
            update_vals['status'] = 'pending'
            
        # Set block height - same field mapping as create logic
        if tx_data.get('height') and tx_data['height'] > 0:
            update_vals['mined_block'] = tx_data['height']
        elif tx_data.get('block_height'):
            update_vals['mined_block'] = tx_data['block_height']
        
        # Update confirmation status in notes
        if tx_data.get('confirmations'):
            confirmations = tx_data['confirmations']
            block_height = tx_data.get('height') or tx_data.get('block_height', 'Unknown')
            status_note = f"Confirmed in block {block_height} ({confirmations} confirmations)"
            
            if self.notes and 'Blockchain Status:' not in self.notes:
                update_vals['notes'] = f"{self.notes}\n\nBlockchain Status: {status_note}"
            else:
                update_vals['notes'] = f"Blockchain Status: {status_note}"
        
        if update_vals:
            _logger.info(f"Updating transaction {self.tx_hash[:16]}... with fields: {list(update_vals.keys())}")
            self.write(update_vals)

    @api.model
    def fetch_address_transactions(self, address, network='mainnet'):
        """Fetch all transactions for a Bitcoin address and create transaction records"""
        # Use a savepoint to isolate this entire operation
        try:
            with self.env.cr.savepoint():
                _logger.info(f"Starting transaction fetch for address: {address}")
                
                # Aggressive circuit breaker: prevent rapid repeated calls
                import time
                cache_key = f"tx_fetch_{address}_{network}"
                current_time = time.time()
                
                if not hasattr(self.env, '_tx_fetch_cache'):
                    self.env._tx_fetch_cache = {}
                if not hasattr(self.env, '_tx_fetch_call_count'):
                    self.env._tx_fetch_call_count = {}
                
                # Track call frequency for this address
                if cache_key not in self.env._tx_fetch_call_count:
                    self.env._tx_fetch_call_count[cache_key] = []
                
                # Clean old entries (older than 10 seconds)
                cutoff_time = current_time - 10
                self.env._tx_fetch_call_count[cache_key] = [
                    t for t in self.env._tx_fetch_call_count[cache_key] if t > cutoff_time
                ]
                
                # Check if too many calls in short time
                if len(self.env._tx_fetch_call_count[cache_key]) >= 5:
                    import traceback
                    stack_trace = traceback.format_stack()
                    _logger.error(f"TOO MANY CALLS for address {address} - {len(self.env._tx_fetch_call_count[cache_key])} calls in 10 seconds. STOPPING EXECUTION.")
                    _logger.error(f"STACK TRACE for infinite loop:\n{''.join(stack_trace)}")
                    raise ValidationError(f"Transaction fetch aborted due to infinite loop detection for address {address}")
                
                # Add current call time
                self.env._tx_fetch_call_count[cache_key].append(current_time)
                
                # Check if this address was processed in the last 30 seconds
                if cache_key in self.env._tx_fetch_cache:
                    last_processed = self.env._tx_fetch_cache[cache_key]
                    if current_time - last_processed < 30:  # 30 second cooldown
                        _logger.warning(f"Address {address} was processed {int(current_time - last_processed)} seconds ago, skipping to prevent infinite loop")
                        return {'created': 0, 'updated': 0, 'total': 0}
                
                # Record the current processing time
                self.env._tx_fetch_cache[cache_key] = current_time
                
                # Use Electrum client to fetch transactions
                electrum_client = self.env['electrum.client'].get_default_client()
                transactions = electrum_client.get_address_history(address)
                
                created_count = 0
                updated_count = 0
                
                for tx_data in transactions:
                    try:
                        txid = tx_data.get('txid')
                        if not txid:
                            continue
                        
                        # Use a savepoint to isolate each transaction operation
                        with self.env.cr.savepoint():
                            # Check if transaction already exists
                            existing_tx = self.search([('tx_hash', '=', txid)], limit=1)
                            
                            if existing_tx:
                                # Update existing transaction
                                existing_tx._update_from_blockchain_data(tx_data)
                                updated_count += 1
                            else:
                                # Create new transaction record
                                multisig_wallet = self.env.context.get('multisig_wallet')
                                wallet = self.env.context.get('wallet')
                                tx_vals = self._prepare_transaction_from_blockchain_data(tx_data, address, multisig_wallet, wallet)
                                new_tx = self.create(tx_vals)
                                # Create transaction lines for inputs and outputs
                                self._create_transaction_lines(new_tx, tx_data)
                                created_count += 1
                                
                    except Exception as tx_error:
                        _logger.warning(f"Failed to process transaction {txid}: {str(tx_error)}")
                        # Continue with other transactions
                        continue
                
                raw_count = len(transactions)
                _logger.info(f"Fetched transactions for {address}: {created_count} new, {updated_count} updated, {raw_count} raw transactions received")
                
                # If we got raw transactions but created/updated 0, there might be normalization issues
                if raw_count > 0 and (created_count + updated_count) == 0:
                    _logger.warning(f"Address {address}: Got {raw_count} raw transactions but processed 0 - possible normalization errors")
                
                # Clear the cache entry for this address after processing
                if hasattr(self.env, '_tx_fetch_cache') and cache_key in self.env._tx_fetch_cache:
                    del self.env._tx_fetch_cache[cache_key]
                
                return {
                    'created': created_count,
                    'updated': updated_count,
                    'total': raw_count  # Return the count of raw transactions received
                }
            
        except Exception as e:
            _logger.error(f"Failed to fetch transactions for address {address}: {str(e)}")
            raise ValidationError(f"Failed to fetch transactions: {str(e)}")

    @api.model
    def _prepare_transaction_from_blockchain_data(self, tx_data, related_address=None, multisig_wallet=None, wallet=None):
        """Prepare transaction creation values from blockchain data"""
        
        # Use the address-specific value calculated by Electrum parser
        # This represents only the amount relevant to the address we're importing for
        address_specific_value_sats = tx_data.get('value', 0)
        address_specific_value_btc = address_specific_value_sats / 100000000 if address_specific_value_sats > 0 else 0
        
        _logger.info(f"Transaction {tx_data.get('txid', 'unknown')[:16]}... - Address-specific value: {address_specific_value_sats} sats ({address_specific_value_btc} BTC)")
        
        # Sanity check - Bitcoin amounts should be reasonable for a single address
        if address_specific_value_btc > 21000000:  # More than total Bitcoin supply
            _logger.error(f"Invalid amount detected: {address_specific_value_btc} BTC - exceeds total Bitcoin supply")
            _logger.error(f"Raw tx_data: {tx_data}")
            raise ValidationError(f"Transaction {tx_data.get('txid', 'unknown')} has invalid amount: {address_specific_value_btc} BTC")
        
        # Determine transaction status
        status = 'confirmed' if tx_data.get('confirmations', 0) > 0 else 'pending'
        
        # Basic transaction data
        vals = {
            'tx_hash': tx_data.get('txid'),
            'size': tx_data.get('size', 0),
            'fee': (tx_data.get('fee', 0) / 100000000) if tx_data.get('fee') else 0,
            'amount': address_specific_value_btc,  # Required field - address-specific amount
            'status': status,  # Required field
            'notes': 'Imported from blockchain',  # Simplified notes
        }
        
        # Link to wallets if provided
        if multisig_wallet:
            vals['multisig_wallet_id'] = multisig_wallet.id
            _logger.info(f"Linking transaction {tx_data.get('txid', 'unknown')[:16]}... to multisig wallet {multisig_wallet.name}")
        elif wallet:
            vals['from_wallet_id'] = wallet.id
            _logger.info(f"Linking transaction {tx_data.get('txid', 'unknown')[:16]}... to wallet {wallet.name}")
        
        # Date from block time
        if tx_data.get('block_time'):
            from datetime import datetime
            import pytz
            
            # Bitcoin timestamps are in UTC
            utc_datetime = datetime.fromtimestamp(tx_data['block_time'], tz=pytz.UTC)
            # Convert to naive datetime for Odoo (Odoo expects naive datetime in UTC)
            vals['date'] = utc_datetime.replace(tzinfo=None)
            _logger.info(f"Transaction {tx_data.get('txid', 'unknown')[:16]}... - Block time: {tx_data['block_time']}, converted date: {vals['date']} UTC")
        else:
            # No fallbacks - if we can't get valid block time for confirmed transactions, fail
            height = tx_data.get('height', 0)
            if height > 0:
                # Confirmed transaction must have block time
                raise ValidationError(f"Transaction {tx_data.get('txid', 'unknown')} confirmed in block {height} but no block timestamp available")
            else:
                # Unconfirmed transactions don't have block time yet - leave date field unset
                _logger.info(f"Transaction {tx_data.get('txid', 'unknown')[:16]}... - Unconfirmed transaction, no date set")
        
        # Set block height (confirmations will be computed) 
        # Electrum uses 'height' field, not 'block_height'
        if tx_data.get('height') and tx_data['height'] > 0:
            vals['mined_block'] = tx_data['height']
            _logger.info(f"Transaction {tx_data.get('txid', 'unknown')[:16]}... - Block height: {tx_data['height']}")
        elif tx_data.get('block_height'):
            vals['mined_block'] = tx_data['block_height']
            _logger.info(f"Transaction {tx_data.get('txid', 'unknown')[:16]}... - Block height (alt): {tx_data['block_height']}")
        else:
            _logger.warning(f"Transaction {tx_data.get('txid', 'unknown')[:16]}... - No block height available")
        
        return vals

    @api.model
    def _create_transaction_lines(self, transaction, tx_data):
        """Create transaction lines (inputs/outputs) from blockchain data"""
        try:
            # Create output lines - handle both 'outputs' and 'vout' field names
            outputs = tx_data.get('outputs') or tx_data.get('vout', [])
            if outputs:
                _logger.info(f"Creating {len(outputs)} output lines for transaction {transaction.tx_hash}")
                for i, output in enumerate(outputs):
                    # Try to find matching address record, create if not found
                    address_record = None
                    # Handle different address field names from different sources
                    output_address = output.get('scriptpubkey_address') or output.get('address')
                    
                    if output_address:
                        address_record = self.env['crypto.bitcoin.address'].search([
                            ('address', '=', output_address)
                        ], limit=1)
                        if not address_record:
                            # Create address record for transaction tracking
                            address_record = self.env['crypto.bitcoin.address'].create({
                                'address': output_address,
                                'label': f'Discovered from transaction',
                                'type': 'external',
                                'used': True
                            })
                    
                    output_vals = {
                        'transaction_id': transaction.id,
                        'line_type': 'output',
                        'sequence': i + 1,
                        'amount': output.get('value', 0) / 100000000,  # Convert to BTC
                        'address_id': address_record.id if address_record else False,
                        'description': f"Output {i + 1}"
                    }
                    self.env['crypto.bitcoin.transaction.line'].create(output_vals)
            
            # Create input lines - handle both 'inputs' and 'vin' field names
            inputs = tx_data.get('inputs') or tx_data.get('vin', [])
            if inputs:
                _logger.info(f"Creating {len(inputs)} input lines for transaction {transaction.tx_hash}")
                for i, input_data in enumerate(inputs):
                    # For inputs, we have the previous transaction info
                    input_vals = {
                        'transaction_id': transaction.id,
                        'line_type': 'input',
                        'sequence': i + 1,
                        'prev_tx_hash': input_data.get('txid'),
                        'prev_output_index': input_data.get('vout'),
                        'amount': input_data.get('prevout', {}).get('value', 0) / 100000000,  # Convert to BTC
                        'description': f"Input {i + 1}"
                    }
                    self.env['crypto.bitcoin.transaction.line'].create(input_vals)
                    
        except Exception as e:
            _logger.warning(f"Failed to create transaction lines for {transaction.tx_hash}: {str(e)}")
            # Don't fail the entire transaction creation if lines fail
