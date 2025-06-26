# Bitcoin Cryptocurrency Module - Development Context

## Project Overview
This Odoo module provides comprehensive Bitcoin cryptocurrency functionality including hierarchical deterministic wallets, multisig wallet creation, and XPUB-based workflows for secure Bitcoin operations without private key exposure.

## Key Architecture Components

### Core Models
- `crypto.bitcoin.private.key` - Master/seed private keys with BIP32 derivation
- `crypto.bitcoin.public.key` - Extended public keys (XPUBs) for secure operations
- `crypto.bitcoin.multisig.wallet` - M-of-N multisig wallet coordination
- `crypto.bitcoin.address` - Individual Bitcoin addresses
- `crypto.bitcoin.wallet` - Legacy wallet containers
- `crypto.bip32.utils` - Core Bitcoin cryptography utilities

### Cryptography Implementation
- **Library Used**: `ecdsa` for secp256k1 elliptic curve operations
- **Standards**: BIP32 (HD wallets), BIP44/49/84/86 (derivation paths), BIP48 (multisig), BIP129 (BSMS)
- **Critical Fix Applied**: Replaced SHA256 with proper secp256k1 + RIPEMD160 for Bitcoin compatibility
- **Address Types**: P2PKH (1...), P2SH (3...), P2WPKH (bc1q...), P2TR (bc1p...)

### Derivation Path Standards
- **BIP44** (Legacy): `m/44'/0'/account'/change/index` ’ P2PKH addresses (1...)
- **BIP49** (Nested SegWit): `m/49'/0'/account'/change/index` ’ P2SH addresses (3...)
- **BIP84** (Native SegWit): `m/84'/0'/account'/change/index` ’ P2WPKH addresses (bc1q...)
- **BIP86** (Taproot): `m/86'/0'/account'/change/index` ’ P2TR addresses (bc1p...)
- **BIP48** (Multisig): `m/48'/0'/account'/script_type'/change/index`

## Major Development History

### Phase 1: Initial XPUB Display (Completed)
Added derivation paths panel to private key details showing XPUBs for different address types with sample addresses.

### Phase 2: Cryptography Fixes (Completed)
**Problem**: XPUBs didn't match Electrum wallet outputs for same mnemonic
**Root Cause**: Using SHA256 instead of secp256k1 elliptic curve cryptography
**Solution**: 
- Added `ecdsa` library dependency
- Implemented proper secp256k1 public key generation in `crypto_bip32_utils.py`
- Fixed XPRV to XPUB conversion with elliptic curve math
- Implemented proper child key derivation
- Added RIPEMD160 HASH160 function (critical for Bitcoin address generation)

### Phase 3: Address Derivation (Completed)
**Problem**: "Public key derivation not yet implemented" errors
**Solution**: Implemented elliptic curve point addition for non-hardened key derivation

### Phase 4: Address Type Corrections (Completed)
**Problem**: BIP44/BIP49 generating bc1q addresses instead of 1.../3... addresses
**Solution**: Fixed address generation to use correct encoding for each derivation path

### Phase 5: XPUB-Only Workflows (Completed)
**Problem**: No way to create public keys without exposing private keys (needed for multisig)
**Solution**: Created comprehensive XPUB import workflow:
- `wizard.import.xpub` model and views for structured XPUB import
- Enhanced `crypto.bitcoin.public.key` to support XPUB-only creation
- Updated multisig wallet with BSMS file generation for professional workflows

### Phase 6: UI Enhancements (Completed)
**Problem**: No "Create" button in Public Keys list view
**Solution**: Enabled create functionality in public key views with XPUB import guidance

## Current Status: COMPLETE 

All requested functionality has been implemented:
-  Private key derivation paths panel with XPUBs and sample addresses
-  Bitcoin cryptography compatibility with Electrum and other standard wallets
-  Address derivation working for all supported derivation paths
-  Correct address formats for each Bitcoin standard (BIP44/49/84/86)
-  XPUB-only import workflow for multisig without private key exposure
-  Professional multisig wallet creation with BSMS file generation
-  Proper "Create" button in Public Keys list view

