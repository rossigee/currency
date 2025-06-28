# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import base64
import binascii
from typing import Dict, List, Optional


class MacaroonValidationError(Exception):
    """Exception raised when macaroon validation fails"""
    pass


class MacaroonUtils:
    """
    Utility class for macaroon parsing, validation and information extraction.
    This class provides clean separation of macaroon logic for better testing.
    """

    @staticmethod
    def validate_macaroon(macaroon_str: str) -> None:
        """
        Validate macaroon format and structure.

        Args:
            macaroon_str: The macaroon string (hex or base64 encoded)

        Raises:
            MacaroonValidationError: If macaroon is invalid
        """
        if not macaroon_str:
            raise MacaroonValidationError("Macaroon cannot be empty")

        try:
            macaroon_bytes = MacaroonUtils._decode_macaroon_string(macaroon_str)

            # Basic structural validation for macaroons
            # Macaroons start with version (0x02 for v2) and are at least 32 bytes
            if len(macaroon_bytes) < 32:
                raise MacaroonValidationError("Macaroon too short")

            if macaroon_bytes[0] != 0x02:
                raise MacaroonValidationError("Invalid macaroon version")

            # Basic macaroon structure validation
            # Just check we can parse basic structure
            try:
                MacaroonUtils._manual_parse_macaroon(macaroon_bytes)
            except Exception as e:
                raise MacaroonValidationError(f"Macaroon structure validation failed: {str(e)}")

        except (ValueError, TypeError, binascii.Error):
            raise MacaroonValidationError("Invalid macaroon format")
        except MacaroonValidationError:
            raise  # Re-raise our custom errors
        except Exception as e:
            raise MacaroonValidationError(f"Macaroon validation failed: {str(e)}")

    @staticmethod
    def parse_macaroon(macaroon_str: str) -> Dict:
        """
        Parse macaroon and extract detailed information.

        Args:
            macaroon_str: The macaroon string (hex or base64 encoded)

        Returns:
            Dictionary containing macaroon information:
            {
                'location': str,
                'identifier': str,
                'caveats': List[str],
                'caveat_count': int,
                'format': str  # 'hex' or 'base64'
            }
        """
        if not macaroon_str:
            return {}

        try:
            macaroon_bytes, format_type = MacaroonUtils._decode_macaroon_string_with_format(macaroon_str)

            # Basic validation
            if len(macaroon_bytes) < 32 or macaroon_bytes[0] != 0x02:
                return {}

            # Use manual parsing for all macaroons
            parsed_info = MacaroonUtils._manual_parse_macaroon(macaroon_bytes)
            parsed_info['format'] = format_type
            return parsed_info
        except Exception:
            return {}

    @staticmethod
    def get_macaroon_permissions(macaroon_str: str) -> List[str]:
        """
        Extract permissions/capabilities from macaroon caveats.

        Args:
            macaroon_str: The macaroon string (hex or base64 encoded)

        Returns:
            List of permission strings found in caveats
        """
        info = MacaroonUtils.parse_macaroon(macaroon_str)
        permissions = []

        for caveat in info.get('caveats', []):
            # Skip binary caveats
            if caveat.startswith('Binary caveat:'):
                continue

            # Extract common permission patterns
            if 'read' in caveat.lower():
                permissions.append(f"Read: {caveat}")
            elif 'write' in caveat.lower():
                permissions.append(f"Write: {caveat}")
            elif 'admin' in caveat.lower():
                permissions.append(f"Admin: {caveat}")
            else:
                permissions.append(caveat)

        return permissions

    @staticmethod
    def format_macaroon_info(macaroon_str: str) -> str:
        """
        Format macaroon information for display.

        Args:
            macaroon_str: The macaroon string (hex or base64 encoded)

        Returns:
            Formatted string with macaroon details
        """
        if not macaroon_str:
            return "No macaroon available"

        info = MacaroonUtils.parse_macaroon(macaroon_str)
        if not info:
            return "Unable to parse macaroon"

        info_text = f"Format: {info.get('format', 'unknown').upper()}\n"
        info_text += f"Location: {info.get('location') or 'N/A'}\n"
        info_text += f"Identifier: {info.get('identifier') or 'N/A'}\n"
        info_text += f"Caveats ({info.get('caveat_count', 0)}):\n"

        for caveat in info.get('caveats', []):
            info_text += f"  • {caveat}\n"

        return info_text

    @staticmethod
    def _decode_macaroon_string(macaroon_str: str) -> bytes:
        """
        Decode macaroon string trying hex first, then base64.

        Args:
            macaroon_str: The macaroon string to decode

        Returns:
            Decoded bytes

        Raises:
            ValueError: If neither hex nor base64 decoding works
        """
        try:
            return bytes.fromhex(macaroon_str)
        except ValueError:
            return base64.b64decode(macaroon_str)

    @staticmethod
    def _decode_macaroon_string_with_format(macaroon_str: str):
        """
        Decode macaroon string and return format type.

        Args:
            macaroon_str: The macaroon string to decode

        Returns:
            Tuple of (decoded_bytes, format_type)
        """
        try:
            return bytes.fromhex(macaroon_str), 'hex'
        except ValueError:
            return base64.b64decode(macaroon_str), 'base64'

    @staticmethod
    def _safe_decode_bytes(data: Optional[bytes]) -> str:
        """
        Safely decode bytes to string, falling back to hex if UTF-8 fails.

        Args:
            data: Bytes to decode, can be None

        Returns:
            Decoded string or hex representation
        """
        if not data:
            return ''

        try:
            return data.decode('utf-8')
        except UnicodeDecodeError:
            return data.hex()

    @staticmethod
    def _manual_parse_macaroon(macaroon_bytes: bytes) -> Dict:
        """
        Manual parser for macaroon binary format.

        This is a simplified parser that extracts basic information
        and looks for readable permission strings in the binary data.
        """
        if len(macaroon_bytes) < 34:
            raise ValueError("Macaroon too short for manual parsing")

        if macaroon_bytes[0] != 0x02:
            raise ValueError("Invalid macaroon version")

        # For LND macaroons, we'll scan for common permission strings
        # rather than trying to parse the complex binary format perfectly

        try:
            # Convert to string for searching, ignoring decode errors
            text_content = macaroon_bytes.decode('utf-8', errors='ignore')

            # Look for LND services and permissions
            permissions = []
            services = ['address', 'info', 'invoices', 'macaroon', 'message', 'offchain', 'onchain', 'peers', 'signer']
            perms = ['read', 'write', 'generate', 'admin']

            for service in services:
                if service in text_content:
                    # Find permissions for this service
                    service_perms = []
                    for perm in perms:
                        if perm in text_content[text_content.find(service):text_content.find(service)+50]:
                            service_perms.append(perm)

                    if service_perms:
                        permissions.append(f"{service}: {', '.join(service_perms)}")
                    else:
                        permissions.append(f"{service}: access")

            # Look for location (typically "lnd" for LND)
            location = "lnd"
            if "lnd" in text_content:
                location = "lnd"

            # Create a simple identifier
            identifier = f"LND Macaroon ({len(macaroon_bytes)} bytes)"

            return {
                'location': location,
                'identifier': identifier,
                'caveats': permissions if permissions else ['LND permissions detected'],
                'caveat_count': len(permissions) if permissions else 1
            }

        except Exception:
            # Return minimal info if scanning fails
            return {
                'location': 'lnd',
                'identifier': f'Binary macaroon ({len(macaroon_bytes)} bytes)',
                'caveats': ['Valid LND macaroon detected'],
                'caveat_count': 1
            }

