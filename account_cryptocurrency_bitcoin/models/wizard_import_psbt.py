# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import base64
import logging

_logger = logging.getLogger(__name__)


class WizardImportPsbt(models.TransientModel):
    _name = 'wizard.import.psbt'
    _description = 'Import Signed PSBT Wizard'

    transaction_id = fields.Many2one('crypto.bitcoin.transaction', 
                                     string='Transaction', required=False,
                                     help="Optional: Select an existing transaction to update")
    
    # Import method (upload only)
    import_method = fields.Selection([
        ('upload', 'Upload PSBT File')
    ], string='Import Method', required=True, default='upload')
    
    # PSBT data
    psbt_file = fields.Binary(string='PSBT File', required=True,
                              help="Upload a binary PSBT file (.psbt)")
    psbt_filename = fields.Char(string='Filename')
    
    # Validation fields
    psbt_valid = fields.Boolean(string='PSBT Valid', 
                                compute='_compute_psbt_validation', store=False)
    validation_message = fields.Text(string='Validation Result', 
                                     compute='_compute_psbt_validation', store=False)
    signature_count = fields.Integer(string='Signatures Found', 
                                     compute='_compute_psbt_validation', store=False)
    is_complete = fields.Boolean(string='Fully Signed', 
                                 compute='_compute_psbt_validation', store=False)

    @api.depends('psbt_file')
    def _compute_psbt_validation(self):
        """Validate the imported PSBT"""
        for record in self:
            psbt_base64 = None
            
            try:
                # Get PSBT data from uploaded file
                if record.psbt_file:
                    # Decode the uploaded file (Odoo stores binary files as base64)
                    file_content = base64.b64decode(record.psbt_file)
                    # PSBT files are binary, so we need to encode them to base64 for storage
                    psbt_base64 = base64.b64encode(file_content).decode('ascii')
                
                if not psbt_base64:
                    record.psbt_valid = False
                    record.validation_message = "No PSBT data provided"
                    record.signature_count = 0
                    record.is_complete = False
                    continue
                
                # Validate PSBT format (proper PSBT validation)
                try:
                    decoded = base64.b64decode(psbt_base64)
                    
                    # Check for PSBT magic bytes at the start
                    if not decoded.startswith(b'psbt\xff'):
                        record.psbt_valid = False
                        record.validation_message = "Not a valid PSBT file (missing magic bytes). This appears to be a different file format."
                        record.signature_count = 0
                        record.is_complete = False
                        continue
                    
                    # Try to parse with embit to validate structure
                    from embit import psbt
                    psbt_obj = psbt.PSBT.parse(decoded)
                    
                    # Basic validation - should have a transaction
                    if not hasattr(psbt_obj, 'tx') or not psbt_obj.tx:
                        record.psbt_valid = False
                        record.validation_message = "Invalid PSBT: missing transaction data"
                        record.signature_count = 0
                        record.is_complete = False
                        continue
                    
                    record.psbt_valid = True
                    
                except Exception as e:
                    record.psbt_valid = False
                    if "magic bytes" in str(e).lower() or "psbt" in str(e).lower():
                        record.validation_message = f"Not a valid PSBT file: {str(e)}"
                    else:
                        record.validation_message = f"File validation error: {str(e)}"
                    record.signature_count = 0
                    record.is_complete = False
                    continue
                
                # Use PSBT parsing utility to get signature info
                bip32_utils = self.env['crypto.bip32.utils']
                sig_info = bip32_utils.parse_psbt_signatures(psbt_base64)
                
                record.signature_count = sig_info['signature_count']
                record.is_complete = sig_info['is_complete']
                
                # Check signature status
                if record.transaction_id:
                    # Comparing with existing transaction
                    current_sigs = record.transaction_id.current_signatures
                    required_sigs = record.transaction_id.required_signatures
                    
                    if record.signature_count > current_sigs:
                        if record.is_complete or record.signature_count >= required_sigs:
                            record.validation_message = f"✅ PSBT is fully signed ({record.signature_count}/{required_sigs} signatures)"
                        else:
                            record.validation_message = f"✅ PSBT has {record.signature_count}/{required_sigs} signatures (current: {current_sigs})"
                    elif record.signature_count == current_sigs:
                        record.validation_message = f"ℹ️ PSBT has same number of signatures as current ({record.signature_count}/{required_sigs})"
                    else:
                        record.validation_message = f"⚠️ PSBT has fewer signatures than current ({record.signature_count} vs {current_sigs})"
                else:
                    # Standalone PSBT import
                    if record.is_complete:
                        record.validation_message = f"✅ PSBT is fully signed ({record.signature_count} signatures)"
                    elif record.signature_count > 0:
                        record.validation_message = f"✅ PSBT has {record.signature_count} partial signatures"
                    else:
                        record.validation_message = "✅ PSBT is valid but unsigned"
                
            except Exception as e:
                _logger.warning(f"PSBT validation error: {str(e)}")
                record.psbt_valid = False
                record.validation_message = f"Validation error: {str(e)}"
                record.signature_count = 0
                record.is_complete = False

    def default_get(self, fields_list):
        """Set default transaction_id from context if coming from a transaction"""
        res = super().default_get(fields_list)
        if self.env.context.get('default_transaction_id'):
            res['transaction_id'] = self.env.context.get('default_transaction_id')
        return res


    def action_import_psbt(self):
        """Import the signed PSBT"""
        self.ensure_one()
        
        if not self.psbt_valid:
            raise ValidationError("Invalid PSBT data. Please check the format and try again.")
        
        # Get the PSBT data from uploaded file
        if not self.psbt_file:
            raise ValidationError("No PSBT file uploaded")
            
        file_content = base64.b64decode(self.psbt_file)
        psbt_base64 = base64.b64encode(file_content).decode('ascii')
        
        if not psbt_base64:
            raise ValidationError("No PSBT data to import")
        
        try:
            if self.transaction_id:
                # Update existing transaction
                updates = {
                    'psbt_base64': psbt_base64,
                }
                
                # Update status based on signature completeness
                if self.is_complete:
                    updates['status'] = 'signed_psbt'
                elif self.signature_count > 0:
                    updates['status'] = 'partial_psbt'
                else:
                    updates['status'] = 'unsigned_psbt'
                
                self.transaction_id.write(updates)
                transaction = self.transaction_id
                message = f'Updated transaction with {self.signature_count} signatures'
                
            else:
                # Create new transaction from PSBT
                _logger.info("Creating new transaction from imported PSBT")
                
                # Try to parse PSBT to extract transaction details
                bip32_utils = self.env['crypto.bip32.utils']
                psbt_info = bip32_utils.parse_psbt_transaction_info(psbt_base64)
                
                _logger.info(f"Parsed PSBT info: {psbt_info}")
                
                # Determine status
                if self.is_complete:
                    status = 'signed_psbt'
                elif self.signature_count > 0:
                    status = 'partial_psbt'
                else:
                    status = 'unsigned_psbt'
                
                _logger.info(f"Creating transaction with status: {status}")
                
                # Create transaction record
                transaction_data = {
                    'date': fields.Datetime.now(),
                    'tx_hash': '[Imported]',  # Placeholder for imported PSBTs
                    'notes': 'Imported from external PSBT',
                    'amount': psbt_info.get('total_output', 0) / 100000000,  # Convert to BTC
                    'fee': psbt_info.get('fee', 0) / 100000000,  # Convert to BTC
                    'status': status,
                    'psbt_base64': psbt_base64,
                    'required_signatures': psbt_info.get('required_signatures', 1),
                    'created_by_id': self.env.user.partner_id.id,
                }
                
                _logger.info(f"Creating transaction with data: {transaction_data}")
                transaction = self.env['crypto.bitcoin.transaction'].create(transaction_data)
                _logger.info(f"Created transaction with ID: {transaction.id}")
                
                # Create transaction lines for outputs if available
                outputs = psbt_info.get('outputs', [])
                _logger.info(f"Creating {len(outputs)} transaction lines")
                _logger.info(f"Outputs data: {outputs}")
                
                # If no outputs were parsed, create a test one to debug
                if not outputs:
                    _logger.warning("No outputs found in PSBT, creating test address to verify address creation")
                    test_address_record = self._get_or_create_address("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")
                    if test_address_record:
                        _logger.info(f"Test address created successfully: {test_address_record.id}")
                    else:
                        _logger.error("Test address creation failed")
                
                for i, output in enumerate(outputs, 1):
                    address_str = output.get('address', '')
                    _logger.info(f"Processing output {i}: address='{address_str}', amount={output.get('amount', 0)}")
                    
                    # Create or find the bitcoin address record
                    address_record = None
                    if address_str and not address_str.startswith('['):
                        # Only create address records for valid addresses (not error placeholders)
                        _logger.info(f"Creating address record for: {address_str}")
                        address_record = self._get_or_create_address(address_str)
                        if address_record:
                            _logger.info(f"Successfully created/found address record ID: {address_record.id}")
                        else:
                            _logger.error(f"Failed to create address record for: {address_str}")
                    else:
                        _logger.warning(f"Skipping address creation for invalid address: {address_str}")
                    
                    line_data = {
                        'transaction_id': transaction.id,
                        'line_type': 'output',
                        'address_id': address_record.id if address_record else False,
                        'amount': output.get('amount', 0) / 100000000,  # Convert to BTC
                        'sequence': i,
                        'description': f'Imported Output {i}',
                    }
                    _logger.info(f"Creating transaction line {i}: {line_data}")
                    line = self.env['crypto.bitcoin.transaction.line'].create(line_data)
                    _logger.info(f"Created transaction line with ID: {line.id}")
                    
                    if address_record:
                        _logger.info(f"Transaction line associated with address record ID: {address_record.id}")
                    else:
                        _logger.warning(f"Transaction line created without address record")
                
                message = f'Created new transaction from PSBT with {self.signature_count} signatures'
            
            # Return action to view the transaction
            return {
                'type': 'ir.actions.act_window',
                'name': 'Imported Transaction',
                'res_model': 'crypto.bitcoin.transaction',
                'res_id': transaction.id,
                'view_mode': 'form',
                'target': 'current',
            }
            
        except Exception as e:
            _logger.error(f"Failed to import PSBT: {str(e)}")
            raise ValidationError(f"PSBT import failed: {str(e)}")

    def _get_or_create_address(self, address_str):
        """
        Get or create a crypto.bitcoin.address record for the given address
        
        Args:
            address_str (str): Bitcoin address string
            
        Returns:
            crypto.bitcoin.address: Address record
        """
        try:
            _logger.info(f"_get_or_create_address called with: '{address_str}'")
            
            if not address_str:
                _logger.warning("Empty address string provided")
                return None
                
            # Check if address already exists
            existing_address = self.env['crypto.bitcoin.address'].search([
                ('address', '=', address_str)
            ], limit=1)
            
            if existing_address:
                _logger.info(f"Found existing address record for {address_str} with ID: {existing_address.id}")
                return existing_address
            
            # Create new address record with minimal required fields
            address_data = {
                'address': address_str,
                'type': 'receive',  # Default for imported addresses
                'notes': 'Imported from PSBT',
            }
            
            _logger.info(f"Creating address record for: {address_str}")
            
            _logger.info(f"Creating address record with data: {address_data}")
            address_record = self.env['crypto.bitcoin.address'].create(address_data)
            _logger.info(f"Successfully created new address record for {address_str} with ID: {address_record.id}")
            
            # Verify the record was created
            if address_record and address_record.id:
                _logger.info(f"Address record verification: ID={address_record.id}, address='{address_record.address}'")
                return address_record
            else:
                _logger.error(f"Address record creation failed - no ID assigned")
                return None
            
        except Exception as e:
            _logger.error(f"Exception in _get_or_create_address for {address_str}: {str(e)}", exc_info=True)
            return None

