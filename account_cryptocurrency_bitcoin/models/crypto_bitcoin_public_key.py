# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError, AccessError
import base58
import hashlib
import uuid
import logging
import json

import hashlib
import hmac
import struct

_logger = logging.getLogger(__name__)

class CryptoBitcoinPublicKey(models.Model):
    _name = 'crypto.bitcoin.public.key'
    _description = 'Crypto Bitcoin Public Key'
    _sql_constraints = [
        ('token_uuid_unique', 'unique(token_uuid)', 'Token UUID must be unique')
    ]

    name = fields.Char(string='Name', required=True)
    token_uuid = fields.Char(string='Token UUID', required=True, default=lambda self: str(uuid.uuid4()), 
                             copy=False, index=True)

    wallet_id = fields.Many2one('crypto.bitcoin.wallet', string='Wallet')

    owner_id = fields.Many2one('res.partner', string='Owner')
    notes = fields.Text(string='Notes')
    
    # Link to private key (if derived from one)
    private_key_id = fields.Many2one('crypto.bitcoin.private.key', string='Source Private Key')
    
    # BIP derivation information
    key_type = fields.Selection([
        ('master', 'Master Key (m/)'),
        ('account', 'Account Key (m/44\'/0\'/account\')'),
        ('multisig', 'Cosigner Key (m/48\'/0\'/account\'/script_type\')')
    ], string='Key Type', required=True, default='master',
       help="Master keys derive from root, Account keys for BIP44, Cosigner keys for BIP48/multisig wallets")
    
    derivation_path = fields.Char(string='Derivation Path', readonly=True,
                                help="BIP44 derivation path (e.g., m/44'/0'/0')")
    account_index = fields.Integer(string='Account Index', 
                                 help="BIP44/BIP48 account index for account/multisig keys")
    fingerprint = fields.Char(string='Key Fingerprint', compute='_compute_xpub_details', store=False)
    master_fingerprint = fields.Char(string='Master Fingerprint', 
                                    help="Root key fingerprint for wallet identification (8 hex chars)")
    
    # Multisig-specific fields
    script_type = fields.Selection([
        ('p2sh', 'P2SH (Legacy)'),
        ('p2wsh', 'P2WSH (Native SegWit)'),
        ('p2sh_p2wsh', 'P2SH-P2WSH (Wrapped SegWit)')
    ], string='Script Type', help="Multisig script type for BIP48 derivation")
    cosigner_index = fields.Integer(string='Cosigner Index', 
                                  help="Index of this cosigner in the multisig setup (0-based)")
    multisig_wallet_id = fields.Many2one('crypto.bitcoin.multisig.wallet', 
                                       string='Multisig Wallet',
                                       help="Associated multisig wallet")
    
    # Partner assignment for account-level keys
    partner_id = fields.Many2one('res.partner', string='Assigned Partner',
                               help="Partner this account key is assigned to for payment processing")

    # Fields to store/retrieve in Vault
    xpub = fields.Char(string='XPUB', compute='_compute_vault_values', inverse='_inverse_xpub', 
                       store=False, readonly=False)
    vault_status = fields.Char(string='Vault Status', compute='_compute_vault_values', store=False,
                              help="Status of vault connectivity for this key")
    
    # Hash field for efficient XPUB lookups
    xpub_hash = fields.Char(string='XPUB Hash', compute='_compute_xpub_hash', store=True, index=True,
                           help="SHA256 hash of XPUB+derivation_path for efficient lookups")

    # Transient fields to display parsed XPUB details
    xpub_version = fields.Char(string='XPUB Version', compute='_compute_xpub_details', store=False)
    xpub_depth = fields.Integer(string='Depth', compute='_compute_xpub_details', store=False)
    xpub_parent_fingerprint = fields.Char(string='Parent Fingerprint', compute='_compute_xpub_details', store=False)
    xpub_child_number = fields.Integer(string='Child Number', compute='_compute_xpub_details', store=False)
    xpub_chain_code = fields.Char(string='Chain Code', compute='_compute_xpub_details', store=False)
    xpub_public_key = fields.Char(string='Public Key', compute='_compute_xpub_details', store=False)

    # Address derivation settings
    max_derivation_count = fields.Integer(string='Max Derivation Count', default=50, 
                                        help="Maximum number of addresses that can be derived at once")
    
    # Computed fields for derived addresses (secured)
    derived_receive_addresses = fields.Text(string='Receive Addresses', 
                                          compute='_compute_derived_addresses', store=False, 
                                          help="First 20 receive addresses (m/0/x) derived from this XPUB using BIP32 + Bech32")
    derived_change_addresses = fields.Text(string='Change Addresses', 
                                         compute='_compute_derived_addresses', store=False,
                                         help="First 20 change addresses (m/1/x) derived from this XPUB using BIP32 + Bech32")
    

    def _inverse_xpub(self):
        for record in self:
            if record.xpub and record.token_uuid:
                # Store xpub in vault using token_uuid
                self.env['vault.connector'].set_secret(record.token_uuid, {
                    'xpub': record.xpub
                })

    @api.depends('xpub', 'derivation_path')
    def _compute_xpub_hash(self):
        """Compute SHA256 hash of XPUB + derivation path for efficient lookups"""
        for record in self:
            if record.xpub:
                # Combine XPUB and derivation path for unique identification
                hash_input = f"{record.xpub}:{record.derivation_path or ''}"
                record.xpub_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
            else:
                record.xpub_hash = False

    @api.model
    def compute_xpub_hash_static(self, xpub, derivation_path=None):
        """Static method to compute XPUB hash for lookups"""
        hash_input = f"{xpub}:{derivation_path or ''}"
        return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

    def _validate_xpub(self, xpub):
        """Check if the decoded data has the correct structure for an xpub"""
        try:
            decoded = base58.b58decode_check(xpub)
            return len(decoded) == 78 and decoded[0] == 0x04 and decoded[1] == 0x88 and decoded[2] == 0xB2 and decoded[3] == 0x1E
        except Exception:
            return False

    def action_refresh_vault_status(self):
        """Manually refresh vault status for this key"""
        self.ensure_one()
        # Force recomputation of vault values
        self._compute_vault_values()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Vault Status Refreshed',
                'message': f'Status: {self.vault_status}',
                'type': 'success' if '✅' in self.vault_status else 'warning'
            }
        }



    @api.model
    def create(self, vals):
        # Validate the xpub string if provided
        if 'xpub' in vals and vals['xpub']:
            if not self._validate_xpub(vals['xpub']):
                raise ValidationError("The provided xpub is invalid.")
        return super(CryptoBitcoinPublicKey, self).create(vals)

    @api.depends('token_uuid')
    def _compute_vault_values(self):
        """Compute XPUB and vault status using centralized vault service"""
        for record in self:
            if record.token_uuid:
                # Use centralized vault service
                vault_result = self._get_xpub_from_vault(record.token_uuid)
                record.xpub = vault_result.get('xpub', '')
                record.vault_status = vault_result.get('status', '❌ Unknown error')
            else:
                record.xpub = ''
                record.vault_status = '⚪ No token UUID'

    def _get_xpub_from_vault(self, token_uuid):
        """
        Centralized method to get XPUB from vault
        Returns: {'xpub': str, 'status': str}
        """
        try:
            vault_connector = self.env['vault.connector']
            vault_data = vault_connector.get_secret(token_uuid)
            
            if vault_data and vault_data.get('xpub'):
                return {
                    'xpub': vault_data['xpub'],
                    'status': '✅ Connected'
                }
            else:
                return {
                    'xpub': '',
                    'status': '⚠️ No XPUB data in vault'
                }
                
        except Exception as e:
            error_msg = str(e)
            _logger.warning(f"Vault error for token {token_uuid}: {error_msg}")
            
            # Categorize errors for user-friendly display
            if 'sealed' in error_msg.lower():
                status = '🔒 Vault is sealed - unseal required'
            elif 'not accessible' in error_msg or 'environment variables' in error_msg:
                status = '❌ Vault not configured'
            elif 'not found' in error_msg:
                status = '⚠️ Secret not found in vault'
            elif 'access denied' in error_msg or 'token' in error_msg:
                status = '❌ Vault access denied'
            else:
                status = f'❌ Vault error: {error_msg}'
                
            return {
                'xpub': '',
                'status': status
            }

    @api.depends('xpub')
    def _compute_xpub_details(self):
        for pubkey in self:
            try:
                if not pubkey.xpub:
                    # Clear fields if xpub is empty
                    pubkey.xpub_version = ''
                    pubkey.xpub_depth = 0
                    pubkey.xpub_parent_fingerprint = ''
                    pubkey.xpub_child_number = 0
                    pubkey.xpub_chain_code = ''
                    pubkey.xpub_public_key = ''
                    pubkey.fingerprint = ''
                    continue

                # Decode the base58 xpub
                decoded = base58.b58decode_check(pubkey.xpub)

                # Extract the details
                pubkey.xpub_version = decoded[:4].hex()
                pubkey.xpub_depth = decoded[4]
                pubkey.xpub_parent_fingerprint = decoded[5:9].hex()
                pubkey.xpub_child_number = int.from_bytes(decoded[9:13], 'big')
                pubkey.xpub_chain_code = decoded[13:45].hex()
                pubkey.xpub_public_key = decoded[45:78].hex()
                
                # Calculate the key fingerprint (XFP) - first 4 bytes of HASH160 of this key's public key
                public_key_bytes = decoded[45:78]
                try:
                    bip32_utils = self.env['crypto.bip32.utils']
                    key_fingerprint = bip32_utils._hash160(public_key_bytes)[:4]
                    pubkey.fingerprint = key_fingerprint.hex()
                except Exception as fp_error:
                    _logger.warning(f"Failed to calculate fingerprint for {pubkey.name}: {str(fp_error)}")
                    pubkey.fingerprint = f"Error: {str(fp_error)}"
                
            except Exception as e:
                # If parsing fails, clear the fields
                _logger.warning(f"Failed to parse XPUB details for {pubkey.name}: {str(e)}")
                pubkey.xpub_version = ''
                pubkey.xpub_depth = 0
                pubkey.xpub_parent_fingerprint = ''
                pubkey.xpub_child_number = 0
                pubkey.xpub_chain_code = ''
                pubkey.xpub_public_key = ''
                pubkey.fingerprint = f"Parse error: {str(e)}"

    # Duplicate Bech32 and crypto methods removed - now using crypto.bip32.utils

    # _hash160 method removed - now using crypto.bip32.utils

    # _derive_child_key method removed - now using crypto.bip32.utils

    def _check_derivation_access(self):
        """Verify user has proper access to derive addresses"""
        self.check_access_rights('read')
        if not self.xpub:
            raise ValidationError("Cannot derive addresses: XPUB not available")
        
    def _validate_derivation_params(self, start_index, count):
        """Validate derivation parameters for security"""
        if start_index < 0:
            raise ValidationError("Start index must be non-negative")
        if count <= 0:
            raise ValidationError("Count must be positive")
        if count > self.max_derivation_count:
            raise ValidationError(f"Cannot derive more than {self.max_derivation_count} addresses at once")
        if start_index + count > 10000:  # Reasonable upper limit
            raise ValidationError("Cannot derive addresses beyond index 10000")

    def _get_address_type_from_path(self, derivation_path):
        """Determine the correct address type based on BIP derivation path"""
        if not derivation_path:
            return "bech32"  # Default fallback
            
        # Extract purpose from derivation path (first hardened component)
        if "44'" in derivation_path or "44h" in derivation_path:
            return "p2pkh"    # BIP44 - Legacy addresses (1...)
        elif "49'" in derivation_path or "49h" in derivation_path:
            return "p2sh"     # BIP49 - Nested SegWit (3...)
        elif "84'" in derivation_path or "84h" in derivation_path:
            return "bech32"   # BIP84 - Native SegWit (bc1q...)
        elif "86'" in derivation_path or "86h" in derivation_path:
            return "taproot"  # BIP86 - Taproot (bc1p...)
        else:
            # For master keys or unknown paths, default to bech32
            return "bech32"

    def _derive_address_from_xpub(self, xpub, change, index):
        """Derive a single address from XPUB using unified derivation method"""
        try:
            # Determine the appropriate base path for display based on key type
            if self.derivation_path:
                # Use the actual derivation path of this key
                base_path = self.derivation_path
            elif self.key_type == 'master':
                base_path = "m"
            else:
                # Fallback for keys without derivation path
                base_path = "m"
            
            # Determine address type from derivation path
            address_type = self._get_address_type_from_path(base_path)
            
            # Use unified derivation from BIP32 utils
            addr_data = self.env['crypto.bip32.utils'].derive_address_from_xpub(
                xpub, change, index, base_path=base_path, address_type=address_type
            )
            
            return addr_data
                
        except Exception as e:
            _logger.error(f"Address derivation failed: {str(e)}")
            raise ValidationError(f"Failed to derive address: {str(e)}")

    def derive_addresses(self, start_index=0, count=20, change=False):
        """
        Securely derive multiple addresses from XPUB
        
        Args:
            start_index (int): Starting derivation index
            count (int): Number of addresses to derive  
            change (bool): Whether to derive change addresses (m/1/x) or receive (m/0/x)
            
        Returns:
            list: List of address dictionaries with index, path, address
        """
        self.ensure_one()
        self._check_derivation_access()
        self._validate_derivation_params(start_index, count)
        
        _logger.info(f"Deriving {count} addresses starting at index {start_index} for XPUB {self.name}")
        
        addresses = []
        change_int = 1 if change else 0
        
        for i in range(start_index, start_index + count):
            try:
                addr_info = self._derive_address_from_xpub(self.xpub, change_int, i)
                addresses.append(addr_info)
            except Exception as e:
                _logger.error(f"Failed to derive address at index {i}: {str(e)}")
                # Continue with other addresses rather than failing completely
                continue
                
        return addresses

    def get_derivation_info(self):
        """Get derivation path information for this key"""
        self.ensure_one()
        
        if self.key_type == 'master':
            return {
                'base_path': 'm/',
                'description': 'Master key addresses (non-standard)',
                'standard': False
            }
        elif self.key_type == 'account':
            return {
                'base_path': self.derivation_path,
                'description': f'BIP44 Account {self.account_index} addresses',
                'standard': True,
                'receive_path': f"{self.derivation_path}/0/x",
                'change_path': f"{self.derivation_path}/1/x"
            }
        elif self.key_type == 'multisig':
            script_name = dict(self._fields['script_type'].selection).get(self.script_type, 'Unknown')
            return {
                'base_path': self.derivation_path,
                'description': f'BIP48 Cosigner Account {self.account_index} ({script_name}) - Cosigner {self.cosigner_index}',
                'standard': True,
                'receive_path': f"{self.derivation_path}/0/x",
                'change_path': f"{self.derivation_path}/1/x",
                'script_type': self.script_type,
                'cosigner_index': self.cosigner_index
            }
        else:
            return {
                'base_path': 'unknown',
                'description': 'Unknown key type',
                'standard': False
            }

    @api.depends('xpub', 'max_derivation_count', 'key_type', 'derivation_path')
    def _compute_derived_addresses(self):
        """Compute preview of derived addresses for display"""
        for record in self:
            if not record.xpub:
                # Use centralized vault service to get status
                if record.token_uuid:
                    vault_result = record._get_xpub_from_vault(record.token_uuid)
                    if not vault_result.get('xpub'):
                        error_msg = f"Cannot retrieve XPUB: {vault_result.get('status', 'Unknown error')}"
                    else:
                        error_msg = "XPUB not found in Vault or vault connection failed"
                    
                    record.derived_receive_addresses = error_msg
                    record.derived_change_addresses = error_msg
                else:
                    record.derived_receive_addresses = "XPUB required for address derivation"
                    record.derived_change_addresses = "XPUB required for address derivation"
                continue

            try:
                # Derive first 20 receive addresses (m/0/x)
                receive_addrs = record.derive_addresses(start_index=0, count=20, change=False)
                receive_text = "\n".join([f"{addr['path']}: {addr['address']}" for addr in receive_addrs])
                record.derived_receive_addresses = receive_text
                
                # Derive first 20 change addresses (m/1/x) 
                change_addrs = record.derive_addresses(start_index=0, count=20, change=True)
                change_text = "\n".join([f"{addr['path']}: {addr['address']}" for addr in change_addrs])
                record.derived_change_addresses = change_text
                
            except Exception as e:
                _logger.warning(f"Could not compute derived addresses for {record.name}: {str(e)}")
                record.derived_receive_addresses = f"Error deriving addresses: {str(e)}"
                record.derived_change_addresses = f"Error deriving addresses: {str(e)}"


    def action_derive_addresses_wizard(self):
        """Launch the address derivation wizard"""
        self.ensure_one()
        self._check_derivation_access()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Derive Addresses',
            'res_model': 'wizard.derive.addresses',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_public_key_id': self.id,
            }
        }


    def action_view_private_key(self):
        """View the linked private key"""
        self.ensure_one()
        
        if not self.private_key_id:
            raise ValidationError("No private key linked to this public key")
            
        return {
            'type': 'ir.actions.act_window',
            'name': 'Source Private Key',
            'res_model': 'crypto.bitcoin.private.key',
            'res_id': self.private_key_id[0].id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def default_get(self, fields_list):
        """Override default_get to provide appropriate defaults"""
        return super().default_get(fields_list)

    @api.model
    def create(self, vals):
        """Override create to redirect to wizard if appropriate"""
        # If no XPUB provided and we're not in wizard context, redirect to wizard
        if not vals.get('xpub') and not self.env.context.get('from_wizard'):
            # This would typically redirect to wizard, but since we can't return actions from create,
            # we'll just proceed with normal creation but validate required fields
            pass
        return super().create(vals)

    @api.model
    def action_create_public_key(self):
        """Custom create action to open Import XPUB wizard"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Import XPUB',
            'res_model': 'wizard.import.xpub',
            'view_mode': 'form',
            'target': 'new',
        }
