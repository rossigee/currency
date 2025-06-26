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
                                     string='Transaction', required=True)
    
    # Import methods
    import_method = fields.Selection([
        ('paste', 'Paste PSBT Text'),
        ('upload', 'Upload PSBT File')
    ], string='Import Method', required=True, default='paste')
    
    # PSBT data
    psbt_data = fields.Text(string='PSBT Data', 
                            help="Paste the signed PSBT in base64 format")
    psbt_file = fields.Binary(string='PSBT File', 
                              help="Upload a PSBT file")
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

    @api.depends('psbt_data', 'psbt_file', 'import_method')
    def _compute_psbt_validation(self):
        """Validate the imported PSBT"""
        for record in self:
            psbt_base64 = None
            
            try:
                # Get PSBT data based on import method
                if record.import_method == 'paste' and record.psbt_data:
                    psbt_base64 = record.psbt_data.strip()
                elif record.import_method == 'upload' and record.psbt_file:
                    # Decode the uploaded file
                    file_content = base64.b64decode(record.psbt_file)
                    # Assume the file content is already base64-encoded PSBT
                    psbt_base64 = file_content.decode('utf-8').strip()
                
                if not psbt_base64:
                    record.psbt_valid = False
                    record.validation_message = "No PSBT data provided"
                    record.signature_count = 0
                    record.is_complete = False
                    continue
                
                # Validate PSBT format (basic check)
                try:
                    decoded = base64.b64decode(psbt_base64)
                    # Basic validation - should be valid base64
                    record.psbt_valid = True
                except Exception:
                    record.psbt_valid = False
                    record.validation_message = "Invalid base64 format"
                    record.signature_count = 0
                    record.is_complete = False
                    continue
                
                # Use PSBT parsing utility to get signature info
                bip32_utils = self.env['crypto.bip32.utils']
                sig_info = bip32_utils.parse_psbt_signatures(psbt_base64)
                
                record.signature_count = sig_info['signature_count']
                record.is_complete = sig_info['is_complete']
                
                # Check if this PSBT has more signatures than the current one
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
                
            except Exception as e:
                _logger.warning(f"PSBT validation error: {str(e)}")
                record.psbt_valid = False
                record.validation_message = f"Validation error: {str(e)}"
                record.signature_count = 0
                record.is_complete = False

    def action_import_psbt(self):
        """Import the signed PSBT"""
        self.ensure_one()
        
        if not self.psbt_valid:
            raise ValidationError("Invalid PSBT data. Please check the format and try again.")
        
        # Get the PSBT data
        psbt_base64 = None
        if self.import_method == 'paste':
            psbt_base64 = self.psbt_data.strip()
        elif self.import_method == 'upload':
            file_content = base64.b64decode(self.psbt_file)
            psbt_base64 = file_content.decode('utf-8').strip()
        
        if not psbt_base64:
            raise ValidationError("No PSBT data to import")
        
        try:
            # Update the transaction with the new PSBT
            updates = {
                'psbt_base64': psbt_base64,
            }
            
            # Update status based on signature completeness
            if self.is_complete:
                updates['status'] = 'signed_psbt'
                # If fully signed, we could also set raw_transaction here
                # For now, we'll leave it to be set when the transaction is broadcast
            elif self.signature_count > 0:
                updates['status'] = 'partial_psbt'
            else:
                updates['status'] = 'unsigned_psbt'
            
            self.transaction_id.write(updates)
            
            # Return success notification
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'PSBT Imported Successfully',
                    'message': f'Updated transaction with {self.signature_count} signatures',
                    'type': 'success'
                }
            }
            
        except Exception as e:
            _logger.error(f"Failed to import PSBT: {str(e)}")
            raise ValidationError(f"PSBT import failed: {str(e)}")

    @api.onchange('import_method')
    def _onchange_import_method(self):
        """Clear data when switching import methods"""
        if self.import_method == 'paste':
            self.psbt_file = False
            self.psbt_filename = False
        else:
            self.psbt_data = False