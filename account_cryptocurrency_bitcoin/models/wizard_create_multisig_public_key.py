# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class WizardCreateMultisigPublicKey(models.TransientModel):
    _name = 'wizard.create.multisig.public.key'
    _description = 'Wizard to Create Cosigner Key'
    
    @api.model
    def create(self, vals):
        """Override create to ensure private_key_id from context"""
        # Apply default from context if missing
        if 'private_key_id' not in vals and 'default_private_key_id' in self.env.context:
            vals['private_key_id'] = self.env.context['default_private_key_id']
        
        # Create the wizard record (don't auto-execute)
        wizard = super().create(vals)
        
        return wizard

    def write(self, vals):
        """Override write to auto-execute creation when form is saved"""
        result = super().write(vals)
        
        # Auto-execute creation only if we have all required fields and no existing public key
        if (not self.created_public_key_id and 
            self.private_key_id and 
            self.script_type and 
            self.account_index is not False and 
            self.cosigner_index is not False):
            self._execute_multisig_creation()
            
        return result

    # Source private key
    private_key_id = fields.Many2one('crypto.bitcoin.private.key', string='Private Key', 
                                   required=True, readonly=True)
    private_key_name = fields.Char(related='private_key_id.name', readonly=True)
    
    # Multisig details
    account_index = fields.Integer(string='Account Index', required=True, default=0,
                                 help="BIP48 account index (0-2147483647). Each account needs a unique index.")
    script_type = fields.Selection([
        ('p2sh', 'P2SH (Legacy)'),
        ('p2wsh', 'P2WSH (Native SegWit)'),
        ('p2sh_p2wsh', 'P2SH-P2WSH (Wrapped SegWit)')
    ], string='Script Type', required=True, default='p2wsh',
       help="Multisig script type for BIP48 derivation")
    cosigner_index = fields.Integer(string='Cosigner Index', required=True, default=0,
                                  help="Index of this cosigner in the multisig setup (0-based)")
    
    # Wallet assignment
    multisig_wallet_id = fields.Many2one('crypto.bitcoin.multisig.wallet', 
                                       string='Assign to Multisig Wallet',
                                       help="Optional: Assign this key to a specific multisig wallet")
    name_suffix = fields.Char(string='Name Suffix', 
                             help="Optional custom suffix for the public key name")
    
    # Management
    suggest_next_account = fields.Boolean(string='Auto-suggest Next Account', default=True,
                                        help="Automatically suggest the next available account index")
    next_available_account = fields.Integer(string='Next Available Account', compute='_compute_next_account')
    existing_multisig_keys = fields.Text(string='Existing Multisig Keys', compute='_compute_existing_keys')
    
    # Derivation preview
    derivation_path = fields.Char(string='Derivation Path', compute='_compute_derivation_info')
    
    # Options
    notes = fields.Text(string='Notes', help="Optional notes about this cosigner key")
    create_sample_addresses = fields.Boolean(string='Generate Sample Addresses', default=True,
                                           help="Generate a few sample addresses to verify derivation")
    sample_address_count = fields.Integer(string='Sample Address Count', default=3)
    
    # Results (shown after creation)
    created_public_key_id = fields.Many2one('crypto.bitcoin.public.key', string='Created Public Key', readonly=True)
    derived_xpub = fields.Char(string='Derived XPUB', readonly=True)
    sample_addresses = fields.Text(string='Sample Addresses', readonly=True)
    success_message = fields.Text(string='Success Message', readonly=True)

    @api.onchange('suggest_next_account', 'private_key_id', 'script_type', 'cosigner_index')
    def _onchange_suggest_account(self):
        """Auto-fill account index when auto-suggest is enabled"""
        if self.suggest_next_account and self.private_key_id:
            self.account_index = self.next_available_account

    @api.depends('private_key_id', 'script_type', 'cosigner_index')
    def _compute_next_account(self):
        """Compute the next available account index for this script type and cosigner"""
        for record in self:
            if record.private_key_id and record.script_type is not False:
                # Find highest used account index for this script type and cosigner
                existing_keys = self.env['crypto.bitcoin.public.key'].search([
                    ('private_key_id', '=', record.private_key_id.id),
                    ('key_type', '=', 'multisig'),
                    ('script_type', '=', record.script_type),
                    ('cosigner_index', '=', record.cosigner_index)
                ], order='account_index desc', limit=1)
                
                if existing_keys:
                    record.next_available_account = existing_keys.account_index + 1
                else:
                    record.next_available_account = 0
            else:
                record.next_available_account = 0

    @api.depends('private_key_id')
    def _compute_existing_keys(self):
        """Show existing multisig key assignments"""
        for record in self:
            if record.private_key_id:
                existing = self.env['crypto.bitcoin.public.key'].search([
                    ('private_key_id', '=', record.private_key_id.id),
                    ('key_type', '=', 'multisig')
                ], order='account_index, script_type, cosigner_index')
                
                if existing:
                    lines = []
                    for key in existing:
                        script_name = dict(key._fields['script_type'].selection).get(key.script_type, key.script_type)
                        wallet_info = f" → {key.multisig_wallet_id.name}" if key.multisig_wallet_id else ""
                        lines.append(f"Account {key.account_index} {script_name} Cosigner {key.cosigner_index}: {key.name}{wallet_info}")
                    record.existing_multisig_keys = "\n".join(lines)
                else:
                    record.existing_multisig_keys = "No multisig keys created yet"
            else:
                record.existing_multisig_keys = ""

    @api.depends('account_index', 'script_type')
    def _compute_derivation_info(self):
        """Compute derivation path preview"""
        for record in self:
            if record.account_index is not False and record.script_type:
                # Map script types to BIP48 numbers
                script_type_map = {'p2sh': 1, 'p2wsh': 2, 'p2sh_p2wsh': 3}
                script_num = script_type_map.get(record.script_type, '?')
                record.derivation_path = f"m/48'/0'/{record.account_index}'/{script_num}'"
            else:
                record.derivation_path = ""

    def _validate_inputs(self):
        """Validate wizard inputs"""
        # Validate account index range
        if self.account_index < 0 or self.account_index > 2147483647:
            raise ValidationError("Account index must be between 0 and 2147483647")
            
        # Validate cosigner index range
        if self.cosigner_index < 0 or self.cosigner_index > 99:
            raise ValidationError("Cosigner index must be between 0 and 99")
            
        # Check for duplicate multisig key  
        _logger.info(f"Validating multisig key: account={self.account_index}, script_type={self.script_type}, cosigner={self.cosigner_index}")
        
        existing_key = self.env['crypto.bitcoin.public.key'].search([
            ('private_key_id', '=', self.private_key_id.id),
            ('key_type', '=', 'multisig'),
            ('account_index', '=', self.account_index),
            ('script_type', '=', self.script_type),
            ('cosigner_index', '=', self.cosigner_index)
        ])
        if existing_key:
            script_name = dict(self._fields['script_type'].selection).get(self.script_type, self.script_type)
            _logger.warning(f"Found existing key: {existing_key.name} with script_type={existing_key.script_type}")
            raise ValidationError(f"Multisig key for account {self.account_index}, {script_name}, cosigner {self.cosigner_index} already exists: {existing_key.name}")

    def _execute_multisig_creation(self):
        """Execute the multisig public key creation (called automatically on save)"""
        self.ensure_one()
        
        try:
            self._validate_inputs()
            
            # Create multisig public key using private key method
            multisig_public_key = self.private_key_id.create_multisig_public_key(
                account_index=self.account_index,
                script_type=self.script_type,
                cosigner_index=self.cosigner_index,
                multisig_wallet_id=self.multisig_wallet_id.id if self.multisig_wallet_id else None,
                name_suffix=self.name_suffix
            )
            
            # Add notes if provided
            if self.notes:
                multisig_public_key.notes = self.notes
                
            # Store reference for display
            self.created_public_key_id = multisig_public_key.id
            self.derived_xpub = multisig_public_key.xpub
            
            # Generate sample addresses if requested
            if self.create_sample_addresses and self.sample_address_count > 0:
                self._generate_sample_addresses()
            
            # Prepare success message
            self._prepare_success_message()
            
            _logger.info(f"Multisig public key creation completed successfully")
            
        except ValidationError as e:
            _logger.error(f"Validation error in multisig public key creation: {str(e)}")
            raise
        except Exception as e:
            _logger.error(f"Unexpected error in multisig public key creation: {str(e)}")
            raise ValidationError(f"Failed to create multisig public key: {str(e)}")

    def _generate_sample_addresses(self):
        """Generate sample receive addresses for display"""
        sample_lines = []
        sample_lines.append(f"📋 Sample Receive Addresses ({self.derivation_path}/0/x):")
        
        try:
            for i in range(min(self.sample_address_count, 3)):  # Limit to 3 samples for now
                try:
                    addr_data = self.env['crypto.bip32.utils'].derive_address_from_xpub(
                        self.derived_xpub, 0, i, base_path=self.derivation_path  # 0 = receive chain
                    )
                    sample_lines.append(f"  {i}: {addr_data['address']}")
                except Exception as e:
                    sample_lines.append(f"  {i}: Error - {str(e)}")
                    
            self.sample_addresses = "\n".join(sample_lines)
        except Exception as e:
            _logger.warning(f"Could not generate sample addresses: {str(e)}")
            self.sample_addresses = f"Sample address generation failed: {str(e)}"

    def _prepare_success_message(self):
        """Prepare the success message for display"""
        script_name = dict(self._fields['script_type'].selection).get(self.script_type, self.script_type.upper())
        
        self.success_message = f"""
✅ Cosigner Key Created Successfully!

🔢 Account: {self.account_index} ({self.derivation_path})
🛡️ Script Type: {script_name}
👥 Cosigner: {self.cosigner_index}
{f"🏢 Multisig Wallet: {self.multisig_wallet_id.name}" if self.multisig_wallet_id else ""}
🔑 XPUB: {self.derived_xpub[:20]}...{self.derived_xpub[-20:]}

📖 Usage Instructions:
• Share this XPUB with other cosigners to create the multisig wallet
• Collect corresponding XPUBs from other cosigners using the same derivation path
• Use wallet software (Electrum, Bitcoin Core, etc.) to combine all XPUBs
• All final multisig addresses will follow BIP48 path: {self.derivation_path}/chain/index

⚠️ Security Notes:
• This XPUB is just YOUR contribution to the multisig
• Single addresses from this XPUB alone are NOT multisig protected
• Verify all cosigner XPUBs before creating the final multisig wallet
• Test with small amounts before using for large transactions
"""

    def action_view_public_key(self):
        """View the created public key record"""
        self.ensure_one()
        
        if not self.created_public_key_id:
            raise ValidationError("No public key created yet")
            
        return {
            'type': 'ir.actions.act_window',
            'name': f'Multisig Public Key - Account {self.account_index}',
            'res_model': 'crypto.bitcoin.public.key',
            'res_id': self.created_public_key_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_another(self):
        """Create another multisig public key"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Another Multisig Public Key',
            'res_model': 'wizard.create.multisig.public.key',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_private_key_id': self.private_key_id.id,
                'default_account_index': self.account_index + 1 if self.account_index is not False else 1,
                'default_script_type': self.script_type,
                'default_cosigner_index': self.cosigner_index,
            }
        }