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
            # Fallback to bitcoin.settings configuration
            try:
                services_config = self.env['bitcoin.settings'].get_services_config()
                if not services_config['electrum']['enabled']:
                    raise ValidationError("Electrum integration is disabled")
                return self
            except:
                # Create default server configurations
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
            # Get configured servers in priority order
            servers = self.env['electrum.server.config'].get_failover_chain()
            
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
        """Get history from a specific Electrum server with configurable timeout"""
        try:
            # Get history from Electrum server
            history = self._electrum_request(
                host=host,
                port=port,
                use_ssl=use_ssl,
                method="blockchain.scripthash.get_history",
                params=[script_hash],
                timeout=timeout
            )
            
            _logger.info(f"Electrum server {host}:{port} returned {len(history)} transactions")
            
            # Convert to standardized format
            transactions = []
            for item in history:
                tx_data = {
                    'txid': item['tx_hash'],
                    'height': item.get('height', 0),
                    'fee': item.get('fee', 0),
                    # Note: Electrum history gives just basic info
                    # For full transaction details, need additional calls
                    'confirmations': self._calculate_confirmations(item.get('height', 0)),
                    'value': 0,    # Would need full transaction data
                    'vin': [],     # Would need full transaction data
                    'vout': []     # Would need full transaction data
                }
                transactions.append(tx_data)
            
            return transactions
            
        except Exception as e:
            _logger.error(f"Server {host}:{port} failed: {str(e)}")
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
            servers = self.env['electrum.server.config'].get_failover_chain(max_servers=3)
            
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
            
            # Fallback to bitcoin.settings configuration
            try:
                services_config = self.env['bitcoin.settings'].get_services_config()
                return 15  # Standard timeout for legacy configurations
            except:
                pass
                
            # Ultimate fallback
            return 10  # Conservative default
            
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
        
        # Check database settings
        try:
            settings = self.env['bitcoin.settings'].get_default_settings()
            db_host = getattr(settings, 'electrum_host', None)
            db_port = getattr(settings, 'electrum_port', None)
            db_ssl = getattr(settings, 'electrum_use_ssl', None)
        except:
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
        
        # Calculate confirmations based on current blockchain height
        current_height = 800000  # TODO: Get actual current height from server
        return max(0, current_height - height + 1)