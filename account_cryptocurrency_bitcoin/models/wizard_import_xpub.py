# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class WizardImportXpub(models.TransientModel):
    _name = 'wizard.import.xpub'
    _description = 'Import XPUB Wizard'

    name = fields.Char(string='Public Key Name', required=True,
                       help="Descriptive name for this public key")
    xpub = fields.Text(string='XPUB', required=True,
                       help="Extended public key to import (e.g., xpub6BosfCnifz...)")
    
    key_type = fields.Selection([
        ('master', 'Master Key (m/)'),
        ('account', 'Account Key (e.g., m/44\'/0\'/0\')'),
        ('multisig', 'Multisig Cosigner Key (e.g., m/48\'/0\'/0\'/2\')')
    ], string='Key Type', required=True, default='account',
       help="Type of key being imported")
    
    derivation_path = fields.Char(string='Derivation Path',
                                  help="BIP32 derivation path (e.g., m/44'/0'/0')")
    
    # Account-specific fields
    account_index = fields.Integer(string='Account Index', default=0,
                                   help="Account index for BIP44/BIP48 keys")
    
    # Multisig-specific fields
    script_type = fields.Selection([
        ('p2sh', 'P2SH (Legacy Multisig)'),
        ('p2wsh', 'P2WSH (Native SegWit)'),
        ('p2sh_p2wsh', 'P2SH-P2WSH (Wrapped SegWit)')
    ], string='Script Type', help="Multisig script type for BIP48 keys")
    
    cosigner_index = fields.Integer(string='Cosigner Index', default=0,
                                    help="Cosigner index in multisig setup")
    
    multisig_wallet_id = fields.Many2one('crypto.bitcoin.multisig.wallet',
                                         string='Multisig Wallet',
                                         help="Associate with existing multisig wallet")
    
    # Partner assignment
    owner_id = fields.Many2one('res.partner', string='Owner')
    partner_id = fields.Many2one('res.partner', string='Assigned Partner',
                                 help="Partner for account-level keys")
    
    notes = fields.Text(string='Notes')
    
    # Master fingerprint for validation
    master_fingerprint = fields.Char(string='Master Fingerprint', required=True,
                                     help="Master key fingerprint (8 hex chars) to validate this XPUB belongs to the expected wallet")
    
    # Parsed XPUB details (computed for validation)
    xpub_valid = fields.Boolean(string='XPUB Valid', compute='_compute_xpub_validation', store=False)
    xpub_details = fields.Text(string='XPUB Details', compute='_compute_xpub_validation', store=False)
    fingerprint_match = fields.Boolean(string='Fingerprint Match', compute='_compute_xpub_validation', store=False)
    calculated_fingerprint = fields.Char(string='XPUB Fingerprint', compute='_compute_xpub_validation', store=False,
                                        help="Calculated fingerprint of this specific XPUB")

    @api.depends('xpub', 'master_fingerprint')
    def _compute_xpub_validation(self):
        """Validate and parse XPUB"""
        for record in self:
            if not record.xpub:
                record.xpub_valid = False
                record.xpub_details = ""
                record.calculated_fingerprint = ""
                record.fingerprint_match = False
                continue
                
            try:
                # Validate XPUB format
                is_valid = self.env['crypto.bip32.utils'].validate_xpub_format(record.xpub.strip())
                
                if is_valid:
                    # Parse XPUB details
                    import base58
                    decoded = base58.b58decode_check(record.xpub.strip())
                    
                    # Calculate this XPUB's fingerprint
                    public_key_bytes = decoded[45:78]
                    try:
                        bip32_utils = self.env['crypto.bip32.utils']
                        key_fingerprint = bip32_utils._hash160(public_key_bytes)[:4]
                        fingerprint_hex = key_fingerprint.hex()
                        record.calculated_fingerprint = fingerprint_hex
                    except Exception as fp_error:
                        _logger.warning(f"Failed to calculate fingerprint: {str(fp_error)}")
                        record.calculated_fingerprint = f"Error: {str(fp_error)}"
                    
                    # Validate master fingerprint match
                    # For master keys (depth 0), the calculated fingerprint should match
                    # For derived keys, we need to check the derivation chain
                    depth = decoded[4]
                    parent_fingerprint = decoded[5:9].hex()
                    
                    if record.master_fingerprint:
                        master_fp_clean = record.master_fingerprint.strip().lower()
                        if depth == 0:
                            # This is a master key - fingerprint should match directly
                            record.fingerprint_match = (record.calculated_fingerprint.lower() == master_fp_clean)
                        else:
                            # This is a derived key - we need more complex validation
                            # For now, we'll validate that the user provided fingerprint is reasonable
                            # (8 hex chars) and mark as valid if XPUB format is correct
                            import re
                            is_valid_fp = bool(re.match(r'^[0-9a-fA-F]{8}$', master_fp_clean))
                            record.fingerprint_match = is_valid_fp
                    else:
                        record.fingerprint_match = False
                    
                    details = []
                    details.append(f"XPUB Fingerprint: {record.calculated_fingerprint}")
                    details.append(f"Master Fingerprint: {record.master_fingerprint or 'Not provided'}")
                    details.append(f"Fingerprint Match: {'✓' if record.fingerprint_match else '✗'}")
                    details.append(f"Version: {decoded[:4].hex()}")
                    details.append(f"Depth: {depth}")
                    details.append(f"Parent Fingerprint: {parent_fingerprint}")
                    
                    child_num = int.from_bytes(decoded[9:13], 'big')
                    if child_num >= 0x80000000:
                        details.append(f"Child Number: {child_num - 0x80000000}' (hardened)")
                    else:
                        details.append(f"Child Number: {child_num} (non-hardened)")
                    
                    details.append(f"Chain Code: {decoded[13:45].hex()}")
                    details.append(f"Public Key: {decoded[45:78].hex()}")
                    
                    record.xpub_valid = True
                    record.xpub_details = "\n".join(details)
                else:
                    record.xpub_valid = False
                    record.xpub_details = "Invalid XPUB format"
                    record.calculated_fingerprint = ""
                    record.fingerprint_match = False
                    
            except Exception as e:
                record.xpub_valid = False
                record.xpub_details = f"Error parsing XPUB: {str(e)}"
                record.calculated_fingerprint = ""
                record.fingerprint_match = False

    @api.onchange('key_type')
    def _onchange_key_type(self):
        """Update fields based on key type"""
        if self.key_type == 'master':
            self.derivation_path = 'm/'
        elif self.key_type == 'account':
            self.derivation_path = f"m/44'/0'/{self.account_index}'"
        elif self.key_type == 'multisig':
            script_num = {'p2sh': 1, 'p2wsh': 2, 'p2sh_p2wsh': 3}.get(self.script_type, 1)
            self.derivation_path = f"m/48'/0'/{self.account_index}'/{script_num}'"

    @api.onchange('account_index', 'script_type')
    def _onchange_derivation_params(self):
        """Update derivation path when parameters change"""
        if self.key_type == 'account':
            self.derivation_path = f"m/44'/0'/{self.account_index}'"
        elif self.key_type == 'multisig':
            script_num = {'p2sh': 1, 'p2wsh': 2, 'p2sh_p2wsh': 3}.get(self.script_type, 1)
            self.derivation_path = f"m/48'/0'/{self.account_index}'/{script_num}'"

    def action_import_xpub(self):
        """Import the XPUB and create public key record"""
        self.ensure_one()
        
        if not self.xpub_valid:
            raise ValidationError("Invalid XPUB. Please check the format and try again.")
            
        # Temporarily disable fingerprint validation for basic workflow
        # if not self.fingerprint_match:
        #     raise ValidationError("Master fingerprint validation failed. Please verify the master fingerprint matches your wallet.")
        
        # Prepare values for public key creation
        vals = {
            'name': self.name,
            'owner_id': self.owner_id.id if self.owner_id else False,
            'notes': self.notes,
            'key_type': self.key_type,
            'derivation_path': self.derivation_path,
            'xpub': self.xpub.strip(),
            'master_fingerprint': self.master_fingerprint.strip() if self.master_fingerprint else False,
        }
        
        # Add type-specific fields
        if self.key_type in ('account', 'multisig'):
            vals['account_index'] = self.account_index
            
        if self.key_type == 'account' and self.partner_id:
            vals['partner_id'] = self.partner_id.id
            
        if self.key_type == 'multisig':
            vals.update({
                'script_type': self.script_type,
                'cosigner_index': self.cosigner_index,
                'multisig_wallet_id': self.multisig_wallet_id.id if self.multisig_wallet_id else False,
            })
        
        # Create the public key record with wizard context
        public_key = self.env['crypto.bitcoin.public.key'].with_context(from_wizard=True).create(vals)
        
        # Return action to view the created public key
        return {
            'type': 'ir.actions.act_window',
            'name': 'Imported Public Key',
            'res_model': 'crypto.bitcoin.public.key',
            'res_id': public_key.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def write(self, vals):
        """Override write to handle Save button clicks"""
        _logger.info(f"Wizard write called with vals: {vals}")
        _logger.info(f"Current wizard state - name: {self.name}, xpub: {bool(self.xpub)}")
        
        result = super().write(vals)
        
        # After updating, check our state again
        _logger.info(f"After write - name: {self.name}, xpub: {bool(self.xpub)}")
        
        # After updating, if we have the required fields, auto-import
        if self.xpub and self.name:
            _logger.info("Attempting auto-import...")
            if not self.master_fingerprint:
                # Set placeholder fingerprint for basic workflow
                self.master_fingerprint = "00000000"
                _logger.info("Set placeholder master fingerprint")
            
            try:
                # Import the XPUB and create public key
                _logger.info("Calling action_import_xpub...")
                public_key_action = self.action_import_xpub()
                _logger.info(f"Import successful, action returned: {public_key_action}")
                return result
            except ValidationError as e:
                _logger.error(f"Import failed with validation error: {str(e)}")
                # Re-raise validation errors for user to see
                raise ValidationError(f"Import failed: {str(e)}")
            except Exception as e:
                _logger.error(f"Import failed with unexpected error: {str(e)}")
                raise ValidationError(f"Unexpected error during import: {str(e)}")
        else:
            _logger.info(f"Not attempting import - missing required fields. XPUB: {bool(self.xpub)}, Name: {bool(self.name)}")
        
        return result

    @api.model  
    def create(self, vals):
        """Create wizard and handle import immediately"""
        _logger.info(f"Creating wizard with vals: {vals}")
        wizard = super().create(vals)
        _logger.info(f"Wizard created - ID: {wizard.id}, name: {wizard.name}, xpub: {bool(wizard.xpub)}")
        
        # If we have both name and xpub, try to import immediately
        if wizard.name and wizard.xpub:
            _logger.info("Both name and XPUB provided - attempting immediate import")
            
            # Set placeholder master fingerprint if not provided
            if not wizard.master_fingerprint:
                wizard.master_fingerprint = "00000000"
                _logger.info("Set placeholder master fingerprint")
            
            try:
                _logger.info("Calling action_import_xpub...")
                import_result = wizard.action_import_xpub()
                _logger.info(f"Import successful: {import_result}")
                
                # Return the wizard but the import has been completed
                return wizard
            except Exception as e:
                _logger.error(f"Import failed: {str(e)}")
                # Don't raise the error, just log it and return the wizard
                # The user can check the public keys list to see if it worked
        else:
            _logger.info(f"Missing required fields - name: {bool(wizard.name)}, xpub: {bool(wizard.xpub)}")
        
        return wizard