# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import base64
import json
import logging

_logger = logging.getLogger(__name__)


class WizardImportBsms(models.TransientModel):
    _name = 'wizard.import.bsms'
    _description = 'Import BSMS File Wizard'

    # BSMS file upload
    bsms_file = fields.Binary(string='BSMS File', required=True,
                              help="Upload a BSMS (Bitcoin Secure Multisig Setup) file")
    bsms_filename = fields.Char(string='Filename')
    
    # Validation fields
    bsms_valid = fields.Boolean(string='BSMS Valid', 
                                compute='_compute_bsms_validation', store=False)
    validation_message = fields.Text(string='Validation Result', 
                                     compute='_compute_bsms_validation', store=False)
    
    # Parsed BSMS data
    parsed_data = fields.Text(string='Parsed Data', 
                              compute='_compute_bsms_validation', store=False)
    wallet_name = fields.Char(string='Wallet Name', 
                              compute='_compute_bsms_validation', store=False)
    m_threshold = fields.Integer(string='Required Signatures (M)', 
                                 compute='_compute_bsms_validation', store=False)
    n_total = fields.Integer(string='Total Cosigners (N)', 
                             compute='_compute_bsms_validation', store=False)
    script_type = fields.Char(string='Script Type', 
                              compute='_compute_bsms_validation', store=False)
    
    @api.depends('bsms_file')
    def _compute_bsms_validation(self):
        """Validate and parse the BSMS file"""
        for record in self:
            if not record.bsms_file:
                record.bsms_valid = False
                record.validation_message = "No BSMS file uploaded"
                record.parsed_data = ""
                record.wallet_name = ""
                record.m_threshold = 0
                record.n_total = 0
                record.script_type = ""
                continue
                
            try:
                # Decode the uploaded file
                file_content = base64.b64decode(record.bsms_file)
                bsms_text = file_content.decode('utf-8').strip()
                
                _logger.info(f"Parsing BSMS file, length: {len(bsms_text)}")
                _logger.info(f"BSMS content preview: {bsms_text[:200]}...")
                
                # Parse BSMS format
                bsms_data = record._parse_bsms_content(bsms_text)
                
                if bsms_data:
                    record.bsms_valid = True
                    record.validation_message = f"✅ Valid BSMS file: {bsms_data['m']}-of-{bsms_data['n']} {bsms_data['script_type']} multisig"
                    record.parsed_data = json.dumps(bsms_data, indent=2)
                    record.wallet_name = bsms_data.get('name', 'Imported Multisig Wallet')
                    record.m_threshold = bsms_data['m']
                    record.n_total = bsms_data['n']
                    record.script_type = bsms_data['script_type']
                else:
                    record.bsms_valid = False
                    record.validation_message = f"❌ Invalid BSMS file format - check logs for details"
                    record.parsed_data = f"Raw content:\n{bsms_text}"
                    record.wallet_name = ""
                    record.m_threshold = 0
                    record.n_total = 0
                    record.script_type = ""
                    
            except Exception as e:
                _logger.error(f"BSMS validation failed: {str(e)}", exc_info=True)
                record.bsms_valid = False
                record.validation_message = f"❌ BSMS parsing error: {str(e)}"
                record.parsed_data = ""
                record.wallet_name = ""
                record.m_threshold = 0
                record.n_total = 0
                record.script_type = ""

    def _parse_bsms_content(self, bsms_text):
        """
        Parse BSMS file content according to BIP-129 specification
        
        Args:
            bsms_text (str): BSMS file content
            
        Returns:
            dict: Parsed BSMS data or None if invalid
        """
        try:
            lines = [line.strip() for line in bsms_text.split('\n') if line.strip()]
            
            _logger.info(f"BSMS lines: {len(lines)}")
            for i, line in enumerate(lines[:5]):  # Log first 5 lines
                _logger.info(f"Line {i}: {line}")
            
            if not lines:
                _logger.error("BSMS file is empty or has no valid lines")
                return None
            
            # Find the descriptor line (should contain wsh, sh, tr, sortedmulti, or multi)
            descriptor = None
            descriptor_line_index = 0
            
            for i, line in enumerate(lines):
                if line.startswith(('wsh(', 'sh(', 'tr(', 'sortedmulti(', 'multi(')):
                    descriptor = line
                    descriptor_line_index = i
                    break
            
            if not descriptor:
                _logger.error("No valid descriptor found in BSMS file")
                _logger.error("Expected a line starting with: wsh(...), sh(...), tr(...), sortedmulti(...), or multi(...)")
                return None
            
            _logger.info(f"Found BSMS descriptor at line {descriptor_line_index}: {descriptor}")
            
            # Remove the descriptor line from lines for metadata parsing
            remaining_lines = lines[:descriptor_line_index] + lines[descriptor_line_index + 1:]
            
            # Extract script type and inner content
            if descriptor.startswith('wsh('):
                script_type = 'p2wsh'
                inner = descriptor[4:-1]  # Remove wsh() wrapper
            elif descriptor.startswith('sh('):
                script_type = 'p2sh'
                inner = descriptor[3:-1]  # Remove sh() wrapper
            elif descriptor.startswith('tr('):
                script_type = 'p2tr'
                inner = descriptor[3:-1]  # Remove tr() wrapper
            elif descriptor.startswith(('sortedmulti(', 'multi(')):
                # Bare multisig (assume P2WSH for modern usage)
                script_type = 'p2wsh'
                inner = descriptor
            else:
                script_type = 'unknown'
                inner = descriptor
            
            _logger.info(f"Script type: {script_type}, Inner: {inner[:100]}...")
            
            # Parse sortedmulti or multi
            if 'sortedmulti(' in inner:
                multi_start = inner.find('sortedmulti(') + 12
                multi_content = inner[multi_start:-1]
                sorted_keys = True
            elif 'multi(' in inner:
                multi_start = inner.find('multi(') + 6
                multi_content = inner[multi_start:-1]
                sorted_keys = False
            else:
                _logger.error(f"No multisig found in descriptor: {inner}")
                return None
            
            _logger.info(f"Multi content: {multi_content[:100]}...")
            
            # Parse M threshold and XPUBs
            parts = multi_content.split(',')
            if len(parts) < 2:
                _logger.error(f"Invalid multisig format: {multi_content}")
                return None
            
            m_threshold = int(parts[0].strip())
            
            # Extract XPUBs, handling derivation paths in brackets
            xpubs = []
            derivation_paths = []
            
            for part in parts[1:]:
                part = part.strip()
                _logger.info(f"Processing XPUB part: {part}")
                
                if '[' in part and ']' in part:
                    # Extract derivation path and XPUB
                    bracket_start = part.find('[')
                    bracket_end = part.find(']')
                    derivation_path = part[bracket_start+1:bracket_end]
                    xpub = part[bracket_end+1:]
                    derivation_paths.append(derivation_path)
                else:
                    # Just XPUB without derivation path
                    xpub = part
                    derivation_paths.append('')
                
                xpubs.append(xpub.strip())
                _logger.info(f"Extracted XPUB: {xpub[:20]}... with derivation: {derivation_paths[-1]}")
            
            n_total = len(xpubs)
            
            _logger.info(f"Parsed: {m_threshold}-of-{n_total} {script_type}")
            
            # Handle additional BSMS metadata
            metadata = {'version': '1.0'}  # Default BSMS version
            derivation_pattern = ''
            sample_address = ''
            
            # Parse remaining lines (excluding the descriptor)
            for line in remaining_lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Check for BSMS version
                if line.startswith('BSMS '):
                    metadata['version'] = line.replace('BSMS ', '').strip()
                # Check for derivation pattern
                elif line.startswith('/') and ('*' in line or ',' in line):
                    derivation_pattern = line
                # Check for sample address (Bitcoin address)
                elif line.startswith(('1', '3', 'bc1')):
                    sample_address = line
                # Check for key:value metadata
                elif ':' in line:
                    key, value = line.split(':', 1)
                    metadata[key.strip().lower()] = value.strip()
                else:
                    # Unknown line, add to metadata
                    metadata['additional_data'] = metadata.get('additional_data', []) + [line]
            
            _logger.info(f"Metadata: {metadata}")
            _logger.info(f"Derivation pattern: {derivation_pattern}")
            _logger.info(f"Sample address: {sample_address}")
            
            return {
                'descriptor': descriptor,
                'script_type': script_type,
                'm': m_threshold,
                'n': n_total,
                'xpubs': xpubs,
                'derivation_paths': derivation_paths,
                'derivation_pattern': derivation_pattern,
                'sample_address': sample_address,
                'sorted_keys': sorted_keys,
                'metadata': metadata,
                'name': metadata.get('name', f'{m_threshold}-of-{n_total} Multisig Wallet')
            }
            
        except Exception as e:
            _logger.error(f"BSMS parsing failed: {str(e)}")
            return None

    def action_import_bsms(self):
        """Import the BSMS file and create/update multisig wallet"""
        self.ensure_one()
        
        if not self.bsms_valid:
            raise ValidationError("Invalid BSMS file. Please check the format and try again.")
        
        if not self.bsms_file:
            raise ValidationError("No BSMS file uploaded")
        
        try:
            # Parse BSMS data
            file_content = base64.b64decode(self.bsms_file)
            bsms_text = file_content.decode('utf-8').strip()
            bsms_data = self._parse_bsms_content(bsms_text)
            
            if not bsms_data:
                raise ValidationError("Failed to parse BSMS file")
            
            _logger.info(f"Creating multisig wallet from BSMS: {bsms_data['name']}")
            _logger.info(f"BSMS data parsed: M={bsms_data['m']}, N={bsms_data['n']}, XPUBs={len(bsms_data['xpubs'])}")
            
            # Create multisig wallet
            wallet_data = {
                'name': bsms_data['name'],
                'm_of_n_threshold': bsms_data['m'],
                'total_cosigners': bsms_data['n'],
                'script_type': self._map_script_type(bsms_data['script_type']),
                'notes': f'Imported from BSMS file: {self.bsms_filename or "unknown"}',
                'sorted_keys': bsms_data.get('sorted_keys', True),
            }
            
            # Add derivation path if found in metadata
            if 'derivation' in bsms_data['metadata']:
                wallet_data['derivation_path'] = bsms_data['metadata']['derivation']
            
            _logger.info(f"Creating wallet with data: {wallet_data}")
            wallet = self.env['crypto.bitcoin.multisig.wallet'].create(wallet_data)
            _logger.info(f"Created wallet with ID: {wallet.id}")
            
            # Create public key records for each XPUB
            _logger.info(f"Starting cosigner creation: {len(bsms_data['xpubs'])} XPUBs to process")
            created_cosigners = 0
            updated_cosigners = 0
            for i, xpub in enumerate(bsms_data['xpubs'], 1):
                # Get the corresponding derivation path for this cosigner
                derivation_path = ''
                if i <= len(bsms_data['derivation_paths']):
                    derivation_path = bsms_data['derivation_paths'][i-1]
                
                _logger.info(f"Processing cosigner {i}: XPUB={xpub[:20]}..., derivation={derivation_path}")
                
                # Check if this XPUB already exists using hash-based lookup
                xpub_hash = self.env['crypto.bitcoin.public.key'].compute_xpub_hash_static(xpub, derivation_path)
                _logger.info(f"Looking up cosigner {i} with hash: {xpub_hash[:16]}...")
                existing_key = self.env['crypto.bitcoin.public.key'].search([
                    ('xpub_hash', '=', xpub_hash)
                ], limit=1)
                
                if existing_key:
                    _logger.info(f"Found existing public key for XPUB {i}: {existing_key.id}, key_type: {existing_key.key_type}")
                    public_key = existing_key
                    # Update existing key with multisig wallet and derivation path
                    existing_key.write({
                        'key_type': 'multisig',  # Ensure key_type is set to multisig
                        'multisig_wallet_id': wallet.id,
                        'derivation_path': derivation_path,
                        'script_type': self._map_script_type(bsms_data['script_type']),
                        'cosigner_index': i - 1,  # 0-based index
                    })
                    # Ensure XPUB is set (in case it wasn't stored in vault before)
                    existing_key.xpub = xpub
                    updated_cosigners += 1
                    _logger.info(f"Updated existing cosigner {i}, set key_type to multisig")
                else:
                    # Create new public key record
                    key_data = {
                        'name': f'Cosigner {i} ({bsms_data["name"]})',
                        'key_type': 'multisig',
                        'notes': f'Imported from BSMS file for {bsms_data["name"]}',
                        'derivation_path': derivation_path,
                        'script_type': self._map_script_type(bsms_data['script_type']),
                        'cosigner_index': i - 1,  # 0-based index
                        'multisig_wallet_id': wallet.id,
                    }
                    
                    _logger.info(f"Creating public key {i}: {key_data['name']}")
                    try:
                        public_key = self.env['crypto.bitcoin.public.key'].create(key_data)
                        _logger.info(f"Created public key with ID: {public_key.id}")
                        
                        # Set XPUB after creation (since it needs token_uuid to be set first)
                        public_key.xpub = xpub
                        _logger.info(f"Set XPUB for cosigner {i}: {xpub[:20]}...")
                        
                        created_cosigners += 1
                    except Exception as create_error:
                        _logger.error(f"Failed to create cosigner {i}: {str(create_error)}")
                        raise ValidationError(f"Failed to create cosigner {i}: {str(create_error)}")
            
            _logger.info(f"BSMS import complete: Created {created_cosigners} new cosigners, updated {updated_cosigners} existing cosigners")
            
            # Verify the cosigner relationship
            wallet.invalidate_cache()  # Force reload from database
            linked_cosigners = wallet.cosigner_public_key_ids
            _logger.info(f"Verification: Wallet {wallet.id} now has {len(linked_cosigners)} linked cosigners")
            for cosigner in linked_cosigners:
                _logger.info(f"  - Cosigner ID: {cosigner.id}, Name: {cosigner.name}, Key Type: {cosigner.key_type}")
            
            # Return action to view the created wallet
            return {
                'type': 'ir.actions.act_window',
                'name': 'Imported Multisig Wallet',
                'res_model': 'crypto.bitcoin.multisig.wallet',
                'res_id': wallet.id,
                'view_mode': 'form',
                'target': 'current',
            }
            
        except Exception as e:
            _logger.error(f"Failed to import BSMS: {str(e)}", exc_info=True)
            raise ValidationError(f"BSMS import failed: {str(e)}")

    def _map_script_type(self, bsms_script_type):
        """Map BSMS script type to internal script type"""
        mapping = {
            'p2wsh': 'p2wsh',
            'p2sh': 'p2sh_p2wsh',  # Assume wrapped segwit for P2SH
            'p2tr': 'p2tr',
        }
        return mapping.get(bsms_script_type, 'p2wsh')  # Default to native segwit