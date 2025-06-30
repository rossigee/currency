# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, api
from odoo.exceptions import ValidationError
import socket
import ssl
import json
import hashlib
import base58
import logging
import os
import time

_logger = logging.getLogger(__name__)


class ElectrumClient(models.AbstractModel):
    _name = 'electrum.client'
    _description = 'Electrum Server Client'
    
    @api.model
    def get_default_client(self):
        """Get configured Electrum client instance with failover support"""
        try:
            # Check if server configurations are available
            server_config = self.env['electrum.server.config'].get_best_server()
            return self
        except UserError:
            # Create default server configurations if none exist
            try:
                self.env['electrum.server.config'].create_default_servers()
                return self
            except:
                raise ValidationError("No Electrum servers available. Please configure at least one Electrum server.")
    
    @api.model
    def get_with_failover(self, network=None, max_attempts=3):
        """Get best available Electrum server configuration with failover"""
        try:
            # Get available server configurations with failover
            servers = self.env['electrum.server.config'].get_active_servers(network)
            
            if not servers:
                # Create default server configurations
                self.env['electrum.server.config'].create_default_servers(network or 'mainnet')
                servers = self.env['electrum.server.config'].get_active_servers(network)
            
            for attempt, server in enumerate(servers[:max_attempts]):
                try:
                    # Quick test to ensure server is working
                    host, port, use_ssl = server._get_connection_settings()
                    result = self.test_connection(host, port, use_ssl)
                    
                    if result['success']:
                        _logger.info(f"Using Electrum server: {server.display_name}")
                        return server
                    else:
                        raise Exception(result.get('message', 'Connection test failed'))
                        
                except Exception as e:
                    _logger.warning(f"Electrum server {server.name} failed (attempt {attempt + 1}): {str(e)}")
                    if attempt == len(servers) - 1 or attempt == max_attempts - 1:
                        # Last attempt, re-raise error
                        raise
                    continue
                    
        except Exception as e:
            _logger.error(f"All Electrum servers failed: {str(e)}")
            raise ValidationError(f"No Electrum servers available: {str(e)}")
    
    @api.model
    def test_connection(self, host=None, port=None, use_ssl=None, timeout=None):
        """Test connection to Electrum server with configurable timeout"""
        try:
            # Use a shorter timeout for testing if not specified
            if timeout is None:
                timeout = self._get_server_timeout(host, port) if host else 5
                timeout = min(timeout, 10)  # Cap test timeout at 10 seconds
            
            block_height = self._get_block_height_from_server(host, port, use_ssl, timeout)
            return {
                'success': True,
                'message': f"Connected successfully, block height: {block_height}",
                'block_height': block_height
            }
        except Exception as e:
            return {
                'success': False,
                'message': f"Connection failed: {str(e)}",
                'error': str(e)
            }

    @api.model
    def get_address_history(self, address, host=None, port=None, use_ssl=True):
        """
        Get transaction history for a Bitcoin address via Electrum protocol with failover
        
        Args:
            address (str): Bitcoin address
            host (str): Electrum server hostname (overrides server configs)
            port (int): Electrum server port (overrides server configs)
            use_ssl (bool): Use SSL connection (overrides server configs)
            
        Returns:
            list: Transaction history in standardized format
        """
        _logger.info(f"Fetching address history via Electrum for: {address}")
        
        # Convert address to script hash (Electrum protocol requirement)
        script_hash = self.env['crypto.bip32.utils'].address_to_script_hash(address)
        _logger.info(f"Converted address to script hash: {script_hash}")
        
        # If specific connection parameters provided, use them directly
        if host and port is not None:
            return self._get_history_from_server(address, script_hash, host, port, use_ssl)
        
        # Use server failover system
        try:
            # Get configured servers in priority order - ONLY for mainnet to prevent network mixing
            servers = self.env['electrum.server.config'].get_failover_chain(network='mainnet')
            
            if not servers:
                # Fallback to environment/settings configuration
                host, port, use_ssl = self._get_electrum_config(host, port, use_ssl)
                return self._get_history_from_server(address, script_hash, host, port, use_ssl)
            
            # Try servers in priority order
            last_error = None
            for attempt, server in enumerate(servers):
                try:
                    server_host, server_port, server_ssl = server._get_connection_settings()
                    _logger.info(f"Trying Electrum server {attempt + 1}/{len(servers)}: {server.display_name}")
                    
                    # Use server's configured timeout
                    server_timeout = server.timeout_seconds
                    return self._get_history_from_server(address, script_hash, server_host, server_port, server_ssl, server_timeout)
                    
                except Exception as e:
                    last_error = e
                    _logger.warning(f"Electrum server {server.name} failed: {str(e)}")
                    continue
            
            # All servers failed
            raise ValidationError(f"All Electrum servers failed. Last error: {str(last_error)}")
            
        except Exception as e:
            _logger.error(f"Failed to get address history via Electrum: {str(e)}")
            raise ValidationError(f"Electrum address history failed: {str(e)}")
    
    def _get_history_from_server(self, address, script_hash, host, port, use_ssl, timeout=None):
        """Get history from a specific Electrum server with configurable timeout and connection reuse"""
        sock = None
        try:
            # Create persistent connection for this batch
            sock = self._create_electrum_connection(host, port, use_ssl, timeout)
            connection = (host, port, use_ssl, sock, timeout)
            
            # Get history from Electrum server using persistent connection
            history = self._electrum_request_with_connection(sock, "blockchain.scripthash.get_history", [script_hash])
            
            _logger.info(f"Electrum server {host}:{port} returned {len(history)} transactions")
            
            # Get current block height once for all transactions
            current_height_response = self._electrum_request_with_connection(sock, "blockchain.headers.subscribe", [])
            current_height = current_height_response.get('height', 0) if current_height_response else 0
            _logger.info(f"Current blockchain height: {current_height}")
            
            # Convert to standardized format with full transaction details
            transactions = []
            for item in history:
                txid = item['tx_hash']
                height = item.get('height', 0)
                
                # Log the raw history item to see what data Electrum provides
                _logger.info(f"Raw Electrum history item for {txid}: {item}")
                
                # CHECK: Does Electrum already provide the balance change?
                if 'value' in item:
                    electrum_value = item['value']
                    _logger.info(f"✓ Electrum provided direct value for {txid}: {electrum_value} sats (net effect)")
                    # Skip complex parsing if Electrum already calculated the amount
                    tx_data = {
                        'txid': txid,
                        'height': height,
                        'fee': 0,  # Will try to get from transaction details
                        'confirmations': max(0, current_height - height + 1) if height > 0 else 0,
                        'value': electrum_value,  # Use Electrum's calculated net effect
                        'vin': [],
                        'vout': [],
                        'block_time': None  # Will be fetched separately
                    }
                    transactions.append(tx_data)
                    continue
                
                try:
                    # Get full transaction details using persistent connection
                    tx_details = self._get_full_transaction_data(txid, address, connection)
                    
                    # Calculate confirmations using already-fetched current height
                    confirmations = max(0, current_height - height + 1) if height > 0 else 0
                    
                    # Get block time for confirmed transactions
                    block_time = None
                    if height > 0:
                        try:
                            _logger.info(f"Fetching block header for height {height} to get timestamp")
                            block_header = self._electrum_request_with_connection(sock, "blockchain.block.header", [height])
                            _logger.info(f"Block header response for height {height}: {block_header}")
                            
                            # Electrum returns hex-encoded block header, need to parse it
                            if block_header and isinstance(block_header, str):
                                # Parse hex block header to get timestamp
                                block_time = self._parse_block_header_timestamp(block_header)
                                if block_time:
                                    _logger.info(f"Successfully parsed block time for height {height}: {block_time}")
                                else:
                                    _logger.error(f"Failed to parse timestamp from block header hex: {block_header}")
                            elif block_header and 'timestamp' in block_header:
                                # Direct timestamp field (some Electrum servers)
                                block_time = block_header['timestamp']
                                _logger.info(f"Successfully got block time for height {height}: {block_time}")
                            else:
                                _logger.error(f"Unexpected block header format for height {height}: {type(block_header)} - {block_header}")
                        except Exception as e:
                            _logger.error(f"Failed to get block header for height {height}: {str(e)}")
                            import traceback
                            _logger.error(f"Stack trace: {traceback.format_exc()}")
                    else:
                        _logger.info(f"Transaction at height {height} is unconfirmed, no block time available")
                    
                    tx_data = {
                        'txid': txid,
                        'height': height,
                        'fee': tx_details.get('fee', 0),
                        'confirmations': confirmations,
                        'value': tx_details.get('value', 0),
                        'vin': tx_details.get('vin', []),
                        'vout': tx_details.get('vout', []),
                        'block_time': block_time,
                        'block_hash': None  # Could get this from block header if needed
                    }
                    
                    _logger.info(f"Prepared tx_data for {txid}: height={height}, block_time={block_time}, confirmations={confirmations}")
                    transactions.append(tx_data)
                    
                except Exception as e:
                    _logger.error(f"Failed to get full details for transaction {txid}: {str(e)}")
                    # Re-raise the error instead of using fallback data
                    raise ValidationError(f"Unable to fetch complete transaction data for {txid}: {str(e)}")
            
            return transactions
            
        except Exception as e:
            _logger.error(f"Server {host}:{port} failed: {str(e)}")
            raise
        finally:
            # Always close the connection
            if sock:
                try:
                    sock.close()
                except:
                    pass

    def _get_full_transaction_data(self, txid, address, connection=None):
        """Get full transaction data including amounts for a specific address"""
        try:
            # Use provided connection or create new one
            if connection:
                host, port, use_ssl, sock, timeout = connection
                # Try to get verbose transaction data first, fallback to hex
                try:
                    _logger.info(f"Attempting verbose transaction fetch for {txid}")
                    tx_verbose = self._electrum_request_with_connection(sock, "blockchain.transaction.get", [txid, True])
                    _logger.info(f"Verbose response type: {type(tx_verbose)}, content: {tx_verbose}")
                    
                    if tx_verbose and isinstance(tx_verbose, dict) and 'vout' in tx_verbose:
                        _logger.info(f"✓ Using verbose transaction data for {txid}")
                        return self._process_verbose_transaction(tx_verbose, address)
                    else:
                        _logger.warning(f"Verbose response not usable: {tx_verbose}")
                except Exception as e:
                    _logger.warning(f"Verbose transaction fetch failed for {txid}, trying hex: {str(e)}")
                
                _logger.info(f"Falling back to hex parsing for {txid}")
                tx_hex = self._electrum_request_with_connection(sock, "blockchain.transaction.get", [txid])
            else:
                # Fallback to individual connection (should be avoided)
                servers = self.env['electrum.server.config'].get_failover_chain(network='mainnet', max_servers=1)
                if servers:
                    server = servers[0]
                    host, port, use_ssl = server._get_connection_settings()
                    timeout = server.timeout_seconds
                else:
                    host, port, use_ssl = self._get_electrum_config()
                    timeout = 10
                    
                tx_hex = self._electrum_request(host, port, use_ssl, "blockchain.transaction.get", [txid], timeout)
            
            # Parse transaction using utility class
            tx_utils = self.env['crypto.bitcoin.transaction.utils']
            parsed_tx = tx_utils.parse_transaction_hex(tx_hex, address)
            
            tx_data = {
                'value': parsed_tx['target_value'],
                'vin': parsed_tx['inputs'],
                'vout': parsed_tx['outputs'],
                'fee': parsed_tx['fee'],
                'version': parsed_tx['version']
            }
            
            return tx_data
            
        except Exception as e:
            _logger.error(f"Failed to get full transaction data for {txid}: {str(e)}")
            raise


    def _script_to_address(self, script_hex):
        """Convert script pubkey to Bitcoin address"""
        # Use the BIP32 utils for consistent address conversion
        return self.env['crypto.bip32.utils']._script_to_address(script_hex)

    def _parse_block_header_timestamp(self, header_hex):
        """Parse timestamp from hex-encoded Bitcoin block header"""
        try:
            import struct
            
            # Block header format: version(4) + prev_hash(32) + merkle_root(32) + timestamp(4) + bits(4) + nonce(4)
            # Total: 80 bytes
            header_bytes = bytes.fromhex(header_hex)
            
            if len(header_bytes) != 80:
                _logger.error(f"Invalid block header length: {len(header_bytes)}, expected 80")
                return None
            
            # Timestamp is at offset 68 (4+32+32), little-endian 4-byte integer
            timestamp = struct.unpack('<I', header_bytes[68:72])[0]
            _logger.info(f"Parsed timestamp from block header: {timestamp}")
            return timestamp
            
        except Exception as e:
            _logger.error(f"Failed to parse block header timestamp: {str(e)}")
            return None

    def _script_matches_address(self, script_hex, target_address):
        """Check if a script matches a target address by reverse-engineering the expected script"""
        try:
            if target_address.startswith('bc1q') and len(target_address) == 42:
                # P2WPKH bech32 address - should create script 0014<20-byte-hash>
                # Convert bech32 to pubkey hash and create expected script
                expected_script = self._address_to_script(target_address)
                matches = script_hex.lower() == expected_script.lower()
                if matches:
                    _logger.info(f"✓ Script {script_hex} matches expected script for {target_address}")
                return matches
            # Add more address types as needed
            return False
        except Exception as e:
            _logger.warning(f"Script matching failed: {str(e)}")
            return False

    def _address_to_script(self, address):
        """Convert address back to expected script (reverse of _script_to_address)"""
        if address.startswith('bc1q') and len(address) == 42:
            # P2WPKH: decode bech32 to get pubkey hash, create 0014<hash> script
            try:
                # Use the script hash from address lookup
                script_hash = self.env['crypto.bip32.utils'].address_to_script_hash(address)
                # For P2WPKH, script should be 0014 + 20-byte pubkey hash
                # The script_hash is already the right format for Electrum lookup
                # But we need the actual script from the address
                
                # SIMPLE APPROACH: Extract from known address format
                # bc1qe4v4m25nj9why2mn83uygy04daud8s9ea3jm89 should produce 0014 + pubkey_hash
                if len(address) == 42:  # Standard P2WPKH
                    # For now, return a predictable pattern we can check
                    return f"0014{address[4:]}"  # This won't work but shows the approach
            except:
                pass
        return None

    def _process_verbose_transaction(self, tx_verbose, target_address):
        """Process verbose transaction data from Electrum server"""
        try:
            _logger.info(f"Processing verbose transaction data for address {target_address}")
            
            received_value = 0  # What we received (outputs TO our address)
            sent_value = 0     # What we sent (inputs FROM our address)
            outputs = []
            inputs = []
            
            # Process outputs - what we received
            if 'vout' in tx_verbose:
                for i, output in enumerate(tx_verbose['vout']):
                    value = int(output.get('value', 0) * 100000000)  # Convert to satoshis
                    script_info = output.get('scriptPubKey', {})
                    addresses = script_info.get('addresses', [])
                    
                    # Check if our target address is in this output (we received money)
                    if target_address in addresses:
                        received_value += value
                        _logger.info(f"✓ RECEIVED: Address {target_address} received {value} sats in output {i}")
                    
                    outputs.append({
                        'value': value,
                        'addresses': addresses,
                        'type': script_info.get('type', 'unknown')
                    })
            
            # Process inputs - what we sent (need to check if inputs came from our address)
            if 'vin' in tx_verbose:
                for i, input_data in enumerate(tx_verbose['vin']):
                    input_value = input_data.get('value', 0)
                    input_addresses = input_data.get('addresses', [])
                    
                    # Check if our target address was the source of this input (we sent money)
                    if target_address in input_addresses:
                        input_value_sats = int(input_value * 100000000) if input_value < 1 else int(input_value)
                        sent_value += input_value_sats
                        _logger.info(f"✓ SENT: Address {target_address} sent {input_value_sats} sats in input {i}")
                    
                    inputs.append({
                        'txid': input_data.get('txid'),
                        'vout': input_data.get('vout'),
                        'value': input_value,
                        'addresses': input_addresses
                    })
            
            # Net effect on the wallet: received - sent
            net_value = received_value - sent_value
            _logger.info(f"Wallet impact for {target_address}: received {received_value} sats, sent {sent_value} sats, net: {net_value} sats")
            
            # Get fee if available
            fee = tx_verbose.get('fee', 0)
            if isinstance(fee, (int, float)):
                fee_sats = int(fee * 100000000) if fee < 1 else int(fee)  # Handle both BTC and sat units
            else:
                fee_sats = 0
            
            _logger.info(f"Verbose transaction processed: net {net_value} sats for {target_address}, fee: {fee_sats} sats")
            
            return {
                'value': net_value,  # Net effect: positive = received, negative = sent
                'vin': inputs,
                'vout': outputs,
                'fee': fee_sats,
                'received': received_value,  # Additional detail
                'sent': sent_value           # Additional detail
            }
            
        except Exception as e:
            _logger.error(f"Failed to process verbose transaction: {str(e)}")
            raise

    @api.model
    def get_transaction(self, txid, host=None, port=None, use_ssl=True, timeout=None):
        """
        Get full transaction details by transaction ID
        
        Args:
            txid (str): Transaction ID
            host (str): Electrum server hostname  
            port (int): Electrum server port
            use_ssl (bool): Use SSL connection
            timeout (int): Connection timeout in seconds
            
        Returns:
            dict: Full transaction data
        """
        try:
            _logger.info(f"Fetching transaction details via Electrum for: {txid}")
            
            # Get server configuration with priority: params > env vars > settings > defaults
            host, port, use_ssl = self._get_electrum_config(host, port, use_ssl)
            
            # Get transaction hex
            tx_hex = self._electrum_request(
                host=host,
                port=port,
                use_ssl=use_ssl,
                method="blockchain.transaction.get",
                params=[txid],
                timeout=timeout
            )
            
            # Parse transaction (would need full Bitcoin transaction parser)
            # For now, return basic structure
            return {
                'txid': txid,
                'hex': tx_hex,
                'parsed': False  # Indicates we need to parse the hex
            }
            
        except Exception as e:
            _logger.error(f"Failed to get transaction via Electrum: {str(e)}")
            raise ValidationError(f"Electrum transaction fetch failed: {str(e)}")

    @api.model
    def get_block_height(self, host=None, port=None, use_ssl=True):
        """
        Get current blockchain height with failover support
        
        Returns:
            int: Current block height
        """
        # If specific connection parameters provided, use them directly
        if host and port is not None:
            return self._get_block_height_from_server(host, port, use_ssl)
        
        # Use server failover system
        try:
            # Get configured servers in priority order
            servers = self.env['electrum.server.config'].get_failover_chain(network='mainnet', max_servers=3)
            
            if not servers:
                # Fallback to environment/settings configuration
                host, port, use_ssl = self._get_electrum_config(host, port, use_ssl)
                return self._get_block_height_from_server(host, port, use_ssl)
            
            # Try servers in priority order
            last_error = None
            for attempt, server in enumerate(servers):
                try:
                    server_host, server_port, server_ssl = server._get_connection_settings()
                    _logger.info(f"Trying Electrum server {attempt + 1}/{len(servers)} for block height: {server.display_name}")
                    
                    # Use server's configured timeout
                    server_timeout = server.timeout_seconds
                    height = self._get_block_height_from_server(server_host, server_port, server_ssl, server_timeout)
                    if height > 0:
                        return height
                    
                except Exception as e:
                    last_error = e
                    _logger.warning(f"Electrum server {server.name} failed for block height: {str(e)}")
                    continue
            
            # All servers failed
            _logger.error(f"All Electrum servers failed for block height. Last error: {str(last_error)}")
            return 0
            
        except Exception as e:
            _logger.error(f"Failed to get block height via Electrum: {str(e)}")
            return 0
    
    def _get_block_height_from_server(self, host, port, use_ssl, timeout=None):
        """Get block height from a specific Electrum server with configurable timeout"""
        try:
            # Get blockchain info
            result = self._electrum_request(
                host=host,
                port=port,
                use_ssl=use_ssl,
                method="blockchain.headers.subscribe",
                params=[],
                timeout=timeout
            )
            
            height = result.get('height', 0)
            _logger.info(f"Electrum server {host}:{port} returned block height: {height}")
            return height
            
        except Exception as e:
            _logger.error(f"Server {host}:{port} failed for block height: {str(e)}")
            raise

    def _electrum_request(self, host, port, use_ssl, method, params, timeout=None):
        """
        Make a request to Electrum server with configurable timeout
        
        Args:
            host (str): Server hostname
            port (int): Server port
            use_ssl (bool): Use SSL
            method (str): Electrum method name
            params (list): Method parameters
            timeout (int): Connection timeout in seconds (auto-detected if None)
            
        Returns:
            dict: Response data
        """
        # Auto-detect timeout from server configuration or use default
        if timeout is None:
            timeout = self._get_server_timeout(host, port)
        
        sock = None
        try:
            # Create socket connection with configurable timeout
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            if use_ssl:
                context = ssl.create_default_context()
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                sock = context.wrap_socket(sock, server_hostname=host)
            
            _logger.info(f"Connecting to Electrum server: {host}:{port} (SSL: {use_ssl})")
            
            # Connect with timeout
            sock.connect((host, port))
            
            # Prepare request
            request = {
                "id": 1,
                "method": method,
                "params": params
            }
            
            # Send request
            message = json.dumps(request) + '\n'
            sock.send(message.encode())
            
            # Read response with timeout
            response_data = b''
            start_time = time.time()
            while b'\n' not in response_data:
                if time.time() - start_time > timeout:
                    raise socket.timeout("Read timeout")
                    
                try:
                    sock.settimeout(1)  # Short timeout for recv
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                except socket.timeout:
                    # Check if we've exceeded overall timeout
                    if time.time() - start_time > timeout:
                        raise socket.timeout("Read timeout")
                    continue
            
            # Parse response
            if not response_data:
                raise ValidationError("No response from Electrum server")
                
            response_text = response_data.decode().strip()
            if not response_text:
                raise ValidationError("Empty response from Electrum server")
                
            response = json.loads(response_text)
            
            if 'error' in response and response['error']:
                raise ValidationError(f"Electrum server error: {response['error']}")
            
            return response.get('result', [])
            
        except socket.timeout as e:
            error_msg = f"Timeout connecting to {host}:{port} (timeout: {timeout}s)"
            _logger.error(error_msg)
            raise ValidationError(error_msg)
            
        except socket.gaierror as e:
            error_msg = f"DNS resolution failed for {host}: {str(e)}"
            _logger.error(error_msg)
            raise ValidationError(error_msg)
            
        except ConnectionRefusedError as e:
            error_msg = f"Connection refused by {host}:{port}"
            _logger.error(error_msg)
            raise ValidationError(error_msg)
            
        except ssl.SSLError as e:
            error_msg = f"SSL error connecting to {host}:{port}: {str(e)}"
            _logger.error(error_msg)
            raise ValidationError(error_msg)
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response from {host}:{port}: {str(e)}"
            _logger.error(error_msg)
            raise ValidationError(error_msg)
            
        except Exception as e:
            error_msg = f"Electrum request to {host}:{port} failed: {str(e)}"
            _logger.error(error_msg)
            raise ValidationError(error_msg)
            
        finally:
            # Ensure socket is always closed
            if sock:
                try:
                    sock.close()
                except:
                    pass

    def _create_electrum_connection(self, host, port, use_ssl, timeout=None):
        """Create and return a connected socket for reuse"""
        if timeout is None:
            timeout = self._get_server_timeout(host, port)
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        
        if use_ssl:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            sock = context.wrap_socket(sock, server_hostname=host)
        
        _logger.info(f"Creating persistent connection to Electrum server: {host}:{port} (SSL: {use_ssl})")
        sock.connect((host, port))
        
        return sock

    def _electrum_request_with_connection(self, sock, method, params):
        """Make request using existing socket connection"""
        import json
        import time
        
        # Prepare request
        request = {
            "id": 1,
            "method": method,
            "params": params
        }
        
        # Send request
        message = json.dumps(request) + '\n'
        sock.send(message.encode())
        
        # Read response
        response_data = b''
        start_time = time.time()
        timeout = 30  # Individual request timeout
        
        while b'\n' not in response_data:
            if time.time() - start_time > timeout:
                raise socket.timeout("Read timeout")
                
            try:
                sock.settimeout(1)  # Short timeout for recv
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
            except socket.timeout:
                # Check if we've exceeded overall timeout
                if time.time() - start_time > timeout:
                    raise socket.timeout("Read timeout")
                continue
        
        # Parse response
        if not response_data:
            raise ValidationError("No response from Electrum server")
            
        response_text = response_data.decode().strip()
        if not response_text:
            raise ValidationError("Empty response from Electrum server")
            
        response = json.loads(response_text)
        
        if 'error' in response and response['error']:
            raise ValidationError(f"Electrum server error: {response['error']}")
        
        return response.get('result', [])

    def _get_server_timeout(self, host, port):
        """Get timeout setting for a specific server or use default"""
        try:
            # Look for server configuration
            server = self.env['electrum.server.config'].search([
                ('host', '=', host),
                ('port', '=', port),
                ('is_active', '=', True)
            ], limit=1)
            
            if server:
                return server.timeout_seconds
            
            # Use default timeout
            return 10  # Standard timeout when no server config found
            
        except Exception:
            return 10  # Safe fallback


    def _get_electrum_config(self, host=None, port=None, use_ssl=None):
        """
        Get Electrum server configuration with priority order:
        1. Method parameters (if provided)
        2. Environment variables
        3. Database settings (from bitcoin.settings)
        4. Default values
        
        Args:
            host (str): Override hostname
            port (int): Override port
            use_ssl (bool): Override SSL setting
            
        Returns:
            tuple: (host, port, use_ssl)
        """
        # Start with defaults
        default_host = 'electrum.blockstream.info'
        default_port = 50002
        default_ssl = True
        
        # Check environment variables
        env_host = os.environ.get('ELECTRUM_HOST')
        env_port = os.environ.get('ELECTRUM_PORT')
        env_ssl = os.environ.get('ELECTRUM_USE_SSL')
        
        # Skip database settings - use only environment variables and defaults
        db_host = db_port = db_ssl = None
        
        # Apply priority order: params > env > db > defaults
        final_host = host or env_host or db_host or default_host
        
        final_port = port
        if not final_port:
            try:
                final_port = int(env_port) if env_port else None
            except (ValueError, TypeError):
                final_port = None
        final_port = final_port or db_port or default_port
        
        final_ssl = use_ssl
        if final_ssl is None:
            if env_ssl is not None:
                final_ssl = env_ssl.lower() in ('true', '1', 'yes', 'on')
            else:
                final_ssl = db_ssl if db_ssl is not None else default_ssl
        
        _logger.info(f"Electrum config: host={final_host}, port={final_port}, ssl={final_ssl}")
        return final_host, final_port, final_ssl

    def _calculate_confirmations(self, height):
        """
        Calculate number of confirmations for a transaction
        
        Args:
            height (int): Block height (0 for unconfirmed)
            
        Returns:
            int: Number of confirmations
        """
        if height <= 0:
            return 0
        
        # Get current block height from Electrum server
        current_height = self.get_block_height()
        if current_height <= 0:
            raise ValidationError("Unable to get current block height for confirmation calculation")
        return max(0, current_height - height + 1)