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
        """Compute real-time confirmations using Bitcoin connector"""
        for record in self:
            if not record.mined_block:
                record.confirmations = 0
                continue
                
            try:
                # Get Bitcoin settings from config parameters
                use_local_node = self.env['ir.config_parameter'].sudo().get_param('bitcoin.use_local_node', True)
                
                if use_local_node:
                    # Use local Bitcoin node for real-time confirmations
                    connector = self.env['bitcoin.connector'].get_default_connector()
                    if connector:
                        record.confirmations = connector.get_transaction_confirmations(
                            record.tx_hash, record.mined_block
                        )
                    else:
                        record.confirmations = 0
                else:
                    # Fallback: estimate based on stored data (will be stale)
                    record.confirmations = 0
                    
            except Exception as e:
                _logger.warning(f"Failed to compute confirmations for {record.tx_hash}: {str(e)}")
                record.confirmations = 0

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
            # Get default transaction fetcher
            fetcher = self.env['crypto.bitcoin.transaction.fetcher'].get_default_fetcher()
            
            # Fetch transaction details
            tx_data = fetcher.fetch_transaction_details(self.tx_hash)
            
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
            update_vals['date'] = datetime.fromtimestamp(tx_data['block_time'])
        
        # Update confirmation status in notes
        if tx_data.get('confirmations'):
            confirmations = tx_data['confirmations']
            block_height = tx_data.get('block_height', 'Unknown')
            status_note = f"Confirmed in block {block_height} ({confirmations} confirmations)"
            
            if self.notes:
                update_vals['notes'] = f"{self.notes}\n\nBlockchain Status: {status_note}"
            else:
                update_vals['notes'] = f"Blockchain Status: {status_note}"
        
        if update_vals:
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
                
                # Get default transaction fetcher
                fetcher = self.env['crypto.bitcoin.transaction.fetcher'].get_default_fetcher(network)
                
                # Fetch transactions
                transactions = fetcher.fetch_address_transactions(address)
                
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
                                tx_vals = self._prepare_transaction_from_blockchain_data(tx_data, address, multisig_wallet)
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
    def _prepare_transaction_from_blockchain_data(self, tx_data, related_address=None, multisig_wallet=None):
        """Prepare transaction creation values from blockchain data"""
        
        # Calculate total output amount in BTC
        total_output = 0
        if tx_data.get('outputs'):
            for output in tx_data['outputs']:
                total_output += output.get('value', 0)
        total_output_btc = total_output / 100000000 if total_output > 0 else 0  # Convert satoshis to BTC
        
        # Debug logging for amount calculation
        outputs_count = len(tx_data.get('outputs', []))
        _logger.info(f"Transaction {tx_data.get('txid', 'unknown')[:16]}... - {outputs_count} outputs, total_output: {total_output} sats, total_output_btc: {total_output_btc}")
        if outputs_count > 0:
            _logger.info(f"First output sample: {tx_data['outputs'][0] if tx_data.get('outputs') else 'None'}")
        
        # Determine transaction status
        status = 'confirmed' if tx_data.get('confirmations', 0) > 0 else 'pending'
        
        # Basic transaction data
        vals = {
            'tx_hash': tx_data.get('txid'),
            'size': tx_data.get('size', 0),
            'fee': (tx_data.get('fee', 0) / 100000000) if tx_data.get('fee') else 0,
            'amount': total_output_btc,  # Required field
            'status': status,  # Required field
            'notes': 'Imported from blockchain',  # Simplified notes
        }
        
        # Link to multisig wallet if provided
        if multisig_wallet:
            vals['multisig_wallet_id'] = multisig_wallet.id
        
        # Date from block time
        if tx_data.get('block_time'):
            from datetime import datetime
            vals['date'] = datetime.fromtimestamp(tx_data['block_time'])
        
        # Set block height (confirmations will be computed)
        if tx_data.get('block_height'):
            vals['mined_block'] = tx_data['block_height']
        
        return vals

    @api.model
    def _create_transaction_lines(self, transaction, tx_data):
        """Create transaction lines (inputs/outputs) from blockchain data"""
        try:
            # Create output lines
            if tx_data.get('outputs'):
                for i, output in enumerate(tx_data['outputs']):
                    # Try to find matching address record, create if not found
                    address_record = None
                    if output.get('scriptpubkey_address'):
                        address_record = self.env['crypto.bitcoin.address'].search([
                            ('address', '=', output['scriptpubkey_address'])
                        ], limit=1)
                        if not address_record:
                            # Create address record for transaction tracking
                            address_record = self.env['crypto.bitcoin.address'].create({
                                'address': output['scriptpubkey_address'],
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
            
            # Create input lines
            if tx_data.get('inputs'):
                for i, input_data in enumerate(tx_data['inputs']):
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
