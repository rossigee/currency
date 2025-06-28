# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import requests
import json
import logging
import os
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class BitcoinConnector(models.Model):
    _name = 'bitcoin.connector'
    _description = 'Bitcoin Node Connector'
    _rec_name = 'name'

    name = fields.Char(string='Connection Name', required=True, default='Bitcoin Core')
    
    # Connection settings
    rpc_host = fields.Char(string='RPC Host', required=True, default='localhost')
    rpc_port = fields.Integer(string='RPC Port', required=True, default=8332)
    rpc_user = fields.Char(string='RPC Username', required=True)
    rpc_password = fields.Char(string='RPC Password', required=True)
    use_ssl = fields.Boolean(string='Use SSL', default=False)
    
    # Network
    network = fields.Selection([
        ('mainnet', 'Bitcoin Mainnet'),
        ('testnet', 'Bitcoin Testnet'),
        ('regtest', 'Regtest'),
        ('signet', 'Signet')
    ], string='Network', required=True, default='mainnet')
    
    # Status and monitoring
    is_active = fields.Boolean(string='Active', default=True)
    last_connected = fields.Datetime(string='Last Connected')
    connection_status = fields.Selection([
        ('unknown', 'Unknown'),
        ('connected', 'Connected'),
        ('error', 'Connection Error'),
        ('auth_failed', 'Authentication Failed'),
        ('timeout', 'Timeout')
    ], string='Status', default='unknown', readonly=True)
    status_message = fields.Text(string='Status Message', readonly=True)
    
    # Node info (cached)
    node_version = fields.Char(string='Node Version', readonly=True)
    current_block_height = fields.Integer(string='Current Block Height', readonly=True)
    best_block_hash = fields.Char(string='Best Block Hash', readonly=True)
    chain = fields.Char(string='Chain', readonly=True)
    last_block_time = fields.Datetime(string='Last Block Time', readonly=True)
    
    # Cache settings
    cache_duration_minutes = fields.Integer(string='Cache Duration (minutes)', default=5,
                                          help="How long to cache blockchain info before refreshing")

    @api.model
    def get_default_connector(self, network='mainnet'):
        """Get the default active connector for a network"""
        connector = self.search([
            ('network', '=', network),
            ('is_active', '=', True)
        ], limit=1, order='last_connected desc')
        
        if not connector:
            # Try to create from environment variables
            connector = self._create_from_env(network)
            
        if not connector:
            raise UserError(f"No active Bitcoin connector found for {network}. Please configure a Bitcoin node connection.")
            
        return connector

    @api.model 
    def _create_from_env(self, network='mainnet'):
        """Create connector from environment variables"""
        try:
            env_vars = {
                'host': os.environ.get('BITCOIN_RPC_HOST', 'localhost'),
                'port': int(os.environ.get('BITCOIN_RPC_PORT', '8332')),
                'user': os.environ.get('BITCOIN_RPC_USER'),
                'password': os.environ.get('BITCOIN_RPC_PASSWORD'),
                'ssl': os.environ.get('BITCOIN_RPC_SSL', 'false').lower() == 'true'
            }
            
            if not env_vars['user'] or not env_vars['password']:
                _logger.warning("Bitcoin RPC credentials not found in environment variables")
                return None
                
            connector = self.create({
                'name': f'Bitcoin Core ({network})',
                'rpc_host': env_vars['host'],
                'rpc_port': env_vars['port'],
                'rpc_user': env_vars['user'],
                'rpc_password': env_vars['password'],
                'use_ssl': env_vars['ssl'],
                'network': network,
                'is_active': True
            })
            
            _logger.info(f"Created Bitcoin connector from environment: {connector.name}")
            return connector
            
        except Exception as e:
            _logger.warning(f"Failed to create Bitcoin connector from environment: {str(e)}")
            return None

    def _get_rpc_url(self):
        """Build RPC URL"""
        protocol = 'https' if self.use_ssl else 'http'
        return f"{protocol}://{self.rpc_host}:{self.rpc_port}/"

    def _make_rpc_call(self, method, params=None):
        """Make RPC call to Bitcoin node"""
        if params is None:
            params = []
            
        payload = {
            "jsonrpc": "2.0",
            "id": "odoo",
            "method": method,
            "params": params
        }
        
        try:
            response = requests.post(
                self._get_rpc_url(),
                json=payload,
                auth=(self.rpc_user, self.rpc_password),
                timeout=30,
                verify=False if not self.use_ssl else True
            )
            
            if response.status_code == 401:
                self.connection_status = 'auth_failed'
                self.status_message = "Authentication failed - check RPC credentials"
                raise UserError("Bitcoin RPC authentication failed")
                
            elif response.status_code != 200:
                self.connection_status = 'error'
                self.status_message = f"HTTP {response.status_code}: {response.text}"
                raise UserError(f"Bitcoin RPC request failed: HTTP {response.status_code}")
            
            data = response.json()
            
            if 'error' in data and data['error']:
                error_msg = data['error'].get('message', 'Unknown RPC error')
                self.connection_status = 'error'
                self.status_message = f"RPC Error: {error_msg}"
                raise UserError(f"Bitcoin RPC error: {error_msg}")
                
            self.connection_status = 'connected'
            self.last_connected = fields.Datetime.now()
            self.status_message = f"Connected successfully at {self.last_connected}"
            
            return data.get('result')
            
        except requests.exceptions.Timeout:
            self.connection_status = 'timeout'
            self.status_message = "Connection timeout"
            raise UserError("Bitcoin RPC connection timeout")
            
        except requests.exceptions.ConnectionError:
            self.connection_status = 'error'
            self.status_message = "Connection refused - check if Bitcoin node is running"
            raise UserError("Cannot connect to Bitcoin node - check if it's running and accessible")
            
        except Exception as e:
            self.connection_status = 'error'
            self.status_message = str(e)
            raise UserError(f"Bitcoin RPC error: {str(e)}")

    def test_connection(self):
        """Test connection to Bitcoin node"""
        try:
            info = self._make_rpc_call('getblockchaininfo')
            self.node_version = str(info.get('initialblockdownload', 'Unknown'))
            self.current_block_height = info.get('blocks', 0)
            self.best_block_hash = info.get('bestblockhash', '')
            self.chain = info.get('chain', 'unknown')
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Connection Successful',
                    'message': f"Connected to {self.chain} at block {self.current_block_height}",
                    'type': 'success'
                }
            }
            
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Connection Failed',
                    'message': str(e),
                    'type': 'danger'
                }
            }

    def refresh_blockchain_info(self):
        """Refresh cached blockchain information"""
        try:
            info = self._make_rpc_call('getblockchaininfo')
            network_info = self._make_rpc_call('getnetworkinfo')
            
            self.write({
                'node_version': network_info.get('subversion', 'Unknown'),
                'current_block_height': info.get('blocks', 0),
                'best_block_hash': info.get('bestblockhash', ''),
                'chain': info.get('chain', 'unknown'),
                'last_block_time': fields.Datetime.now()
            })
            
            _logger.info(f"Updated blockchain info: {self.chain} block {self.current_block_height}")
            
        except Exception as e:
            _logger.error(f"Failed to refresh blockchain info: {str(e)}")
            raise

    def get_current_block_height(self, force_refresh=False):
        """Get current blockchain height with caching"""
        # Check if we need to refresh cache
        if (force_refresh or 
            not self.last_block_time or 
            self.last_block_time < datetime.now() - timedelta(minutes=self.cache_duration_minutes)):
            
            self.refresh_blockchain_info()
            
        return self.current_block_height

    def get_transaction_confirmations(self, tx_hash, block_height):
        """Get real-time confirmation count for a transaction"""
        if not block_height:
            return 0
            
        current_height = self.get_current_block_height()
        return max(0, current_height - block_height + 1)

    def get_transaction_details(self, tx_hash):
        """Get detailed transaction information from node"""
        try:
            # Get raw transaction
            raw_tx = self._make_rpc_call('getrawtransaction', [tx_hash, True])
            
            # Calculate confirmations
            confirmations = 0
            if 'confirmations' in raw_tx:
                confirmations = raw_tx['confirmations']
            elif 'blockhash' in raw_tx:
                # Get block info to calculate confirmations
                block_info = self._make_rpc_call('getblock', [raw_tx['blockhash']])
                confirmations = self.get_transaction_confirmations(tx_hash, block_info['height'])
            
            return {
                'txid': raw_tx['txid'],
                'size': raw_tx.get('size', 0),
                'vsize': raw_tx.get('vsize', 0),
                'weight': raw_tx.get('weight', 0),
                'fee': raw_tx.get('fee'),  # May not be available for all transactions
                'confirmations': confirmations,
                'block_height': block_info.get('height') if 'block_info' in locals() else None,
                'block_hash': raw_tx.get('blockhash'),
                'block_time': raw_tx.get('blocktime'),
                'inputs': raw_tx.get('vin', []),
                'outputs': raw_tx.get('vout', [])
            }
            
        except Exception as e:
            _logger.error(f"Failed to get transaction details for {tx_hash}: {str(e)}")
            raise UserError(f"Failed to get transaction details: {str(e)}")

    def get_address_transactions(self, address, count=100):
        """Get transactions for an address (requires txindex=1 on node)"""
        try:
            # This requires Bitcoin Core with txindex enabled
            # Alternative: use scantxoutset for UTXO scanning
            result = self._make_rpc_call('scantxoutset', ['start', [f'addr({address})']])
            
            transactions = []
            for utxo in result.get('unspents', []):
                tx_details = self.get_transaction_details(utxo['txid'])
                transactions.append(tx_details)
                
            return transactions
            
        except Exception as e:
            _logger.warning(f"Address transaction lookup failed for {address}: {str(e)}")
            # Fallback to external API if node doesn't support this operation
            return []

    def estimate_fee(self, target_blocks=6):
        """Estimate fee rate for confirmation within target blocks"""
        try:
            # Try estimatesmartfee first (newer method)
            result = self._make_rpc_call('estimatesmartfee', [target_blocks])
            
            if 'feerate' in result:
                # Convert BTC/kB to sat/vB
                btc_per_kb = result['feerate']
                sat_per_vb = (btc_per_kb * 100000000) / 1000
                return {
                    'feerate_sat_vb': sat_per_vb,
                    'feerate_btc_kb': btc_per_kb,
                    'blocks': target_blocks
                }
            else:
                _logger.warning("Fee estimation not available from node")
                return None
                
        except Exception as e:
            _logger.error(f"Fee estimation failed: {str(e)}")
            return None

    def broadcast_transaction(self, raw_tx_hex):
        """Broadcast a signed transaction to the network"""
        try:
            result = self._make_rpc_call('sendrawtransaction', [raw_tx_hex])
            _logger.info(f"Transaction broadcast successfully: {result}")
            return result  # Returns txid if successful
            
        except Exception as e:
            _logger.error(f"Transaction broadcast failed: {str(e)}")
            raise UserError(f"Failed to broadcast transaction: {str(e)}")

    @api.model
    def get_network_stats(self):
        """Get network statistics"""
        try:
            connector = self.get_default_connector()
            
            blockchain_info = connector._make_rpc_call('getblockchaininfo')
            network_info = connector._make_rpc_call('getnetworkinfo')
            mining_info = connector._make_rpc_call('getmininginfo')
            
            return {
                'block_height': blockchain_info.get('blocks'),
                'difficulty': blockchain_info.get('difficulty'),
                'network_hash_rate': mining_info.get('networkhashps'),
                'connected_peers': network_info.get('connections'),
                'mempool_size': connector._make_rpc_call('getmempoolinfo').get('size', 0)
            }
            
        except Exception as e:
            _logger.error(f"Failed to get network stats: {str(e)}")
            return {}