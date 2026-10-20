# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class WizardCreatePrivateKey(models.TransientModel):
    _name = 'wizard.create.private.key'
    _description = 'Wizard to Create Bitcoin Private Key'

    name = fields.Char(string='Key Name', required=True, default="New Bitcoin Key")
    owner_id = fields.Many2one('res.partner', string='Owner')
    
    creation_method = fields.Selection([
        ('generate', 'Generate New Key'),
        ('import_mnemonic', 'Import from Mnemonic'),
        ('import_xprv', 'Import from XPRV')
    ], string='Creation Method', required=True, default='generate')
    
    # Import fields
    mnemonic_phrase = fields.Text(string='Mnemonic Phrase (24 words)', 
                                 help="Enter 24-word BIP39 mnemonic phrase")
    bip39_passphrase = fields.Char(string='BIP39 Passphrase (Optional)', 
                                  help="Optional 25th word for additional security")
    xprv_key = fields.Char(string='Extended Private Key', 
                          help="Extended private key starting with 'xprv'")
    
    # Generation options
    word_count = fields.Selection([
        ('12', '12 words'),
        ('24', '24 words')
    ], string='Mnemonic Length', default='24')
    
    # Results (shown after creation)
    created_private_key_id = fields.Many2one('crypto.bitcoin.private.key', string='Created Private Key', readonly=True)
    generated_mnemonic = fields.Text(string='Generated Mnemonic', readonly=True,
                                   help="IMPORTANT: Write this down and store securely!")
    success_message = fields.Text(string='Success Message', readonly=True)

    @api.onchange('creation_method')
    def _onchange_creation_method(self):
        """Clear fields when switching methods"""
        self.mnemonic_phrase = False
        self.bip39_passphrase = False
        self.xprv_key = False

    def _validate_mnemonic_input(self):
        """Validate mnemonic phrase input"""
        if not self.mnemonic_phrase:
            raise ValidationError("Mnemonic phrase is required")
            
        words = self.mnemonic_phrase.strip().split()
        if len(words) not in [12, 15, 18, 21, 24]:
            raise ValidationError(f"Mnemonic must be 12, 15, 18, 21, or 24 words. Found {len(words)} words.")
            
        # Basic word validation
        for word in words:
            if not word.isalpha() or len(word) < 3:
                raise ValidationError(f"Invalid word: '{word}'. Words must be alphabetic and at least 3 characters.")

    def _validate_xprv_input(self):
        """Validate XPRV input"""
        if not self.xprv_key:
            raise ValidationError("Extended private key is required")
            
        if not self.xprv_key.startswith('xprv'):
            raise ValidationError("Extended private key must start with 'xprv'")
            
        # Additional validation would be done in the model

    def action_create_private_key(self):
        """Create the private key based on selected method"""
        self.ensure_one()
        
        try:
            # Prepare creation values
            vals = {
                'name': self.name,
                'owner_id': self.owner_id.id if self.owner_id else False,
            }
            
            if self.creation_method == 'generate':
                vals.update({
                    'key_source': 'generated',
                })
                
            elif self.creation_method == 'import_mnemonic':
                self._validate_mnemonic_input()
                vals.update({
                    'key_source': 'mnemonic',
                    'mnemonic': self.mnemonic_phrase,
                    'passphrase': self.bip39_passphrase or "",
                })
                
            elif self.creation_method == 'import_xprv':
                self._validate_xprv_input()
                vals.update({
                    'key_source': 'xprv',
                    'xprv': self.xprv_key,
                })
            
            # Create the private key
            private_key = self.env['crypto.bitcoin.private.key'].create(vals)
            
            # Store reference and prepare success message
            self.created_private_key_id = private_key.id
            
            # For generated keys, show the mnemonic
            if self.creation_method == 'generate':
                # Retrieve the generated mnemonic from vault
                try:
                    vault_data = self.env['vault.connector'].get_secret(private_key.token_uuid)
                    if vault_data and vault_data.get('mnemonic'):
                        self.generated_mnemonic = vault_data['mnemonic']
                except Exception as e:
                    _logger.warning(f"Could not retrieve generated mnemonic: {str(e)}")
                self.success_message = "✅ Private key created successfully!"
            else:
                self.success_message = f"✅ Private key imported successfully from {self.creation_method.replace('_', ' ')}!"
            
            # Return action to show results
            return {
                'type': 'ir.actions.act_window',
                'name': 'Private Key Created',
                'res_model': 'wizard.create.private.key',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'context': {'show_results': True}
            }
            
        except Exception as e:
            raise ValidationError(f"Failed to create private key: {str(e)}")

    def action_create_public_key(self):
        """Create a public key from the created private key"""
        self.ensure_one()
        
        if not self.created_private_key_id:
            raise ValidationError("No private key created yet")
            
        return self.created_private_key_id.action_create_public_key()

    def action_view_private_key(self):
        """View the created private key"""
        self.ensure_one()
        
        if not self.created_private_key_id:
            raise ValidationError("No private key created yet")
            
        return {
            'type': 'ir.actions.act_window',
            'name': 'Private Key',
            'res_model': 'crypto.bitcoin.private.key',
            'res_id': self.created_private_key_id.id,
            'view_mode': 'form',
            'target': 'current',
        }