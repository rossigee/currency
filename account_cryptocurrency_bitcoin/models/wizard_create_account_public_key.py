# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class WizardCreateAccountPublicKey(models.TransientModel):
    _name = 'wizard.create.account.public.key'
    _description = 'Wizard to Create Account-Level Public Key'
    
    @api.model
    def create(self, vals):
        """Override create to ensure private_key_id from context and execute account creation"""
        # Apply default from context if missing
        if 'private_key_id' not in vals and 'default_private_key_id' in self.env.context:
            vals['private_key_id'] = self.env.context['default_private_key_id']
        
        # Create the wizard record first
        wizard = super().create(vals)
        
        # Then execute the account public key creation
        wizard._execute_account_creation()
        
        return wizard

    # Source private key
    private_key_id = fields.Many2one('crypto.bitcoin.private.key', string='Private Key', 
                                   required=True, readonly=True)
    private_key_name = fields.Char(related='private_key_id.name', readonly=True)
    
    # Account details
    account_index = fields.Integer(string='Account Index', required=True, default=0,
                                 help="BIP44 account index (0-2147483647). Each account needs a unique index.")
    partner_id = fields.Many2one('res.partner', string='Assign to Partner',
                               help="Optional: Assign this account to a specific partner for payment processing")
    name_suffix = fields.Char(string='Name Suffix', 
                             help="Optional custom suffix for the public key name")
    
    # Account management
    suggest_next_account = fields.Boolean(string='Auto-suggest Next Account', default=True,
                                        help="Automatically suggest the next available account index")
    next_available_account = fields.Integer(string='Next Available Account', compute='_compute_next_account')
    existing_accounts = fields.Text(string='Existing Account Keys', compute='_compute_existing_accounts')
    
    # Derivation preview
    derivation_path = fields.Char(string='Derivation Path', compute='_compute_derivation_info')
    
    # Options
    notes = fields.Text(string='Notes', help="Optional notes about this account public key")
    create_sample_addresses = fields.Boolean(string='Generate Sample Addresses', default=True,
                                           help="Generate a few sample addresses to verify derivation")
    sample_address_count = fields.Integer(string='Sample Address Count', default=3)
    
    # Results (shown after creation)
    created_public_key_id = fields.Many2one('crypto.bitcoin.public.key', string='Created Public Key', readonly=True)
    derived_xpub = fields.Char(string='Derived XPUB', readonly=True)
    sample_addresses = fields.Text(string='Sample Addresses', readonly=True)
    success_message = fields.Text(string='Success Message', readonly=True)

    @api.onchange('suggest_next_account', 'private_key_id')
    def _onchange_suggest_account(self):
        """Auto-fill account index when auto-suggest is enabled"""
        if self.suggest_next_account and self.private_key_id:
            self.account_index = self.next_available_account

    @api.depends('private_key_id')
    def _compute_next_account(self):
        """Compute the next available account index"""
        for record in self:
            if record.private_key_id:
                # Find highest used account index
                existing_accounts = self.env['crypto.bitcoin.public.key'].search([
                    ('private_key_id', '=', record.private_key_id.id),
                    ('key_type', '=', 'account')
                ], order='account_index desc', limit=1)
                
                if existing_accounts:
                    record.next_available_account = existing_accounts.account_index + 1
                else:
                    record.next_available_account = 0
            else:
                record.next_available_account = 0

    @api.depends('private_key_id')
    def _compute_existing_accounts(self):
        """Show existing account assignments"""
        for record in self:
            if record.private_key_id:
                existing = self.env['crypto.bitcoin.public.key'].search([
                    ('private_key_id', '=', record.private_key_id.id),
                    ('key_type', '=', 'account')
                ], order='account_index')
                
                if existing:
                    lines = []
                    for account in existing:
                        partner_info = f" → {account.partner_id.name}" if account.partner_id else ""
                        lines.append(f"Account {account.account_index}: {account.name}{partner_info}")
                    record.existing_accounts = "\n".join(lines)
                else:
                    record.existing_accounts = "No account keys created yet"
            else:
                record.existing_accounts = ""

    @api.depends('account_index')
    def _compute_derivation_info(self):
        """Compute derivation path preview"""
        for record in self:
            if record.account_index is not False:
                record.derivation_path = f"m/44'/0'/{record.account_index}'"
            else:
                record.derivation_path = ""

    def _validate_inputs(self):
        """Validate wizard inputs"""
        # Validate account index range
        if self.account_index < 0 or self.account_index > 2147483647:
            raise ValidationError("Account index must be between 0 and 2147483647")
            
        # Check for duplicate account index
        existing_account = self.env['crypto.bitcoin.public.key'].search([
            ('private_key_id', '=', self.private_key_id.id),
            ('key_type', '=', 'account'),
            ('account_index', '=', self.account_index)
        ])
        if existing_account:
            raise ValidationError(f"Account {self.account_index} already has a public key: {existing_account.name}")

    def _execute_account_creation(self):
        """Execute the account public key creation (called automatically on save)"""
        self.ensure_one()
        
        try:
            self._validate_inputs()
            
            # Create account public key using private key method
            account_public_key = self.private_key_id.create_account_public_key(
                account_index=self.account_index,
                partner_id=self.partner_id.id if self.partner_id else None,
                name_suffix=self.name_suffix
            )
            
            # Add notes if provided
            if self.notes:
                account_public_key.notes = self.notes
                
            # Store reference for display
            self.created_public_key_id = account_public_key.id
            self.derived_xpub = account_public_key.xpub
            
            # Generate sample addresses if requested
            if self.create_sample_addresses and self.sample_address_count > 0:
                self._generate_sample_addresses()
            
            # Prepare success message
            self._prepare_success_message()
            
            _logger.info(f"Account public key creation completed successfully")
            
        except ValidationError as e:
            _logger.error(f"Validation error in account public key creation: {str(e)}")
            raise
        except Exception as e:
            _logger.error(f"Unexpected error in account public key creation: {str(e)}")
            raise ValidationError(f"Failed to create account public key: {str(e)}")

    def _generate_sample_addresses(self):
        """Generate sample receive addresses for display"""
        sample_lines = []
        sample_lines.append(f"📋 Sample Receive Addresses ({self.derivation_path}/0/x):")
        
        try:
            for i in range(min(self.sample_address_count, 3)):  # Limit to 3 samples for now
                try:
                    addr_data = self.env['crypto.bip32.utils'].derive_address_from_account_xpub(
                        self.derived_xpub, 0, i  # 0 = receive chain
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
        self.success_message = f"""
✅ Account Public Key Created Successfully!

🔢 Account: {self.account_index} ({self.derivation_path})
{f"🏢 Partner: {self.partner_id.name}" if self.partner_id else ""}
🔑 XPUB: {self.derived_xpub[:20]}...{self.derived_xpub[-20:]}

📖 Usage Instructions:
• Use this XPUB to derive addresses for account {self.account_index}
• All addresses follow BIP44 path: {self.derivation_path}/chain/index
• Chain 0 = receive addresses, Chain 1 = change addresses
{f"• Share with {self.partner_id.name} for payment processing" if self.partner_id else ""}

⚠️ Security Notes:
• XPUB allows address generation but NOT spending
• Keep your private key secure
• Monitor transactions via this account path
"""

    def action_create_account_public_key(self):
        """Legacy method - now just calls the execution method and returns form"""
        self.ensure_one()
        
        # Execute the creation if not already done
        if not self.created_public_key_id:
            self._execute_account_creation()
        
        # Return action to show results
        return {
            'type': 'ir.actions.act_window',
            'name': f'Account Public Key Created - Account {self.account_index}',
            'res_model': 'wizard.create.account.public.key',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'show_results': True}
        }

    def action_view_public_key(self):
        """View the created public key record"""
        self.ensure_one()
        
        if not self.created_public_key_id:
            raise ValidationError("No public key created yet")
            
        return {
            'type': 'ir.actions.act_window',
            'name': f'Account Public Key - Account {self.account_index}',
            'res_model': 'crypto.bitcoin.public.key',
            'res_id': self.created_public_key_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_another(self):
        """Create another account public key"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Another Account Public Key',
            'res_model': 'wizard.create.account.public.key',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_private_key_id': self.private_key_id.id,
                'default_account_index': self.account_index + 1 if self.account_index is not False else 1,
            }
        }