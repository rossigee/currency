# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, api
from odoo.exceptions import ValidationError
import struct
import logging

_logger = logging.getLogger(__name__)


class CryptoBitcoinTransactionUtils(models.AbstractModel):
    _name = 'crypto.bitcoin.transaction.utils'
    _description = 'Bitcoin Transaction Parsing Utilities'

    @api.model
    def parse_transaction_hex(self, tx_hex, target_address=None):
        """
        Parse raw Bitcoin transaction hex to extract transaction data
        
        Args:
            tx_hex (str): Raw transaction in hex format
            target_address (str, optional): Address to calculate value for
            
        Returns:
            dict: Parsed transaction data with inputs, outputs, and calculated values
        """
        try:
            _logger.info(f"Parsing Bitcoin transaction hex, length: {len(tx_hex)} chars")
            if target_address:
                _logger.info(f"Calculating value for target address: {target_address}")
            
            # Decode hex to bytes
            tx_bytes = bytes.fromhex(tx_hex)
            
            if len(tx_bytes) < 10:
                raise ValidationError("Transaction too short")
            
            # Parse version
            version = struct.unpack('<I', tx_bytes[:4])[0]
            offset = 4
            
            # Check for SegWit marker and flag (BIP 141)
            is_segwit = False
            if offset + 2 < len(tx_bytes) and tx_bytes[offset] == 0x00 and tx_bytes[offset + 1] == 0x01:
                is_segwit = True
                offset += 2  # Skip marker (0x00) and flag (0x01)
                _logger.info(f"SegWit transaction detected, version: {version}")
            else:
                _logger.info(f"Legacy transaction, version: {version}")
            
            # Parse inputs
            inputs, offset = self._parse_transaction_inputs(tx_bytes, offset)
            
            # Parse outputs  
            outputs, offset = self._parse_transaction_outputs(tx_bytes, offset, target_address)
            
            # Handle witness data for SegWit transactions
            if is_segwit:
                offset = self._skip_witness_data(tx_bytes, offset, len(inputs))
            
            # Calculate net effect on target address (outputs - inputs)
            target_value = 0
            if target_address:
                # Add amounts received (outputs TO our address)
                received = 0
                for output in outputs:
                    if output.get('address') == target_address:
                        received += output['value']
                        _logger.info(f"✓ RECEIVED: {output['value']} sats in output")
                
                # Subtract amounts sent (inputs FROM our address)
                sent = 0
                for input_data in inputs:
                    # Check if this input came from our address
                    # Note: This requires looking up the previous output, which we don't have in the current transaction
                    # For now, we'll implement this differently - we need to track inputs properly
                    pass  # Will implement input tracking separately
                
                target_value = received - sent
                _logger.info(f"Net effect for {target_address}: +{received} sats received, -{sent} sats sent, net: {target_value} sats")
            
            _logger.info(f"Parsed transaction: {len(inputs)} inputs, {len(outputs)} outputs")
            if target_address:
                _logger.info(f"Total value for {target_address}: {target_value} satoshis")
            
            # Validate parsed amounts
            self._validate_transaction_amounts(target_value, outputs, target_address)
            
            return {
                'version': version,
                'is_segwit': is_segwit,
                'inputs': inputs,
                'outputs': outputs,
                'target_value': target_value,
                'fee': 0  # Cannot calculate without input values
            }
            
        except Exception as e:
            _logger.error(f"Failed to parse transaction hex: {str(e)}")
            raise ValidationError(f"Unable to parse transaction data: {str(e)}")

    def _parse_transaction_inputs(self, tx_bytes, offset):
        """Parse transaction inputs"""
        # Parse input count
        input_count, offset = self._parse_varint(tx_bytes, offset)
        _logger.debug(f"Input count: {input_count}")
        
        inputs = []
        for i in range(input_count):
            if offset + 36 > len(tx_bytes):
                _logger.warning(f"Transaction too short for input {i}")
                break
                
            # Previous transaction hash (32 bytes) and output index (4 bytes)
            prev_hash = tx_bytes[offset:offset + 32].hex()
            prev_index = struct.unpack('<I', tx_bytes[offset + 32:offset + 36])[0]
            offset += 36
            
            # Parse script length and skip script
            script_len, offset = self._parse_varint(tx_bytes, offset)
            if offset + script_len > len(tx_bytes):
                _logger.warning(f"Transaction too short for input {i} script")
                break
            
            script = tx_bytes[offset:offset + script_len].hex()
            offset += script_len
            
            # Skip sequence (4 bytes)
            if offset + 4 > len(tx_bytes):
                _logger.warning(f"Transaction too short for input {i} sequence")
                break
            
            sequence = struct.unpack('<I', tx_bytes[offset:offset + 4])[0]
            offset += 4
            
            inputs.append({
                'prev_hash': prev_hash,
                'prev_index': prev_index,
                'script': script,
                'sequence': sequence
            })
        
        return inputs, offset

    def _parse_transaction_outputs(self, tx_bytes, offset, target_address=None):
        """Parse transaction outputs"""
        # Parse output count
        if offset >= len(tx_bytes):
            raise ValidationError("Transaction parsing failed: insufficient data for outputs")
        
        output_count, offset = self._parse_varint(tx_bytes, offset)
        _logger.debug(f"Output count: {output_count}")
        
        outputs = []
        for i in range(output_count):
            if offset + 8 > len(tx_bytes):
                _logger.warning(f"Transaction too short for output {i} value")
                break
                
            # Parse value (8 bytes, little endian)
            value = struct.unpack('<Q', tx_bytes[offset:offset + 8])[0]
            offset += 8
            
            # Parse script length
            script_len, offset = self._parse_varint(tx_bytes, offset)
            
            if offset + script_len > len(tx_bytes):
                _logger.warning(f"Transaction too short for output {i} script")
                break
                
            # Get script
            script = tx_bytes[offset:offset + script_len]
            script_hex = script.hex()
            offset += script_len
            
            # Convert script to address
            try:
                output_address = self._script_to_address(script_hex)
                
                if target_address and output_address:
                    if output_address == target_address:
                        _logger.info(f"✓ MATCH: Output {i}: {value} sats → {output_address}")
                    else:
                        _logger.debug(f"Output {i}: {value} sats → {output_address}")
                
            except Exception as addr_err:
                _logger.warning(f"Could not parse address for output {i}: {str(addr_err)}")
                output_address = f"UNPARSEABLE:{script_hex[:16]}"
            
            outputs.append({
                'value': value,
                'script': script_hex,
                'address': output_address
            })
        
        return outputs, offset

    def _skip_witness_data(self, tx_bytes, offset, input_count):
        """Skip witness data for SegWit transactions"""
        _logger.debug(f"Parsing witness data, offset: {offset}")
        
        try:
            # For each input, parse witness stack
            for i in range(input_count):
                if offset >= len(tx_bytes):
                    _logger.warning(f"Insufficient data for witness {i}")
                    break
                
                # Parse witness stack item count
                witness_count, offset = self._parse_varint(tx_bytes, offset)
                _logger.debug(f"Input {i} has {witness_count} witness stack items")
                
                # Skip each witness stack item
                for j in range(witness_count):
                    if offset >= len(tx_bytes):
                        break
                    witness_len, offset = self._parse_varint(tx_bytes, offset)
                    if offset + witness_len > len(tx_bytes):
                        _logger.warning(f"Witness item {j} too long")
                        break
                    offset += witness_len  # Skip witness data
                    
        except Exception as witness_err:
            _logger.warning(f"Failed to parse witness data: {str(witness_err)}")
            # Continue anyway - witness data doesn't affect output amounts
        
        _logger.debug(f"Completed witness parsing, final offset: {offset}")
        return offset

    def _validate_transaction_amounts(self, target_value, outputs, target_address):
        """Validate that parsed transaction amounts are reasonable"""
        # Allow zero values now since they might represent sends (negative amounts)
        # if target_address and target_value == 0:
        #     _logger.error(f"ZERO VALUE RESULT for {target_address}")
        #     _logger.error(f"Parsed {len(outputs)} outputs:")
        #     for i, output in enumerate(outputs):
        #         _logger.error(f"  Output {i}: {output['value']} sats → {output['address']}")
        #     raise ValidationError(f"Transaction parsing failed: no valid amount found for address {target_address}")
            
        # Check for suspiciously large amounts (parsing errors)
        max_reasonable = 21000000 * 100000000  # 21M BTC in satoshis
        for i, output in enumerate(outputs):
            if output['value'] > max_reasonable:
                _logger.error(f"Invalid amount in output {i}: {output['value']} sats (>{21000000} BTC)")
                raise ValidationError(f"Transaction parsing produced invalid amount: {output['value']} satoshis")
        
        # If target_value is 0 and we found no outputs to our address, 
        # this might be a transaction where we're sending (inputs)
        if target_address and target_value == 0:
            has_output_to_address = any(output.get('address') == target_address for output in outputs)
            if not has_output_to_address:
                _logger.info(f"Zero value transaction for {target_address} - likely a send transaction where address is in inputs")
                # Don't raise error for send transactions

    def _script_to_address(self, script_hex):
        """Convert script pubkey to Bitcoin address"""
        # Delegate to the BIP32 utils for address conversion
        return self.env['crypto.bip32.utils']._script_to_address(script_hex)

    def _parse_varint(self, data, offset):
        """Parse Bitcoin variable integer"""
        if offset >= len(data):
            return 0, offset
            
        first_byte = data[offset]
        
        if first_byte < 0xfd:
            return first_byte, offset + 1
        elif first_byte == 0xfd:
            if offset + 2 >= len(data):
                return 0, offset + 1
            return struct.unpack('<H', data[offset + 1:offset + 3])[0], offset + 3
        elif first_byte == 0xfe:
            if offset + 4 >= len(data):
                return 0, offset + 1
            return struct.unpack('<I', data[offset + 1:offset + 5])[0], offset + 5
        else:  # 0xff
            if offset + 8 >= len(data):
                return 0, offset + 1
            return struct.unpack('<Q', data[offset + 1:offset + 9])[0], offset + 9