## Security Considerations

### Implemented Safeguards
- Private keys stored in HashiCorp Vault via `vault.connector`
- XPUBs can be imported without private key exposure
- Address derivation limits (max 10,000 addresses, configurable batch size)
- Proper access control with Bitcoin user groups
- Input validation for all XPUB imports
- No fallback to insecure algorithms (fail-fast on missing RIPEMD160)

### Critical Security Notes
- **NEVER** store private keys in database - use Vault only
- **NEVER** log or display private key material
- RIPEMD160 is required - SHA256 fallback would corrupt Bitcoin data
- All cryptographic operations use standard secp256k1 curve

## Testing and Validation

### Test Vectors Used
- BIP32 official test vectors for key derivation
- Electrum wallet outputs for real-world validation
- Test mnemonic: "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
- Verified XPUB matches: `xpub6BosfCnifzxcFwrSzQiqu2DBVTshkCXacvNsWGYJVVhhawA7d4R5WSWGFNbi8Aw6ZRc1brxMyWMzG3DSSSSoekkudhUd9yLb6qx39T9nMdj`

### Test Files
- `tests/test_crypto_bip32_utils.py` - Comprehensive BIP32 implementation tests

## Dependencies
- `ecdsa` - secp256k1 elliptic curve cryptography (REQUIRED)
- `base58` - Bitcoin address encoding
- `hashlib` - SHA256, RIPEMD160 for Bitcoin HASH160
- Standard Odoo dependencies

## Key File Locations

### Models
- `models/crypto_bip32_utils.py` - Core Bitcoin cryptography (CRITICAL)
- `models/crypto_bitcoin_private_key.py` - HD wallet private keys
- `models/crypto_bitcoin_public_key.py` - XPUB management and address derivation
- `models/crypto_bitcoin_multisig_wallet.py` - Multisig coordination with BSMS
- `models/wizard_import_xpub.py` - XPUB import wizard

### Views
- `views/crypto_bitcoin_private_key_views.xml` - Derivation paths panel
- `views/crypto_bitcoin_public_key_views.xml` - XPUB import and management
- `views/crypto_bitcoin_multisig_wallet_views.xml` - Multisig setup UI
- `views/wizard_import_xpub.xml` - XPUB import wizard UI

## Common Operations

### Create Private Key with Derivation Paths
1. Navigate to Bitcoin ’ Key Management ’ Private Keys
2. Click "Create" to launch wizard
3. View derivation paths panel showing XPUBs and sample addresses for BIP44/49/84/86

### Import XPUB for Multisig
1. Navigate to Bitcoin ’ Key Management ’ Public Keys
2. Click "Create" 
3. Set key type to "Cosigner Key" for multisig
4. Paste XPUB and configure settings
5. Use "Derive Addresses" to generate receiving addresses

### Create Multisig Wallet
1. Navigate to Bitcoin ’ Multisig Wallets
2. Click "Create"
3. Configure M-of-N threshold and script type
4. Add cosigner public keys (from XPUB imports)
5. Download BSMS file for wallet software integration

## Troubleshooting

### XPUB Mismatch with Other Wallets
- Ensure `ecdsa` library is installed
- Verify derivation path matches (case-sensitive)
- Check that both wallets use same passphrase (if any)

### Address Derivation Errors
- Verify XPUB is valid and accessible from Vault
- Check derivation limits and permissions
- Ensure proper network configuration (mainnet/testnet)

### Multisig Setup Issues
- All cosigners must use same derivation path and script type
- XPUB order matters for deterministic address generation
- Test with small amounts before production use

## Future Development Notes
- Consider implementing BIP174 (PSBT) for transaction coordination
- Hardware wallet integration via device APIs
- Lightning Network support through separate module
- Enhanced fee estimation and UTXO management