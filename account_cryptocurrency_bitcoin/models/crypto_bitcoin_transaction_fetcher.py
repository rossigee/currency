# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import requests
import json
import logging
import socket
import time
from datetime import datetime

_logger = logging.getLogger(__name__)


class CryptoBitcoinTransactionFetcher(models.Model):
    _name = 'crypto.bitcoin.transaction.fetcher'
    _description = 'Bitcoin Transaction Fetcher Utility'

    name = fields.Char(string='Service Name', required=True)
    service_type = fields.Selection([
        ('blockstream', 'Blockstream API'),
        ('mempool', 'Mempool.space API'),
        ('electrum', 'Electrum Server'),
        ('custom', 'Custom API')
    ], string='Service Type', required=True, default='blockstream')
    
    # Connection settings
    base_url = fields.Char(string='Base URL', help="Base URL for the API service")
    electrum_host = fields.Char(string='Electrum Host', help="Electrum server hostname")
    electrum_port = fields.Integer(string='Electrum Port', default=50002, help="Electrum server port")
    use_ssl = fields.Boolean(string='Use SSL', default=True, help="Use SSL for Electrum connection")
    
    # Network
    network = fields.Selection([
        ('mainnet', 'Bitcoin Mainnet'),
        ('testnet', 'Bitcoin Testnet')
    ], string='Network', required=True, default='mainnet')
    
    # Rate limiting
    rate_limit_delay = fields.Float(string='Rate Limit Delay (seconds)', default=0.1, 
                                   help="Delay between API requests to avoid rate limiting")
    max_retries = fields.Integer(string='Max Retries', default=3, help="Maximum number of retry attempts")
    
    # Status
    last_used = fields.Datetime(string='Last Used')
    is_active = fields.Boolean(string='Active', default=True)
    status_message = fields.Text(string='Status Message')

    @api.model
    def get_default_fetcher(self, network='mainnet'):
        """Get the default active fetcher for a network"""
        fetcher = self.search([
            ('network', '=', network),
            ('is_active', '=', True)
        ], limit=1, order='last_used desc')
        
        if not fetcher:
            # Create default Blockstream fetcher
            base_urls = {
                'mainnet': 'https://blockstream.info/api',
                'testnet': 'https://blockstream.info/testnet/api'
            }
            fetcher = self.create({
                'name': f'Blockstream API ({network.title()})',
                'service_type': 'blockstream',
                'base_url': base_urls[network],
                'network': network,
                'is_active': True
            })
            _logger.info(f"Created default transaction fetcher: {fetcher.name}")
        
        return fetcher

    def test_connection(self):
        """Test connection to the service"""
        self.ensure_one()
        
        try:
            if self.service_type == 'electrum':
                return self._test_electrum_connection()
            else:
                return self._test_api_connection()
        except Exception as e:
            self.status_message = f"Connection test failed: {str(e)}"
            return False

    def _test_electrum_connection(self):
        """Test Electrum server connection"""
        try:
            import socket
            import ssl
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            
            if self.use_ssl:
                context = ssl.create_default_context()
                sock = context.wrap_socket(sock, server_hostname=self.electrum_host)
            
            sock.connect((self.electrum_host, self.electrum_port))
            
            # Send a test request
            request = {"id": 1, "method": "server.version", "params": []}
            sock.send((json.dumps(request) + '\n').encode())
            response = sock.recv(1024).decode()
            sock.close()
            
            if 'result' in response:
                self.status_message = "Electrum connection successful"
                return True
            else:
                self.status_message = f"Electrum connection failed: {response}"
                return False
                
        except Exception as e:
            self.status_message = f"Electrum connection error: {str(e)}"
            return False

    def _test_api_connection(self):
        """Test API connection"""
        try:
            test_url = f"{self.base_url}/blocks/tip/height"
            response = requests.get(test_url, timeout=10)
            
            if response.status_code == 200:
                self.status_message = f"API connection successful (height: {response.text})"
                return True
            else:
                self.status_message = f"API connection failed: HTTP {response.status_code}"
                return False
                
        except Exception as e:
            self.status_message = f"API connection error: {str(e)}"
            return False

    def fetch_address_transactions(self, address):
        """Fetch all transactions for a Bitcoin address"""
        self.ensure_one()
        
        if self.service_type == 'electrum':
            return self._fetch_address_transactions_electrum(address)
        else:
            return self._fetch_address_transactions_api(address)

    def _fetch_address_transactions_api(self, address):
        """Fetch transactions via API (Blockstream/Mempool.space)"""
        try:
            self._update_last_used()
            
            if self.service_type == 'blockstream':
                url = f"{self.base_url}/address/{address}/txs"
            elif self.service_type == 'mempool':
                url = f"{self.base_url}/address/{address}/txs"
            else:
                raise ValidationError(f"Unsupported API service type: {self.service_type}")
            
            transactions = []
            last_seen_txid = None
            
            # Paginate through all transactions
            while True:
                paginated_url = url
                if last_seen_txid:
                    paginated_url = f"{url}/{last_seen_txid}"
                
                _logger.info(f"Fetching transactions: {paginated_url}")
                
                response = requests.get(paginated_url, timeout=30)
                if response.status_code != 200:
                    raise UserError(f"API request failed: HTTP {response.status_code}")
                
                batch = response.json()
                _logger.info(f"API response type: {type(batch)}, length: {len(batch) if isinstance(batch, list) else 'N/A'}")
                
                # Handle empty response (no transactions or end of pagination)
                if not batch or len(batch) == 0:
                    _logger.info(f"No more transactions found for address {address}")
                    break
                
                transactions.extend(batch)
                
                # Check if we need to paginate (Blockstream returns up to 25 per page)
                if len(batch) < 25:
                    _logger.info(f"Received partial batch ({len(batch)} transactions), pagination complete")
                    break
                
                # Set up for next page
                last_seen_txid = batch[-1]['txid']
                _logger.info(f"Fetched {len(batch)} transactions, continuing with last_seen_txid: {last_seen_txid[:16]}...")
                time.sleep(self.rate_limit_delay)
            
            _logger.info(f"Fetched {len(transactions)} transactions for address {address}")
            _logger.debug(f"About to normalize transactions: {[type(tx) for tx in transactions[:3]]}")  # Show types of first 3
            return self._normalize_transaction_data(transactions)
            
        except Exception as e:
            _logger.error(f"Failed to fetch transactions for {address}: {str(e)}")
            raise UserError(f"Failed to fetch transactions: {str(e)}")

    def _fetch_address_transactions_electrum(self, address):
        """Fetch transactions via Electrum protocol"""
        # This would require implementing the Electrum protocol
        # For now, fall back to API method
        _logger.warning("Electrum protocol not yet implemented, falling back to API")
        return []

    def fetch_transaction_details(self, txid):
        """Fetch detailed transaction information by transaction ID"""
        self.ensure_one()
        
        try:
            self._update_last_used()
            
            if self.service_type in ['blockstream', 'mempool']:
                url = f"{self.base_url}/tx/{txid}"
                response = requests.get(url, timeout=30)
                
                if response.status_code != 200:
                    raise UserError(f"Transaction not found: {txid}")
                
                tx_data = response.json()
                return self._normalize_transaction_data([tx_data])[0]
            else:
                raise ValidationError(f"Transaction lookup not supported for: {self.service_type}")
                
        except Exception as e:
            _logger.error(f"Failed to fetch transaction {txid}: {str(e)}")
            raise UserError(f"Failed to fetch transaction: {str(e)}")

    def _normalize_transaction_data(self, raw_transactions):
        """Normalize transaction data from different APIs"""
        normalized = []
        
        _logger.info(f"Normalizing {len(raw_transactions)} transactions")
        _logger.info(f"Raw transactions type: {type(raw_transactions)}")
        if raw_transactions:
            _logger.info(f"First element type: {type(raw_transactions[0])}")
            _logger.info(f"First element preview: {str(raw_transactions[0])[:200]}")
        
        for i, tx in enumerate(raw_transactions):
            try:
                # Debug: Check if tx is the expected format
                _logger.info(f"Processing transaction {i}: type={type(tx)}")
                if not isinstance(tx, dict):
                    _logger.error(f"Transaction {i} is not a dict: type={type(tx)}, value={str(tx)[:200]}")
                    continue
                
                # Common fields across APIs
                _logger.info(f"Getting txid from tx...")
                txid = tx.get('txid')
                _logger.info(f"Got txid: {txid}")
                
                normalized_tx = {
                    'txid': txid,
                    'version': tx.get('version', 1),
                    'locktime': tx.get('locktime', 0),
                    'size': tx.get('size', 0),
                    'weight': tx.get('weight', 0),
                    'fee': tx.get('fee', 0),
                    'status': tx.get('status', {}),
                    'block_height': None,
                    'block_hash': None,
                    'block_time': None,
                    'confirmations': 0,
                    'inputs': [],
                    'outputs': []
                }
                _logger.info(f"Created normalized_tx structure")
                
                # Handle confirmation status
                _logger.info(f"Processing status...")
                if 'status' in tx and tx['status'].get('confirmed'):
                    _logger.info(f"Transaction is confirmed, getting block info...")
                    normalized_tx['block_height'] = tx['status'].get('block_height')
                    normalized_tx['block_hash'] = tx['status'].get('block_hash')
                    normalized_tx['block_time'] = tx['status'].get('block_time')
                    
                    # Calculate confirmations (approximate)
                    if normalized_tx['block_height']:
                        _logger.info(f"Getting current block height...")
                        current_height = self._get_current_block_height()
                        if current_height:
                            normalized_tx['confirmations'] = max(0, current_height - normalized_tx['block_height'] + 1)
                _logger.info(f"Status processing complete")
                
                # Process inputs
                _logger.info(f"Processing {len(tx.get('vin', []))} inputs...")
                for vin in tx.get('vin', []):
                    _logger.info(f"Processing input, type: {type(vin)}")
                    normalized_input = {
                        'txid': vin.get('txid'),
                        'vout': vin.get('vout'),
                        'sequence': vin.get('sequence'),
                        'scriptsig': vin.get('scriptsig', {}),
                        'prevout': vin.get('prevout', {}),
                        'witness': vin.get('witness', [])
                    }
                    normalized_tx['inputs'].append(normalized_input)
                
                # Process outputs  
                _logger.info(f"Processing {len(tx.get('vout', []))} outputs...")
                for vout in tx.get('vout', []):
                    _logger.info(f"Processing output, type: {type(vout)}")
                    
                    # Handle scriptpubkey safely - it might be a string or dict
                    scriptpubkey = vout.get('scriptpubkey', {})
                    if isinstance(scriptpubkey, dict):
                        scriptpubkey_address = scriptpubkey.get('address')
                    else:
                        # scriptpubkey is a string (hex), no address available
                        scriptpubkey_address = None
                        _logger.debug(f"scriptpubkey is string: {scriptpubkey}")
                    
                    normalized_output = {
                        'value': vout.get('value', 0),
                        'scriptpubkey': scriptpubkey,
                        'scriptpubkey_address': scriptpubkey_address
                    }
                    normalized_tx['outputs'].append(normalized_output)
                
                _logger.info(f"Appending normalized transaction to result list...")
                normalized.append(normalized_tx)
                _logger.info(f"Transaction {i} normalization complete")
                
            except Exception as e:
                tx_id = tx.get('txid', 'unknown') if isinstance(tx, dict) else str(tx)[:50]
                _logger.warning(f"Failed to normalize transaction {tx_id}: {str(e)}")
                _logger.debug(f"Raw transaction data: {tx}")
                continue
        
        return normalized

    def _get_current_block_height(self):
        """Get current blockchain height"""
        try:
            url = f"{self.base_url}/blocks/tip/height"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return int(response.text)
        except:
            pass
        return None

    def _update_last_used(self):
        """Update last used timestamp"""
        self.last_used = fields.Datetime.now()

    def fetch_wallet_transactions(self, wallet_addresses):
        """Fetch transactions for multiple addresses (wallet)"""
        self.ensure_one()
        
        all_transactions = {}
        
        for address in wallet_addresses:
            try:
                transactions = self.fetch_address_transactions(address)
                all_transactions[address] = transactions
                time.sleep(self.rate_limit_delay)
            except Exception as e:
                _logger.error(f"Failed to fetch transactions for address {address}: {str(e)}")
                all_transactions[address] = []
        
        return all_transactions

    @api.model
    def create_default_fetchers(self):
        """Create default transaction fetchers for both networks"""
        for network in ['mainnet', 'testnet']:
            existing = self.search([('network', '=', network)], limit=1)
            if not existing:
                self.get_default_fetcher(network)
        
        return True