# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, api
from odoo.exceptions import ValidationError
import base58
import hashlib
import hmac
import struct
import logging
from ecdsa import SigningKey, SECP256k1
from ecdsa.util import string_to_number, number_to_string
from ecdsa.ellipticcurve import Point

_logger = logging.getLogger(__name__)

class CryptoBip32Utils(models.AbstractModel):
    _name = 'crypto.bip32.utils'
    _description = 'Bitcoin BIP32 Utility Functions'

    @api.model
    def derive_child_key(self, parent_key, parent_chain_code, index, hardened=False, is_private=True):
        """
        BIP32 child key derivation using proper secp256k1 elliptic curve math
        
        Args:
            parent_key (bytes): Parent key (private or public)
            parent_chain_code (bytes): Parent chain code  
            index (int): Child index
            hardened (bool): Whether to use hardened derivation
            is_private (bool): Whether parent_key is private key
            
        Returns:
            tuple: (child_key, child_chain_code)
        """
        if hardened:
            index = index | 0x80000000
            
        if index >= 0x80000000:  # Hardened derivation
            if not is_private:
                raise ValidationError("Cannot derive hardened keys from public key")
                
            # Use private key for hardened derivation
            if len(parent_key) == 33 and parent_key[0] == 0x00:
                # XPRV format - remove padding
                private_key = parent_key[1:]
            else:
                private_key = parent_key[:32]
            data = b'\x00' + private_key + struct.pack('>I', index)
        else:
            # Non-hardened derivation
            if is_private:
                # Generate public key from private key first
                if len(parent_key) == 33 and parent_key[0] == 0x00:
                    private_key_raw = parent_key[1:]
                else:
                    private_key_raw = parent_key[:32]
                    
                # Get public key using secp256k1
                private_key_int = string_to_number(private_key_raw)
                signing_key = SigningKey.from_secret_exponent(private_key_int, curve=SECP256k1)
                verifying_key = signing_key.get_verifying_key()
                point = verifying_key.pubkey.point
                x_coord = number_to_string(point.x(), SECP256k1.order)
                
                # Use compressed public key
                if point.y() % 2 == 0:
                    public_key = b'\x02' + x_coord
                else:
                    public_key = b'\x03' + x_coord
                    
                data = public_key + struct.pack('>I', index)
            else:
                # Use parent public key directly
                data = parent_key + struct.pack('>I', index)
            
        hmac_result = hmac.new(parent_chain_code, data, hashlib.sha512).digest()
        
        child_private_scalar = hmac_result[:32]
        child_chain_code = hmac_result[32:]
        
        # Generate child key using proper secp256k1 math
        if is_private:
            # For private keys: child_private_key = (parent_private_key + child_private_scalar) mod n
            if len(parent_key) == 33 and parent_key[0] == 0x00:
                parent_private_raw = parent_key[1:]
            else:
                parent_private_raw = parent_key[:32]
                
            parent_private_int = string_to_number(parent_private_raw)
            child_private_scalar_int = string_to_number(child_private_scalar)
            
            # Add the scalars modulo the curve order
            child_private_int = (parent_private_int + child_private_scalar_int) % SECP256k1.order
            
            # Convert back to bytes with padding for XPRV format
            child_private_bytes = number_to_string(child_private_int, SECP256k1.order)
            child_key = b'\x00' + child_private_bytes
        else:
            # For public keys: child_public_key = parent_public_key + child_private_scalar * G
            # Parse parent public key and perform point addition
            if len(parent_key) != 33 or parent_key[0] not in (0x02, 0x03):
                raise ValidationError("Invalid compressed public key format")
            
            # Get parent public key point
            x_coord = string_to_number(parent_key[1:])
            y_squared = (pow(x_coord, 3, SECP256k1.generator.curve().p()) + 7) % SECP256k1.generator.curve().p()
            y_coord = pow(y_squared, (SECP256k1.generator.curve().p() + 1) // 4, SECP256k1.generator.curve().p())
            
            # Adjust y coordinate based on compression flag
            if parent_key[0] == 0x02 and y_coord % 2 != 0:
                y_coord = SECP256k1.generator.curve().p() - y_coord
            elif parent_key[0] == 0x03 and y_coord % 2 == 0:
                y_coord = SECP256k1.generator.curve().p() - y_coord
                
            # Create parent point
            parent_point = Point(SECP256k1.generator.curve(), x_coord, y_coord)
            
            # Create scalar point (child_private_scalar * G)
            child_private_scalar_int = string_to_number(child_private_scalar)
            scalar_point = SECP256k1.generator * child_private_scalar_int
            
            # Add points: child_public_point = parent_point + scalar_point
            child_point = parent_point + scalar_point
            
            # Convert back to compressed public key
            x_coord = number_to_string(child_point.x(), SECP256k1.order)
            if child_point.y() % 2 == 0:
                child_key = b'\x02' + x_coord
            else:
                child_key = b'\x03' + x_coord
        
        return child_key, child_chain_code

    @api.model
    def xprv_to_xpub(self, xprv):
        """
        Convert XPRV to XPUB using proper secp256k1 elliptic curve cryptography
        
        Args:
            xprv (str): Extended private key
            
        Returns:
            str: Extended public key
        """
        try:
            # Parse XPRV
            decoded = base58.b58decode_check(xprv)
            if len(decoded) != 78:
                raise ValidationError("Invalid XPRV length")
            
            # Extract components
            version = decoded[:4]
            depth = decoded[4:5]
            parent_fingerprint = decoded[5:9]
            child_number = decoded[9:13]
            chain_code = decoded[13:45]
            private_key_bytes = decoded[45:78]
            
            # Convert version from private to public
            if version == b'\x04\x88\xAD\xE4':  # xprv mainnet
                pub_version = b'\x04\x88\xB2\x1E'  # xpub mainnet
            elif version == b'\x04\x35\x83\x94':  # tprv testnet  
                pub_version = b'\x04\x35\x87\xCF'  # tpub testnet
            else:
                raise ValidationError("Unknown XPRV version")
            
            # Extract private key (remove padding if present)
            if private_key_bytes[0] == 0x00:
                private_key_raw = private_key_bytes[1:]
            else:
                private_key_raw = private_key_bytes[:32]
                
            # Generate public key using proper secp256k1 elliptic curve
            private_key_int = string_to_number(private_key_raw)
            signing_key = SigningKey.from_secret_exponent(private_key_int, curve=SECP256k1)
            verifying_key = signing_key.get_verifying_key()
            
            # Get compressed public key (33 bytes: 0x02/0x03 + 32-byte x coordinate)
            point = verifying_key.pubkey.point
            x_coord = number_to_string(point.x(), SECP256k1.order)
            
            # Use compressed format: 0x02 if y is even, 0x03 if y is odd
            if point.y() % 2 == 0:
                pub_key = b'\x02' + x_coord
            else:
                pub_key = b'\x03' + x_coord
            
            # Construct XPUB
            xpub_data = pub_version + depth + parent_fingerprint + child_number + chain_code + pub_key
            
            # Encode as base58check
            xpub = base58.b58encode_check(xpub_data).decode('ascii')
            return xpub
            
        except Exception as e:
            _logger.error(f"Failed to convert XPRV to XPUB: {str(e)}")
            raise ValidationError(f"XPRV to XPUB conversion failed: {str(e)}")

    @api.model
    def derive_bip44_account(self, master_xprv, account_index, coin_type=0):
        """
        Derive BIP44 account-level keys: m/44'/coin_type'/account'
        
        Args:
            master_xprv (str): Master extended private key
            account_index (int): Account index (0-based)
            coin_type (int): Coin type (0=Bitcoin, 1=Testnet)
            
        Returns:
            dict: Account derivation info
        """
        try:
            # Parse master XPRV
            decoded = base58.b58decode_check(master_xprv)
            if len(decoded) != 78:
                raise ValidationError("Invalid master XPRV format")
                
            master_chain_code = decoded[13:45]
            master_private_key = decoded[45:78]
            
            # Derive m/44' (purpose)
            purpose_key, purpose_chain = self.derive_child_key(
                master_private_key, master_chain_code, 44, hardened=True, is_private=True
            )
            
            # Derive m/44'/coin_type' (coin type)
            coin_key, coin_chain = self.derive_child_key(
                purpose_key, purpose_chain, coin_type, hardened=True, is_private=True
            )
            
            # Derive m/44'/coin_type'/account' (account)
            account_key, account_chain = self.derive_child_key(
                coin_key, coin_chain, account_index, hardened=True, is_private=True
            )
            
            # Construct account-level XPRV
            version = b'\x04\x88\xAD\xE4'  # xprv mainnet version
            depth = b'\x03'  # Account level depth
            
            # Calculate parent fingerprint (from coin-level public key)
            coin_public_key = self._private_key_to_public_key(coin_key)
            parent_fingerprint = self._hash160(coin_public_key)[:4]
            
            # Calculate account fingerprint (unique for this account)
            account_public_key = self._private_key_to_public_key(account_key)
            account_fingerprint = self._hash160(account_public_key)[:4]
            child_number = struct.pack('>I', account_index | 0x80000000)
            
            account_xprv_data = version + depth + parent_fingerprint + child_number + account_chain + account_key
            account_xprv = base58.b58encode_check(account_xprv_data).decode('ascii')
            
            # Derive corresponding XPUB
            account_xpub = self.xprv_to_xpub(account_xprv)
            
            return {
                'account_index': account_index,
                'coin_type': coin_type,
                'path': f"m/44'/{coin_type}'/{account_index}'",
                'xprv': account_xprv,
                'xpub': account_xpub,
                'depth': 3,
                'fingerprint': account_fingerprint.hex(),
                'chain_code': account_chain.hex()
            }
            
        except Exception as e:
            _logger.error(f"Failed to derive BIP44 account: {str(e)}")
            raise ValidationError(f"Account derivation failed: {str(e)}")

    @api.model
    def derive_address_from_xpub(self, xpub, change, index, base_path="m", address_type="bech32"):
        """
        Universal address derivation from any XPUB
        
        Args:
            xpub (str): Extended public key (master or account level)
            change (int): 0 for receive, 1 for change
            index (int): Address index
            base_path (str): Base derivation path for display
            address_type (str): Address type - 'p2pkh', 'p2sh', 'bech32', 'taproot'
            
        Returns:
            dict: Address derivation info
        """
        try:
            # Parse XPUB
            decoded = base58.b58decode_check(xpub)
            if len(decoded) != 78:
                raise ValidationError("Invalid XPUB format")
                
            chain_code = decoded[13:45]
            public_key = decoded[45:78]
            
            # Derive change-level key: xpub/change
            change_key, change_chain = self.derive_child_key(
                public_key, chain_code, change, hardened=False, is_private=False
            )
            
            # Derive final address key: xpub/change/index
            final_key, _ = self.derive_child_key(
                change_key, change_chain, index, hardened=False, is_private=False
            )
            
            # Generate address from final key based on type
            pubkey_hash = self._hash160(final_key)
            
            if address_type == "p2pkh":
                # Legacy P2PKH - starts with '1'
                address = self._create_p2pkh_address(pubkey_hash)
            elif address_type == "p2sh":
                # Nested SegWit P2SH - starts with '3'
                # For P2SH-P2WPKH, we hash the witness script (0x0014 + pubkey_hash)
                witness_script = b'\x00\x14' + pubkey_hash  # OP_0 + 20-byte pubkey hash
                script_hash = self._hash160(witness_script)
                address = self._create_p2sh_address(script_hash)
            elif address_type == "taproot":
                # Taproot - starts with 'bc1p'  
                address = self._create_bech32_address(pubkey_hash, version=1)
            else:
                # Native SegWit (bech32) - starts with 'bc1q'
                address = self._create_bech32_address(pubkey_hash, version=0)
            
            return {
                'index': index,
                'change': change,
                'path': f"{base_path}/{change}/{index}",
                'address': address,
                'public_key': final_key.hex(),
                'address_type': address_type
            }
            
        except Exception as e:
            _logger.error(f"Failed to derive address from XPUB: {str(e)}")
            raise ValidationError(f"Address derivation failed: {str(e)}")

    @api.model
    def derive_address_from_account_xpub(self, account_xpub, change, index):
        """
        Derive address from account-level XPUB: m/44'/0'/account'/change/index
        (Legacy method - now uses unified derivation)
        
        Args:
            account_xpub (str): Account-level XPUB
            change (int): 0 for receive, 1 for change
            index (int): Address index
            
        Returns:
            dict: Address derivation info
        """
        # Use unified derivation with generic account path
        # The actual path will be updated by the calling public key model
        return self.derive_address_from_xpub(
            account_xpub, change, index, base_path="m/44'/0'/account'"
        )

    @api.model
    def derive_bip48_multisig(self, master_xprv, account_index, script_type, cosigner_index=0, coin_type=0):
        """
        Derive BIP48 multisig keys: m/48'/coin_type'/account'/script_type'
        
        Args:
            master_xprv (str): Master extended private key
            account_index (int): Account index (0-based)
            script_type (str): 'p2sh', 'p2wsh', or 'p2sh_p2wsh'
            cosigner_index (int): Cosigner index for this key
            coin_type (int): Coin type (0=Bitcoin, 1=Testnet)
            
        Returns:
            dict: Multisig derivation info
        """
        try:
            # Map script types to BIP48 script type numbers
            script_type_map = {
                'p2sh': 1,        # P2SH multisig
                'p2wsh': 2,       # P2WSH native segwit multisig  
                'p2sh_p2wsh': 3   # P2SH-wrapped P2WSH multisig
            }
            
            if script_type not in script_type_map:
                raise ValidationError(f"Unsupported script type: {script_type}")
                
            script_type_num = script_type_map[script_type]
            
            # Parse master XPRV
            decoded = base58.b58decode_check(master_xprv)
            if len(decoded) != 78:
                raise ValidationError("Invalid master XPRV format")
                
            master_chain_code = decoded[13:45]
            master_private_key = decoded[45:78]
            
            # Derive m/48' (purpose)
            purpose_key, purpose_chain = self.derive_child_key(
                master_private_key, master_chain_code, 48, hardened=True, is_private=True
            )
            
            # Derive m/48'/coin_type' (coin type)
            coin_key, coin_chain = self.derive_child_key(
                purpose_key, purpose_chain, coin_type, hardened=True, is_private=True
            )
            
            # Derive m/48'/coin_type'/account' (account)
            account_key, account_chain = self.derive_child_key(
                coin_key, coin_chain, account_index, hardened=True, is_private=True
            )
            
            # Derive m/48'/coin_type'/account'/script_type' (script type)
            script_key, script_chain = self.derive_child_key(
                account_key, account_chain, script_type_num, hardened=True, is_private=True
            )
            
            # Construct multisig-level XPRV
            version = b'\x04\x88\xAD\xE4'  # xprv mainnet version
            depth = b'\x04'  # Multisig level depth
            
            # Calculate parent fingerprint (from account-level public key)
            account_public_key = self._private_key_to_public_key(account_key)
            parent_fingerprint = self._hash160(account_public_key)[:4]
            
            # Calculate script-level fingerprint (unique for this multisig setup)
            script_public_key = self._private_key_to_public_key(script_key)
            script_fingerprint = self._hash160(script_public_key)[:4]
            
            child_number = struct.pack('>I', script_type_num | 0x80000000)
            
            multisig_xprv_data = version + depth + parent_fingerprint + child_number + script_chain + script_key
            multisig_xprv = base58.b58encode_check(multisig_xprv_data).decode('ascii')
            
            # Derive corresponding XPUB
            multisig_xpub = self.xprv_to_xpub(multisig_xprv)
            
            return {
                'account_index': account_index,
                'coin_type': coin_type,
                'script_type': script_type,
                'script_type_num': script_type_num,
                'cosigner_index': cosigner_index,
                'path': f"m/48'/{coin_type}'/{account_index}'/{script_type_num}'",
                'xprv': multisig_xprv,
                'xpub': multisig_xpub,
                'depth': 4,
                'fingerprint': script_fingerprint.hex(),
                'chain_code': script_chain.hex()
            }
            
        except Exception as e:
            _logger.error(f"Failed to derive BIP48 multisig: {str(e)}")
            raise ValidationError(f"Multisig derivation failed: {str(e)}")

    @api.model
    def _private_key_to_public_key(self, private_key):
        """Convert private key bytes to compressed public key"""
        # Remove padding if present
        if len(private_key) == 33 and private_key[0] == 0x00:
            private_key_raw = private_key[1:]
        else:
            private_key_raw = private_key[:32]
            
        # Generate public key using secp256k1
        private_key_int = string_to_number(private_key_raw)
        signing_key = SigningKey.from_secret_exponent(private_key_int, curve=SECP256k1)
        verifying_key = signing_key.get_verifying_key()
        point = verifying_key.pubkey.point
        x_coord = number_to_string(point.x(), SECP256k1.order)
        
        # Return compressed public key
        if point.y() % 2 == 0:
            return b'\x02' + x_coord
        else:
            return b'\x03' + x_coord

    @api.model
    def _hash160(self, data):
        """RIPEMD160(SHA256(data)) - Bitcoin's standard hash function"""
        sha256_hash = hashlib.sha256(data).digest()
        try:
            # Use proper RIPEMD160 - required for Bitcoin compatibility
            ripemd160_hash = hashlib.new('ripemd160', sha256_hash).digest()
            return ripemd160_hash
        except ValueError:
            # RIPEMD160 is required for Bitcoin - cannot fallback safely
            raise ValidationError(
                "RIPEMD160 hash function is not available. "
                "This is required for Bitcoin address generation. "
                "Please install a Python version with RIPEMD160 support or use a crypto library that provides it."
            )

    @api.model
    def _convertbits(self, data, frombits, tobits, pad=True):
        """Convert between bit groups for Bech32 encoding"""
        acc = 0
        bits = 0
        ret = []
        maxv = (1 << tobits) - 1
        max_acc = (1 << (frombits + tobits - 1)) - 1
        
        for value in data:
            if value < 0 or (value >> frombits):
                return None
            acc = ((acc << frombits) | value) & max_acc
            bits += frombits
            while bits >= tobits:
                bits -= tobits
                ret.append((acc >> bits) & maxv)
        
        if pad:
            if bits:
                ret.append((acc << (tobits - bits)) & maxv)
        elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
            return None
            
        return ret

    @api.model
    def _bech32_polymod(self, values):
        """Bech32 polymod for checksum calculation"""
        GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
        chk = 1
        for value in values:
            top = chk >> 25
            chk = (chk & 0x1ffffff) << 5 ^ value
            for i in range(5):
                chk ^= GEN[i] if ((top >> i) & 1) else 0
        return chk

    @api.model
    def _bech32_hrp_expand(self, hrp):
        """Expand HRP for Bech32 checksum"""
        return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]

    @api.model
    def _bech32_create_checksum(self, hrp, data):
        """Create Bech32 checksum"""
        values = self._bech32_hrp_expand(hrp) + data
        polymod = self._bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ 1
        return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]

    @api.model
    def _bech32_encode(self, hrp, data):
        """Encode Bech32 address"""
        CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
        combined = data + self._bech32_create_checksum(hrp, data)
        return hrp + '1' + ''.join([CHARSET[d] for d in combined])

    @api.model
    def _create_p2pkh_address(self, pubkey_hash):
        """Create P2PKH (Legacy) address from public key hash - starts with '1'"""
        # P2PKH uses version byte 0x00 for mainnet
        version_byte = b'\x00'
        payload = version_byte + pubkey_hash
        return base58.b58encode_check(payload).decode('ascii')
    
    @api.model
    def _create_p2sh_address(self, script_hash):
        """Create P2SH address from script hash - starts with '3'"""
        # P2SH uses version byte 0x05 for mainnet
        version_byte = b'\x05'
        payload = version_byte + script_hash
        return base58.b58encode_check(payload).decode('ascii')
    
    @api.model
    def _create_bech32_address(self, pubkey_hash, version=0):
        """Create Bech32 address from public key hash"""
        # Convert to 5-bit groups for Bech32
        converted = self._convertbits(pubkey_hash, 8, 5)
        if converted is None:
            raise ValidationError("Failed to convert public key hash for Bech32")
            
        # Create Bech32 address (witness version + pubkey hash)
        if version == 1:
            # Taproot (version 1) uses bc1p prefix
            witness_program = [version] + converted
            return self._bech32_encode('bc', witness_program).replace('bc1q', 'bc1p')
        else:
            # Native SegWit (version 0) uses bc1q prefix  
            witness_program = [version] + converted
            return self._bech32_encode('bc', witness_program)

    @api.model
    def validate_xprv_format(self, xprv):
        """Validate XPRV format"""
        if not xprv or not isinstance(xprv, str):
            return False
            
        if not xprv.startswith(('xprv', 'tprv')):
            return False
            
        try:
            decoded = base58.b58decode_check(xprv)
            return len(decoded) == 78
        except Exception:
            return False

    @api.model
    def validate_xpub_format(self, xpub):
        """Validate XPUB format"""
        if not xpub or not isinstance(xpub, str):
            return False
            
        if not xpub.startswith(('xpub', 'tpub')):
            return False
            
        try:
            decoded = base58.b58decode_check(xpub)
            return len(decoded) == 78
        except Exception:
            return False

    @api.model
    def generate_multisig_address(self, xpubs_with_paths, m_threshold, script_type, change=0, index=0):
        """
        Generate multisig address from multiple XPUBs
        
        Args:
            xpubs_with_paths (list): List of tuples (xpub, derivation_path)
            m_threshold (int): Required signatures (M in M-of-N)
            script_type (str): 'p2sh', 'p2wsh', or 'p2sh_p2wsh'
            change (int): 0 for receive, 1 for change
            index (int): Address index
            
        Returns:
            dict: Address info with address, script, and derived pubkeys
        """
        try:
            # Derive public key from each XPUB at the specified path
            derived_pubkeys = []
            
            for xpub, base_path in xpubs_with_paths:
                # Derive the public key at change/index
                addr_data = self.derive_address_from_xpub(
                    xpub, change, index, base_path=base_path, address_type="bech32"
                )
                derived_pubkeys.append(addr_data['public_key'])
            
            # Create multisig address from derived public keys
            multisig_address = self._create_multisig_address(
                derived_pubkeys, m_threshold, script_type
            )
            
            return {
                'address': multisig_address,
                'change': change,
                'index': index,
                'path': f"m/{change}/{index}",
                'script_type': script_type,
                'derived_pubkeys': derived_pubkeys,
                'm_threshold': m_threshold,
                'n_total': len(derived_pubkeys)
            }
            
        except Exception as e:
            _logger.error(f"Failed to generate multisig address: {str(e)}")
            raise ValidationError(f"Multisig address generation failed: {str(e)}")

    @api.model
    def _create_multisig_address(self, public_keys, m_threshold, script_type):
        """Create multisig address from list of public keys"""
        import hashlib
        
        # Sort public keys for deterministic multisig (as per sortedmulti)
        sorted_pubkeys = sorted(public_keys)
        
        # Create the multisig redeem script
        redeem_script = self._create_multisig_script(sorted_pubkeys, m_threshold)
        
        # Generate address based on script type
        if script_type == 'p2sh':
            # P2SH: hash160(redeem_script)
            script_hash = self._hash160(redeem_script)
            return self._create_p2sh_address(script_hash)
            
        elif script_type == 'p2wsh':
            # P2WSH: SHA256(redeem_script) for witness script
            script_hash = hashlib.sha256(redeem_script).digest()
            return self._create_bech32_address(script_hash, version=0)
            
        elif script_type == 'p2sh_p2wsh':
            # P2SH-wrapped P2WSH: hash160(witness_program)
            witness_script_hash = hashlib.sha256(redeem_script).digest()
            witness_program = bytes([0x00, 0x20]) + witness_script_hash  # OP_0 + 32-byte hash
            script_hash = self._hash160(witness_program)
            return self._create_p2sh_address(script_hash)
            
        else:
            raise ValidationError(f"Unsupported script type: {script_type}")

    @api.model
    def _create_multisig_script(self, sorted_public_keys, m_threshold):
        """Create multisig redeem script from sorted public keys"""
        # Format: OP_M <pubkey1> <pubkey2> ... <pubkeyN> OP_N OP_CHECKMULTISIG
        script_parts = []
        
        # OP_M (required signatures) - OP_1=0x51 through OP_16=0x60
        if 1 <= m_threshold <= 16:
            script_parts.append(bytes([0x50 + m_threshold]))
        else:
            raise ValidationError(f"Invalid M threshold: {m_threshold}")
        
        # Add each public key
        for pubkey_hex in sorted_public_keys:
            pubkey_bytes = bytes.fromhex(pubkey_hex)
            if len(pubkey_bytes) not in [33, 65]:  # Compressed or uncompressed
                raise ValidationError(f"Invalid public key length: {len(pubkey_bytes)}")
            script_parts.append(bytes([len(pubkey_bytes)]))  # Push data length
            script_parts.append(pubkey_bytes)  # Push public key
        
        # OP_N (total public keys)
        n_total = len(sorted_public_keys)
        if 1 <= n_total <= 16:
            script_parts.append(bytes([0x50 + n_total]))
        else:
            raise ValidationError(f"Invalid N total: {n_total}")
        
        # OP_CHECKMULTISIG
        script_parts.append(bytes([0xae]))
        
        return b''.join(script_parts)

    @api.model
    def create_psbt(self, multisig_wallet, outputs, fee_rate_sat_vb=None):
        """
        Create a Partially Signed Bitcoin Transaction (PSBT) for a multisig wallet
        
        Args:
            multisig_wallet: crypto.bitcoin.multisig.wallet record
            outputs: List of dicts with 'address' and 'amount' (in satoshis)
            fee_rate_sat_vb: Target fee rate in sat/vB (optional)
            
        Returns:
            dict: PSBT creation result with base64 PSBT and metadata
        """
        import json
        
        try:
            if not multisig_wallet.is_complete:
                raise ValidationError("Multisig wallet configuration is incomplete")
            
            # For now, create a basic PSBT structure
            # In a real implementation, this would use proper Bitcoin libraries
            # like bitcoinlib or python-bitcointx
            
            # Calculate total output amount
            total_output = sum(output['amount'] for output in outputs)
            
            # Estimate transaction size (rough calculation)
            # Base size + inputs + outputs + multisig overhead
            estimated_size = 50 + (len(outputs) * 35) + (multisig_wallet.m_of_n_threshold * 75)
            
            # Calculate fee
            if fee_rate_sat_vb:
                estimated_fee = int(estimated_size * fee_rate_sat_vb)
            else:
                estimated_fee = int(estimated_size * 5)  # Default 5 sat/vB
            
            total_needed = total_output + estimated_fee
            
            # Create PSBT structure (simplified for demonstration)
            psbt_data = {
                'version': '2.0',
                'global': {
                    'unsigned_tx': {
                        'version': 2,
                        'inputs': [],  # Would be populated with actual UTXOs
                        'outputs': [
                            {
                                'value': output['amount'],
                                'script_pubkey': self._address_to_script_pubkey(output['address'])
                            }
                            for output in outputs
                        ],
                        'locktime': 0
                    },
                    'xpubs': []
                },
                'inputs': [],  # Would contain input-specific data
                'outputs': []  # Would contain output-specific data
            }
            
            # Add multisig wallet XPUBs to global section
            for cosigner in multisig_wallet.cosigner_public_key_ids:
                if cosigner.xpub:
                    psbt_data['global']['xpubs'].append({
                        'xpub': cosigner.xpub,
                        'master_fingerprint': cosigner.master_fingerprint or "00000000",
                        'derivation_path': cosigner.derivation_path or "m/48'/0'/0'/2'"
                    })
            
            # Convert to base64 (placeholder - would use proper PSBT encoding)
            psbt_json = json.dumps(psbt_data, indent=2)
            import base64
            psbt_base64 = base64.b64encode(psbt_json.encode('utf-8')).decode('ascii')
            
            return {
                'psbt_base64': psbt_base64,
                'total_output': total_output,
                'estimated_fee': estimated_fee,
                'total_needed': total_needed,
                'estimated_size': estimated_size,
                'fee_rate': fee_rate_sat_vb or 5,
                'multisig_wallet_id': multisig_wallet.id,
                'outputs': outputs
            }
            
        except Exception as e:
            _logger.error(f"Failed to create PSBT: {str(e)}")
            raise ValidationError(f"PSBT creation failed: {str(e)}")

    @api.model
    def parse_psbt_signatures(self, psbt_base64):
        """
        Parse PSBT to count current signatures
        
        Args:
            psbt_base64 (str): Base64-encoded PSBT
            
        Returns:
            dict: Signature count information
        """
        try:
            # Decode PSBT (placeholder implementation)
            import base64
            import json
            
            psbt_json = base64.b64decode(psbt_base64).decode('utf-8')
            psbt_data = json.loads(psbt_json)
            
            # Count signatures in inputs (simplified)
            signature_count = 0
            input_signatures = []
            
            for input_data in psbt_data.get('inputs', []):
                input_sigs = len(input_data.get('partial_sigs', {}))
                input_signatures.append(input_sigs)
                signature_count = max(signature_count, input_sigs)
            
            return {
                'signature_count': signature_count,
                'input_signatures': input_signatures,
                'is_complete': False  # Would check if all inputs have enough signatures
            }
            
        except Exception as e:
            _logger.warning(f"Failed to parse PSBT signatures: {str(e)}")
            return {
                'signature_count': 0,
                'input_signatures': [],
                'is_complete': False
            }

    @api.model
    def _address_to_script_pubkey(self, address):
        """
        Convert Bitcoin address to script pubkey (simplified implementation)
        
        Args:
            address (str): Bitcoin address
            
        Returns:
            str: Hex-encoded script pubkey
        """
        try:
            if address.startswith('bc1'):
                # Bech32 address - would need proper bech32 decoding
                return f"0014{address[4:44]}"  # Placeholder
            elif address.startswith('3'):
                # P2SH address
                import base58
                decoded = base58.b58decode_check(address)
                script_hash = decoded[1:].hex()
                return f"a914{script_hash}87"
            elif address.startswith('1'):
                # P2PKH address
                import base58
                decoded = base58.b58decode_check(address)
                pubkey_hash = decoded[1:].hex()
                return f"76a914{pubkey_hash}88ac"
            else:
                raise ValidationError(f"Unsupported address format: {address}")
                
        except Exception as e:
            _logger.warning(f"Failed to convert address to script: {str(e)}")
            return "00"  # Placeholder