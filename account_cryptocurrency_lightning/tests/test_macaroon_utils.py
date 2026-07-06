# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import unittest
import base64
from unittest.mock import patch, MagicMock

from odoo.tests.common import TransactionCase
from ..models.macaroon_utils import MacaroonUtils, MacaroonValidationError


class TestMacaroonUtils(TransactionCase):
    """Test cases for MacaroonUtils class"""

    def setUp(self):
        super().setUp()
        # Sample valid LND macaroon (hex format) for testing
        self.valid_hex_macaroon = "0201036c6e6402ac01030a10dbaf04d38e9ba8ff52e93365b6d3ae381201301a0f0a07616464726573731204726561641a0c0a04696e666f1204726561641a100a08696e766f696365731204726561641a100a086d616361726f6f6e1204726561641a0f0a076d6573736167651204726561641a100a086f6666636861696e1204726561641a0f0a076f6e636861696e1204726561641a0d0a0570656572731204726561641a0e0a067369676e657212047265616400000620396b1846260476447cf1735d7bd51d741fdb9e78e1a17b72e38dac98792fa3f4"

        # Convert hex to base64 for testing base64 format
        self.valid_base64_macaroon = base64.b64encode(bytes.fromhex(self.valid_hex_macaroon)).decode('utf-8')

        # Invalid macaroons for testing error cases
        self.invalid_hex = "invalid_hex_string"
        self.invalid_base64 = "invalid_base64!@#$%"
        self.empty_macaroon = ""

    def test_validate_macaroon_valid_hex(self):
        """Test validation of valid hex-encoded macaroon"""
        try:
            MacaroonUtils.validate_macaroon(self.valid_hex_macaroon)
        except MacaroonValidationError:
            self.fail("validate_macaroon() raised MacaroonValidationError unexpectedly!")

    def test_validate_macaroon_valid_base64(self):
        """Test validation of valid base64-encoded macaroon"""
        try:
            MacaroonUtils.validate_macaroon(self.valid_base64_macaroon)
        except MacaroonValidationError:
            self.fail("validate_macaroon() raised MacaroonValidationError unexpectedly!")

    def test_validate_macaroon_empty(self):
        """Test validation fails for empty macaroon"""
        with self.assertRaises(MacaroonValidationError) as context:
            MacaroonUtils.validate_macaroon(self.empty_macaroon)
        self.assertIn("cannot be empty", str(context.exception))

    def test_validate_macaroon_invalid_format(self):
        """Test validation fails for invalid format"""
        with self.assertRaises(MacaroonValidationError):
            MacaroonUtils.validate_macaroon(self.invalid_hex)

    def test_parse_macaroon_valid_hex(self):
        """Test parsing of valid hex-encoded macaroon"""
        result = MacaroonUtils.parse_macaroon(self.valid_hex_macaroon)

        self.assertIsInstance(result, dict)
        self.assertIn('location', result)
        self.assertIn('identifier', result)
        self.assertIn('caveats', result)
        self.assertIn('caveat_count', result)
        self.assertIn('format', result)
        self.assertEqual(result['format'], 'hex')
        self.assertGreater(result['caveat_count'], 0)

    def test_parse_macaroon_valid_base64(self):
        """Test parsing of valid base64-encoded macaroon"""
        result = MacaroonUtils.parse_macaroon(self.valid_base64_macaroon)

        self.assertIsInstance(result, dict)
        self.assertEqual(result['format'], 'base64')
        self.assertGreater(result['caveat_count'], 0)

    def test_parse_macaroon_empty(self):
        """Test parsing returns empty dict for empty macaroon"""
        result = MacaroonUtils.parse_macaroon(self.empty_macaroon)
        self.assertEqual(result, {})

    def test_parse_macaroon_invalid(self):
        """Test parsing returns empty dict for invalid macaroon"""
        result = MacaroonUtils.parse_macaroon(self.invalid_hex)
        self.assertEqual(result, {})

    def test_get_macaroon_permissions(self):
        """Test extraction of permissions from macaroon"""
        permissions = MacaroonUtils.get_macaroon_permissions(self.valid_hex_macaroon)

        self.assertIsInstance(permissions, list)
        self.assertGreater(len(permissions), 0)

        # Check for expected LND permissions
        permission_text = ' '.join(permissions).lower()
        self.assertIn('read', permission_text)

    def test_format_macaroon_info_valid(self):
        """Test formatting of macaroon information"""
        info_text = MacaroonUtils.format_macaroon_info(self.valid_hex_macaroon)

        self.assertIsInstance(info_text, str)
        self.assertIn('Format: HEX', info_text)
        self.assertIn('Location:', info_text)
        self.assertIn('Identifier:', info_text)
        self.assertIn('Caveats', info_text)

    def test_format_macaroon_info_empty(self):
        """Test formatting returns appropriate message for empty macaroon"""
        info_text = MacaroonUtils.format_macaroon_info(self.empty_macaroon)
        self.assertEqual(info_text, "No macaroon available")

    def test_format_macaroon_info_invalid(self):
        """Test formatting returns appropriate message for invalid macaroon"""
        info_text = MacaroonUtils.format_macaroon_info(self.invalid_hex)
        self.assertEqual(info_text, "Unable to parse macaroon")

    def test_decode_macaroon_string_hex(self):
        """Test internal hex decoding method"""
        result = MacaroonUtils._decode_macaroon_string(self.valid_hex_macaroon)
        self.assertIsInstance(result, bytes)

    def test_decode_macaroon_string_base64(self):
        """Test internal base64 decoding method"""
        result = MacaroonUtils._decode_macaroon_string(self.valid_base64_macaroon)
        self.assertIsInstance(result, bytes)

    def test_decode_macaroon_string_with_format_hex(self):
        """Test internal decoding with format detection for hex"""
        result, format_type = MacaroonUtils._decode_macaroon_string_with_format(self.valid_hex_macaroon)
        self.assertIsInstance(result, bytes)
        self.assertEqual(format_type, 'hex')

    def test_decode_macaroon_string_with_format_base64(self):
        """Test internal decoding with format detection for base64"""
        result, format_type = MacaroonUtils._decode_macaroon_string_with_format(self.valid_base64_macaroon)
        self.assertIsInstance(result, bytes)
        self.assertEqual(format_type, 'base64')

    def test_safe_decode_bytes_utf8(self):
        """Test safe bytes decoding for UTF-8 text"""
        test_bytes = b"hello world"
        result = MacaroonUtils._safe_decode_bytes(test_bytes)
        self.assertEqual(result, "hello world")

    def test_safe_decode_bytes_binary(self):
        """Test safe bytes decoding for binary data"""
        test_bytes = b"\x00\x01\x02\xff"
        result = MacaroonUtils._safe_decode_bytes(test_bytes)
        self.assertEqual(result, "000102ff")

    def test_safe_decode_bytes_none(self):
        """Test safe bytes decoding for None input"""
        result = MacaroonUtils._safe_decode_bytes(None)
        self.assertEqual(result, "")

    @patch('odoo.addons.account_cryptocurrency_lightning.models.macaroon_utils.pymacaroons')
    def test_validate_macaroon_pymacaroons_exception(self, mock_pymacaroons):
        """Test handling of pymacaroons exceptions"""
        mock_pymacaroons.Macaroon.deserialize.side_effect = Exception("Parsing failed")

        with self.assertRaises(MacaroonValidationError) as context:
            MacaroonUtils.validate_macaroon("valid_looking_hex")

        self.assertIn("Macaroon validation failed", str(context.exception))

    def test_edge_case_very_short_string(self):
        """Test edge case with very short string"""
        with self.assertRaises(MacaroonValidationError):
            MacaroonUtils.validate_macaroon("ab")

    def test_edge_case_whitespace_string(self):
        """Test edge case with whitespace-only string"""
        with self.assertRaises(MacaroonValidationError):
            MacaroonUtils.validate_macaroon("   ")