# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging
import base64
import json
from datetime import datetime

_logger = logging.getLogger(__name__)

class CryptoBitcoinMultisigWallet(models.Model):
    _name = 'crypto.bitcoin.multisig.wallet'
    _description = 'Crypto Bitcoin Multisig Wallet'

    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
    
    # Multisig configuration
    m_of_n_threshold = fields.Integer(string='Required Signatures (M)', required=True, default=2,
                                     help="Number of signatures required to spend (M in M-of-N)")
    total_cosigners = fields.Integer(string='Total Cosigners (N)', required=True, default=3,
                                    help="Total number of cosigners (N in M-of-N)")
    
    # Script type
    script_type = fields.Selection([
        ('p2sh', 'P2SH (Legacy Multisig)'),
        ('p2wsh', 'P2WSH (Native SegWit)'),
        ('p2sh_p2wsh', 'P2SH-P2WSH (Wrapped SegWit)')
    ], string='Script Type', required=True, default='p2wsh',
       help="Multisig script type for address generation")
    
    # Network
    network = fields.Selection([
        ('mainnet', 'Bitcoin Mainnet'),
        ('testnet', 'Bitcoin Testnet')
    ], string='Network', required=True, default='mainnet')
    
    # Associated public keys
    cosigner_public_key_ids = fields.One2many('crypto.bitcoin.public.key', 'multisig_wallet_id',
                                              string='Cosigner Public Keys',
                                              domain=[('key_type', '=', 'multisig')])
    
    # Legacy field for backward compatibility
    wallet_ids = fields.Many2many('crypto.bitcoin.wallet', string='Associated Wallets')
    signer_count = fields.Integer(string="Signer count", compute='_compute_signer_count', store=True)
    
    # Computed fields
    is_complete = fields.Boolean(string='Configuration Complete', compute='_compute_completeness', store=True)
    vault_status_summary = fields.Text(string='Vault Status Summary', compute='_compute_vault_status_summary', store=False)
    has_vault_issues = fields.Boolean(string='Has Vault Issues', compute='_compute_vault_status_summary', store=False)
    bsms_content = fields.Text(string='BSMS File Content', compute='_compute_bsms_content', store=False)
    
    # Address derivation fields
    max_address_count = fields.Integer(string='Max Address Count', default=20, 
                                     help="Maximum number of addresses to generate at once")
    derived_receive_addresses = fields.Text(string='Receive Addresses', 
                                          compute='_compute_derived_addresses', store=False,
                                          help="Multisig receive addresses (m/0/x)")
    derived_change_addresses = fields.Text(string='Change Addresses', 
                                         compute='_compute_derived_addresses', store=False,
                                         help="Multisig change addresses (m/1/x)")

    @api.depends('total_cosigners', 'cosigner_public_key_ids')
    def _compute_signer_count(self):
        """Maintain backward compatibility"""
        for record in self:
            record.signer_count = len(record.cosigner_public_key_ids)

    @api.depends('m_of_n_threshold', 'total_cosigners', 'cosigner_public_key_ids', 'script_type', 'has_vault_issues')
    def _compute_completeness(self):
        """Check if multisig wallet configuration is complete"""
        for record in self:
            record.is_complete = (
                record.m_of_n_threshold > 0 and
                record.total_cosigners > 0 and
                record.m_of_n_threshold <= record.total_cosigners and
                len(record.cosigner_public_key_ids) == record.total_cosigners and
                record.script_type and
                all(key.xpub for key in record.cosigner_public_key_ids) and
                not record.has_vault_issues  # New condition: no vault issues
            )

    @api.depends('cosigner_public_key_ids.vault_status', 'cosigner_public_key_ids.xpub')
    def _compute_vault_status_summary(self):
        """Compute vault status summary for all cosigners"""
        for record in self:
            if not record.cosigner_public_key_ids:
                record.vault_status_summary = ""
                record.has_vault_issues = False
                continue
                
            status_items = []
            has_issues = False
            
            for key in record.cosigner_public_key_ids:
                vault_status = key.vault_status or ''
                
                if not key.xpub:
                    status_items.append(f"❌ {key.name}: No XPUB available")
                    has_issues = True
                elif '❌' in vault_status:
                    status_items.append(f"❌ {key.name}: {vault_status}")
                    has_issues = True
                elif '⚠️' in vault_status:
                    # For ⚠️ warnings, only consider it an issue if there's no XPUB
                    # (some warnings like "No data found" might still have working XPUBs from cache)
                    status_items.append(f"⚠️ {key.name}: {vault_status}")
                    if not key.xpub:
                        has_issues = True
                elif '✅' in vault_status:
                    status_items.append(f"✅ {key.name}: Connected")
                elif '⚪' in vault_status:
                    status_items.append(f"⚪ {key.name}: {vault_status}")
                    # No token UUID is not necessarily a blocking issue if XPUB is available
                    if not key.xpub:
                        has_issues = True
                else:
                    status_items.append(f"⚪ {key.name}: Unknown status")
                    if not key.xpub:
                        has_issues = True
            
            record.vault_status_summary = "\n".join(status_items)
            record.has_vault_issues = has_issues

    @api.depends('cosigner_public_key_ids', 'm_of_n_threshold', 'script_type', 'network')
    def _compute_bsms_content(self):
        """Generate BSMS (Bitcoin Secure Multisig Standard) file content per BIP-129 Descriptor Record format"""
        for record in self:
            if not record.is_complete:
                record.bsms_content = ""
                continue
                
            try:
                # BIP-129 Descriptor Record format:
                # Line 1: BSMS 1.0
                # Line 2: Descriptor (e.g., wsh(sortedmulti(m,[fp/path]xpub,[fp/path]xpub)))
                # Line 3: Path restrictions 
                # Line 4: First address
                
                bsms_lines = []
                
                # Line 1: Version
                bsms_lines.append("BSMS 1.0")
                
                # Line 2: Build descriptor
                script_type_map = {
                    'p2sh': 'sh',
                    'p2wsh': 'wsh', 
                    'p2sh_p2wsh': 'sh'  # For P2SH-wrapped P2WSH, outer is sh()
                }
                outer_script = script_type_map.get(record.script_type, 'wsh')
                
                # Sort cosigners by cosigner_index for consistent ordering
                sorted_keys = record.cosigner_public_key_ids.sorted('cosigner_index')
                
                # Build key entries with fingerprint/path prefixes
                key_entries = []
                for key in sorted_keys:
                    if key.xpub:
                        # Format: [master_fingerprint/derivation_path]xpub
                        master_fp = key.master_fingerprint or "00000000"
                        derivation = key.derivation_path or "48'/0'/0'/2'"
                        
                        # Remove 'm/' prefix from derivation path for descriptor format
                        if derivation.startswith('m/'):
                            derivation = derivation[2:]
                        
                        key_entry = f"[{master_fp}/{derivation}]{key.xpub}"
                        key_entries.append(key_entry)
                
                if len(key_entries) == record.total_cosigners:
                    # Build the descriptor
                    if record.script_type == 'p2sh_p2wsh':
                        # P2SH-wrapped P2WSH: sh(wsh(sortedmulti(...)))
                        inner_desc = f"wsh(sortedmulti({record.m_of_n_threshold},{','.join(key_entries)}))"
                        descriptor = f"sh({inner_desc})"
                    else:
                        # Pure P2SH or P2WSH: sh(sortedmulti(...)) or wsh(sortedmulti(...))
                        descriptor = f"{outer_script}(sortedmulti({record.m_of_n_threshold},{','.join(key_entries)}))"
                    
                    bsms_lines.append(descriptor)
                    
                    # Line 3: Path restrictions - standard receive/change pattern
                    bsms_lines.append("/0/*,/1/*")
                    
                    # Line 4: Generate first multisig address (m/0/0)
                    try:
                        first_address = record._generate_first_multisig_address()
                        bsms_lines.append(first_address)
                    except Exception as addr_error:
                        _logger.warning(f"Failed to generate first address: {str(addr_error)}")
                        bsms_lines.append("# Error generating first address")
                    
                else:
                    bsms_lines.append("# Error: Not all cosigner XPUBs are available")
                    bsms_lines.append("/0/*,/1/*") 
                    bsms_lines.append("# Cannot generate first address")
                
                record.bsms_content = "\n".join(bsms_lines)
                
            except Exception as e:
                _logger.warning(f"Failed to generate BSMS for {record.name}: {str(e)}")
                record.bsms_content = f"# Error generating BSMS: {str(e)}\n/0/*,/1/*\n# Cannot generate address"

    def _generate_first_multisig_address(self):
        """Generate the first multisig address (m/0/0) using utility class"""
        self.ensure_one()
        
        if not self.is_complete:
            raise ValidationError("Cannot generate address: multisig wallet not complete")
        
        # Get sorted cosigner keys
        sorted_keys = self.cosigner_public_key_ids.sorted('cosigner_index')
        
        # Prepare XPUB and path data for utility method
        xpubs_with_paths = []
        for key in sorted_keys:
            if not key.xpub:
                raise ValidationError(f"Missing XPUB for cosigner {key.name}")
            xpubs_with_paths.append((key.xpub, key.derivation_path or "m/48'/0'/0'/2'"))
        
        # Use utility class to generate multisig address
        bip32_utils = self.env['crypto.bip32.utils']
        addr_info = bip32_utils.generate_multisig_address(
            xpubs_with_paths=xpubs_with_paths,
            m_threshold=self.m_of_n_threshold,
            script_type=self.script_type,
            change=0,  # receive addresses
            index=0    # first address
        )
        
        return addr_info['address']

    @api.depends('cosigner_public_key_ids', 'm_of_n_threshold', 'script_type', 'is_complete', 'max_address_count')
    def _compute_derived_addresses(self):
        """Compute derived multisig addresses for display"""
        for record in self:
            if not record.is_complete:
                record.derived_receive_addresses = "Multisig wallet configuration incomplete"
                record.derived_change_addresses = "Multisig wallet configuration incomplete"
                continue
                
            try:
                # Check if all cosigners have XPUBs available
                missing_xpubs = []
                for key in record.cosigner_public_key_ids:
                    if not key.xpub:
                        missing_xpubs.append(key.name)
                
                if missing_xpubs:
                    error_msg = f"Missing XPUBs for cosigners: {', '.join(missing_xpubs)}\n\nPossible causes:\n• Vault server not accessible\n• XPUBs not imported for these cosigners\n• Vault authentication issues\n\nTo resolve:\n1. Check vault connectivity\n2. Verify cosigner public keys have XPUBs imported\n3. Check vault environment variables (VAULT_ADDR, VAULT_TOKEN)"
                    
                    record.derived_receive_addresses = error_msg
                    record.derived_change_addresses = error_msg
                    continue
                
                # Generate receive addresses (m/0/x)
                receive_addrs = record._generate_multisig_addresses(
                    change=0, 
                    count=record.max_address_count
                )
                receive_text = "\n".join([
                    f"m/0/{addr['index']}: {addr['address']}" 
                    for addr in receive_addrs
                ])
                record.derived_receive_addresses = receive_text
                
                # Generate change addresses (m/1/x)
                change_addrs = record._generate_multisig_addresses(
                    change=1, 
                    count=record.max_address_count
                )
                change_text = "\n".join([
                    f"m/1/{addr['index']}: {addr['address']}" 
                    for addr in change_addrs
                ])
                record.derived_change_addresses = change_text
                
            except ValidationError as ve:
                _logger.warning(f"Validation error computing derived addresses for {record.name}: {str(ve)}")
                error_msg = f"Validation error: {str(ve)}"
                record.derived_receive_addresses = error_msg
                record.derived_change_addresses = error_msg
            except Exception as e:
                _logger.warning(f"Failed to compute derived addresses for {record.name}: {str(e)}")
                error_msg = f"Error generating addresses: {str(e)}"
                record.derived_receive_addresses = error_msg
                record.derived_change_addresses = error_msg

    def _generate_multisig_addresses(self, change=0, count=20):
        """Generate multiple multisig addresses using utility class"""
        self.ensure_one()
        
        if not self.is_complete:
            raise ValidationError("Cannot generate addresses: multisig wallet not complete")
        
        # Get sorted cosigner keys
        sorted_keys = self.cosigner_public_key_ids.sorted('cosigner_index')
        
        # Prepare XPUB and path data for utility method
        xpubs_with_paths = []
        for key in sorted_keys:
            if not key.xpub:
                raise ValidationError(f"Missing XPUB for cosigner {key.name}")
            xpubs_with_paths.append((key.xpub, key.derivation_path or "m/48'/0'/0'/2'"))
        
        # Generate multiple addresses
        addresses = []
        bip32_utils = self.env['crypto.bip32.utils']
        
        for index in range(count):
            try:
                addr_info = bip32_utils.generate_multisig_address(
                    xpubs_with_paths=xpubs_with_paths,
                    m_threshold=self.m_of_n_threshold,
                    script_type=self.script_type,
                    change=change,
                    index=index
                )
                addresses.append(addr_info)
            except Exception as e:
                _logger.error(f"Failed to generate address at {change}/{index}: {str(e)}")
                # Continue with other addresses
                continue
                
        return addresses

    @api.constrains('m_of_n_threshold', 'total_cosigners')
    def _check_threshold_validity(self):
        """Validate M-of-N threshold"""
        for record in self:
            if record.m_of_n_threshold <= 0:
                raise ValidationError("Required signatures (M) must be greater than 0")
            if record.total_cosigners <= 0:
                raise ValidationError("Total cosigners (N) must be greater than 0")
            if record.m_of_n_threshold > record.total_cosigners:
                raise ValidationError("Required signatures (M) cannot exceed total cosigners (N)")

    def action_download_bsms(self):
        """Generate and download BSMS file"""
        self.ensure_one()
        
        if not self.is_complete:
            raise ValidationError(
                "Cannot generate BSMS file: Multisig wallet configuration is incomplete. "
                "Ensure all cosigner public keys are added and have valid XPUBs."
            )
        
        # Generate filename
        filename = f"{self.name.replace(' ', '_')}_multisig.bsms"
        
        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(self.bsms_content.encode('utf-8')),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'text/plain',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_add_cosigner(self):
        """Launch wizard to add a cosigner public key"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Add Cosigner Public Key',
            'res_model': 'wizard.import.xpub',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_key_type': 'multisig',
                'default_script_type': self.script_type,
                'default_multisig_wallet_id': self.id,
                'default_account_index': 0,
                'default_cosigner_index': len(self.cosigner_public_key_ids),
                'default_name': f"{self.name} - Cosigner {len(self.cosigner_public_key_ids) + 1}",
            }
        }

    def create_multisig_wallet(self):
        """Legacy method for backward compatibility"""
        return {
            'type': 'ir.actions.act_window_close',
        }