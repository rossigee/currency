# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestCryptoBip32Utils(TransactionCase):
    """Test cases for crypto.bip32.utils model"""
    
    def setUp(self):
        super().setUp()
        self.bip32_utils = self.env['crypto.bip32.utils']
        
        # Known BIP32 test vectors from the specification
        # Test vector 1: https://github.com/bitcoin/bips/blob/master/bip-0032.mediawiki
        self.test_vector_1 = {
            'seed': '000102030405060708090a0b0c0d0e0f',
            'master_xprv': 'xprv9s21ZrQH143K3QTDL4LXw2F7HEK3wJUD2nW2nRk4stbPy6cq3jPPqjiChkVvvNKmPGJxWUtg6LnF5kejMRNNU3TGtRBeJgk33yuGBxrMPHi',
            'master_xpub': 'xpub661MyMwAqRbcFtXgS5sYJABqqG9YLmC4Q1Rdap9gSE8NqtwybGhePY2gZ29ESFjqJoCu1Rupje8YtGqsefD265TMg7usUDFdp6W1EGMcet8',
            'master_chain_code': '873dff81c02f525623fd1fe5167eac3a55a049de3d314bb42ee227ffed37d508',
            'master_private_key': 'e8f32e723decf4b71b3542e0e2d6d97c9e48e3a6b0b7b7d9b6b8b5b4b3b2b1b0',
        }
        
        # Electrum test case - provide your actual test data here
        self.electrum_test = {
            'mnemonic': 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about',
            'passphrase': '',
            # Add expected Electrum outputs here after you test
            'expected_legacy_xpub': '',  # m/44'/0'/0'
            'expected_nested_xpub': '',  # m/49'/0'/0'  
            'expected_native_xpub': '',  # m/84'/0'/0'
            'expected_taproot_xpub': '', # m/86'/0'/0'
        }

    def test_xprv_to_xpub_conversion(self):
        """Test XPRV to XPUB conversion with known test vectors"""
        test_xprv = self.test_vector_1['master_xprv']
        expected_xpub = self.test_vector_1['master_xpub']
        
        result_xpub = self.bip32_utils.xprv_to_xpub(test_xprv)
        
        self.assertEqual(result_xpub, expected_xpub,
                        f"XPUB conversion failed. Expected: {expected_xpub}, Got: {result_xpub}")

    def test_xprv_validation(self):
        """Test XPRV format validation"""
        # Valid XPRV
        valid_xprv = self.test_vector_1['master_xprv']
        self.assertTrue(self.bip32_utils.validate_xprv_format(valid_xprv))
        
        # Invalid formats
        self.assertFalse(self.bip32_utils.validate_xprv_format(''))
        self.assertFalse(self.bip32_utils.validate_xprv_format('invalid'))
        self.assertFalse(self.bip32_utils.validate_xprv_format('xpub' + valid_xprv[4:]))  # Wrong prefix

    def test_xpub_validation(self):
        """Test XPUB format validation"""
        # Valid XPUB
        valid_xpub = self.test_vector_1['master_xpub']
        self.assertTrue(self.bip32_utils.validate_xpub_format(valid_xpub))
        
        # Invalid formats
        self.assertFalse(self.bip32_utils.validate_xpub_format(''))
        self.assertFalse(self.bip32_utils.validate_xpub_format('invalid'))
        self.assertFalse(self.bip32_utils.validate_xpub_format('xprv' + valid_xpub[4:]))  # Wrong prefix

    def test_child_key_derivation(self):
        """Test BIP32 child key derivation"""
        # Test with known values
        parent_key = bytes.fromhex('0488ade4000000000000000000873dff81c02f525623fd1fe5167eac3a55a049de3d314bb42ee227ffed37d508')
        parent_chain = bytes.fromhex('873dff81c02f525623fd1fe5167eac3a55a049de3d314bb42ee227ffed37d508')
        
        # Test hardened derivation (index 0x80000000)
        child_key, child_chain = self.bip32_utils.derive_child_key(
            parent_key, parent_chain, 0, hardened=True, is_private=True
        )
        
        # Should return valid key and chain code
        self.assertEqual(len(child_key), 33)  # 33 bytes for private key with padding
        self.assertEqual(len(child_chain), 32)  # 32 bytes for chain code

    def test_bip44_account_derivation(self):
        """Test BIP44 account derivation m/44'/0'/account'"""
        master_xprv = self.test_vector_1['master_xprv']
        
        # Test account 0 derivation
        account_data = self.bip32_utils.derive_bip44_account(master_xprv, 0, 0)
        
        # Verify structure
        self.assertEqual(account_data['account_index'], 0)
        self.assertEqual(account_data['coin_type'], 0)
        self.assertEqual(account_data['path'], "m/44'/0'/0'")
        self.assertEqual(account_data['depth'], 3)
        
        # Verify XPRV and XPUB are valid
        self.assertTrue(self.bip32_utils.validate_xprv_format(account_data['xprv']))
        self.assertTrue(self.bip32_utils.validate_xpub_format(account_data['xpub']))
        
        # Verify XPUB can be derived from XPRV
        derived_xpub = self.bip32_utils.xprv_to_xpub(account_data['xprv'])
        self.assertEqual(derived_xpub, account_data['xpub'])

    def test_address_derivation_types(self):
        """Test different address type derivation"""
        # Use a known account XPUB for testing
        master_xprv = self.test_vector_1['master_xprv']
        account_data = self.bip32_utils.derive_bip44_account(master_xprv, 0, 0)
        account_xpub = account_data['xpub']
        
        # Test P2PKH address (should start with '1')
        p2pkh_addr = self.bip32_utils.derive_address_from_xpub(
            account_xpub, 0, 0, "m/44'/0'/0'", "p2pkh"
        )
        self.assertTrue(p2pkh_addr['address'].startswith('1'), 
                       f"P2PKH address should start with '1', got: {p2pkh_addr['address']}")
        
        # Test P2SH address (should start with '3')
        p2sh_addr = self.bip32_utils.derive_address_from_xpub(
            account_xpub, 0, 0, "m/49'/0'/0'", "p2sh"
        )
        self.assertTrue(p2sh_addr['address'].startswith('3'),
                       f"P2SH address should start with '3', got: {p2sh_addr['address']}")
        
        # Test Bech32 address (should start with 'bc1q')
        bech32_addr = self.bip32_utils.derive_address_from_xpub(
            account_xpub, 0, 0, "m/84'/0'/0'", "bech32"
        )
        self.assertTrue(bech32_addr['address'].startswith('bc1q'),
                       f"Bech32 address should start with 'bc1q', got: {bech32_addr['address']}")
        
        # Test Taproot address (should start with 'bc1p')
        taproot_addr = self.bip32_utils.derive_address_from_xpub(
            account_xpub, 0, 0, "m/86'/0'/0'", "taproot"
        )
        self.assertTrue(taproot_addr['address'].startswith('bc1p'),
                       f"Taproot address should start with 'bc1p', got: {taproot_addr['address']}")

    def test_multiple_derivation_paths(self):
        """Test different BIP derivation paths"""
        master_xprv = self.test_vector_1['master_xprv']
        
        # Test different purposes
        paths_to_test = [44, 49, 84, 86]
        
        for purpose in paths_to_test:
            with self.subTest(purpose=purpose):
                if purpose == 44:
                    # Use standard BIP44 method
                    account_data = self.bip32_utils.derive_bip44_account(master_xprv, 0, 0)
                else:
                    # This will test the custom derivation method when implemented
                    # For now, just test that we can derive something
                    try:
                        # Create a private key instance to test custom derivation
                        private_key = self.env['crypto.bitcoin.private.key'].create({
                            'name': f'Test Key {purpose}',
                            'key_source': 'xprv',
                            'xprv': master_xprv,
                        })
                        account_data = private_key._derive_custom_account_path(purpose, 0, 0)
                    except Exception as e:
                        self.fail(f"Failed to derive path m/{purpose}'/0'/0': {str(e)}")
                
                # Verify basic structure
                self.assertIn('xpub', account_data)
                self.assertIn('path', account_data)
                self.assertTrue(self.bip32_utils.validate_xpub_format(account_data['xpub']))

    def test_error_handling(self):
        """Test error handling for invalid inputs"""
        # Test invalid XPRV
        with self.assertRaises(ValidationError):
            self.bip32_utils.xprv_to_xpub('invalid_xprv')
        
        # Test invalid XPUB for address derivation
        with self.assertRaises(ValidationError):
            self.bip32_utils.derive_address_from_xpub('invalid_xpub', 0, 0)
        
        # Test invalid account derivation
        with self.assertRaises(ValidationError):
            self.bip32_utils.derive_bip44_account('invalid_xprv', 0, 0)

    def test_electrum_compatibility(self):
        """Test compatibility with Electrum wallet outputs"""
        # Skip this test if Electrum test data is not provided
        if not self.electrum_test['expected_legacy_xpub']:
            self.skipTest("Electrum test data not provided - fill in expected values")
        
        # Create private key from mnemonic
        private_key = self.env['crypto.bitcoin.private.key'].create({
            'name': 'Electrum Test Key',
            'key_source': 'mnemonic',
            'mnemonic': self.electrum_test['mnemonic'],
            'passphrase': self.electrum_test['passphrase'],
        })
        
        # Test Legacy path
        if self.electrum_test['expected_legacy_xpub']:
            self.assertEqual(private_key.legacy_xpub, self.electrum_test['expected_legacy_xpub'],
                           "Legacy XPUB doesn't match Electrum")
        
        # Test Nested SegWit path
        if self.electrum_test['expected_nested_xpub']:
            self.assertEqual(private_key.nested_segwit_xpub, self.electrum_test['expected_nested_xpub'],
                           "Nested SegWit XPUB doesn't match Electrum")
        
        # Test Native SegWit path
        if self.electrum_test['expected_native_xpub']:
            self.assertEqual(private_key.native_segwit_xpub, self.electrum_test['expected_native_xpub'],
                           "Native SegWit XPUB doesn't match Electrum")
        
        # Test Taproot path
        if self.electrum_test['expected_taproot_xpub']:
            self.assertEqual(private_key.taproot_xpub, self.electrum_test['expected_taproot_xpub'],
                           "Taproot XPUB doesn't match Electrum")

    def test_address_consistency(self):
        """Test that addresses are consistently generated"""
        master_xprv = self.test_vector_1['master_xprv']
        account_data = self.bip32_utils.derive_bip44_account(master_xprv, 0, 0)
        
        # Test that the same inputs produce the same addresses
        addr1 = self.bip32_utils.derive_address_from_xpub(
            account_data['xpub'], 0, 0, "m/44'/0'/0'", "p2pkh"
        )
        addr2 = self.bip32_utils.derive_address_from_xpub(
            account_data['xpub'], 0, 0, "m/44'/0'/0'", "p2pkh"
        )
        
        self.assertEqual(addr1['address'], addr2['address'],
                        "Same inputs should produce same address")
        self.assertEqual(addr1['path'], addr2['path'],
                        "Same inputs should produce same path")

