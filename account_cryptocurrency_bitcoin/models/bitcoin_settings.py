# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class BitcoinSettings(models.Model):
    _name = 'bitcoin.settings'
    _description = 'Bitcoin Module Settings'
    _rec_name = 'name'

    name = fields.Char(string='Configuration Name', required=True, default='Bitcoin Configuration')
    
    # Active configuration
    is_default = fields.Boolean(string='Default Configuration', default=False,
                               help="Mark this as the default configuration to use")
    
    # Bitcoin Node Connection
    use_local_node = fields.Boolean(string='Use Local Bitcoin Node', default=True,
                                   help="Use local Bitcoin Core node instead of external APIs")
    
    # Local Node Settings
    node_rpc_host = fields.Char(string='Bitcoin Node Host', default='localhost')
    node_rpc_port = fields.Integer(string='Bitcoin Node Port', default=8332)
    node_rpc_user = fields.Char(string='RPC Username')
    node_rpc_password = fields.Char(string='RPC Password')
    node_use_ssl = fields.Boolean(string='Use SSL for Node Connection', default=False)
    node_network = fields.Selection([
        ('mainnet', 'Bitcoin Mainnet'),
        ('testnet', 'Bitcoin Testnet'),
        ('regtest', 'Regtest'),
        ('signet', 'Signet')
    ], string='Bitcoin Network', default='mainnet', required=True)
    
    # External API Settings (fallback)
    external_api_provider = fields.Selection([
        ('blockstream', 'Blockstream API'),
        ('mempool', 'Mempool.space API'),
        ('custom', 'Custom API')
    ], string='External API Provider', default='blockstream')
    
    custom_api_base_url = fields.Char(string='Custom API Base URL',
                                     help="Base URL for custom blockchain API")
    api_rate_limit_delay = fields.Float(string='API Rate Limit Delay (seconds)', default=0.1)
    api_max_retries = fields.Integer(string='API Max Retries', default=3)
    
    # Transaction Import Settings
    max_addresses_per_import = fields.Integer(string='Max Addresses per Import', default=50,
                                            help="Limit number of addresses to check in one import operation")
    import_chunk_size = fields.Integer(string='Import Chunk Size', default=5,
                                     help="Number of addresses to process before showing progress notification")
    import_delay_between_addresses = fields.Float(string='Delay Between Addresses (seconds)', default=0.5,
                                                 help="Delay between API calls to avoid rate limiting")
    
    # Cache Settings
    blockchain_info_cache_minutes = fields.Integer(string='Blockchain Info Cache (minutes)', default=5,
                                                  help="How long to cache current block height and network info")
    
    # Status and Testing
    connection_status = fields.Selection([
        ('untested', 'Not Tested'),
        ('connected', 'Connected'),
        ('failed', 'Connection Failed')
    ], string='Connection Status', default='untested', readonly=True)
    last_test_date = fields.Datetime(string='Last Connection Test', readonly=True)
    status_message = fields.Text(string='Status Message', readonly=True)

    @api.constrains('is_default')
    def _check_single_default(self):
        """Ensure only one configuration is marked as default"""
        if self.is_default:
            other_defaults = self.search([
                ('is_default', '=', True),
                ('id', '!=', self.id)
            ])
            if other_defaults:
                other_defaults.write({'is_default': False})

    @api.model
    def get_default_settings(self):
        """Get the default Bitcoin settings configuration"""
        settings = self.search([('is_default', '=', True)], limit=1)
        
        if not settings:
            # Create default settings if none exist
            settings = self.create({
                'name': 'Default Bitcoin Configuration',
                'is_default': True
            })
            _logger.info("Created default Bitcoin settings configuration")
            
        return settings

    def action_test_connection(self):
        """Test the Bitcoin connection based on current settings"""
        self.ensure_one()
        
        try:
            if self.use_local_node:
                success = self._test_local_node_connection()
            else:
                success = self._test_external_api_connection()
                
            if success:
                self.write({
                    'connection_status': 'connected',
                    'last_test_date': fields.Datetime.now(),
                    'status_message': 'Connection test successful'
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Connection Successful',
                        'message': self.status_message,
                        'type': 'success'
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Connection Failed',
                        'message': self.status_message,
                        'type': 'danger'
                    }
                }
                
        except Exception as e:
            error_msg = f"Connection test failed: {str(e)}"
            self.write({
                'connection_status': 'failed',
                'last_test_date': fields.Datetime.now(),
                'status_message': error_msg
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Connection Test Error',
                    'message': error_msg,
                    'type': 'danger'
                }
            }

    def _test_local_node_connection(self):
        """Test connection to local Bitcoin node"""
        try:
            # Create a temporary Bitcoin connector to test
            connector_vals = {
                'name': 'Test Connection',
                'rpc_host': self.node_rpc_host,
                'rpc_port': self.node_rpc_port,
                'rpc_user': self.node_rpc_user,
                'rpc_password': self.node_rpc_password,
                'use_ssl': self.node_use_ssl,
                'network': self.node_network,
                'is_active': False  # Don't make it active
            }
            
            test_connector = self.env['bitcoin.connector'].create(connector_vals)
            
            try:
                # Test the connection
                blockchain_info = test_connector._make_rpc_call('getblockchaininfo')
                network_info = test_connector._make_rpc_call('getnetworkinfo')
                
                self.status_message = (
                    f"✅ Connected to {blockchain_info.get('chain', 'unknown')} network\n"
                    f"📊 Block height: {blockchain_info.get('blocks', 0)}\n"
                    f"🔗 Node version: {network_info.get('subversion', 'unknown')}\n"
                    f"👥 Connections: {network_info.get('connections', 0)}"
                )
                
                return True
                
            finally:
                # Clean up test connector
                test_connector.unlink()
                
        except Exception as e:
            self.status_message = f"❌ Local node connection failed: {str(e)}"
            return False

    def _test_external_api_connection(self):
        """Test connection to external blockchain API"""
        try:
            import requests
            
            # Build test URL based on provider
            if self.external_api_provider == 'blockstream':
                if self.node_network == 'mainnet':
                    test_url = 'https://blockstream.info/api/blocks/tip/height'
                else:
                    test_url = 'https://blockstream.info/testnet/api/blocks/tip/height'
            elif self.external_api_provider == 'mempool':
                if self.node_network == 'mainnet':
                    test_url = 'https://mempool.space/api/blocks/tip/height'
                else:
                    test_url = 'https://mempool.space/testnet/api/blocks/tip/height'
            elif self.external_api_provider == 'custom' and self.custom_api_base_url:
                test_url = f"{self.custom_api_base_url}/blocks/tip/height"
            else:
                raise ValidationError("Invalid API provider configuration")
            
            response = requests.get(test_url, timeout=10)
            
            if response.status_code == 200:
                block_height = response.text.strip()
                self.status_message = (
                    f"✅ Connected to {self.external_api_provider} API\n"
                    f"📊 Current block height: {block_height}\n"
                    f"🌐 Network: {self.node_network}"
                )
                return True
            else:
                self.status_message = f"❌ API request failed: HTTP {response.status_code}"
                return False
                
        except Exception as e:
            self.status_message = f"❌ External API connection failed: {str(e)}"
            return False

    def get_bitcoin_connector(self):
        """Get or create Bitcoin connector based on current settings"""
        self.ensure_one()
        
        if not self.use_local_node:
            return None  # Will use external APIs
            
        # Look for existing connector with matching settings
        existing_connector = self.env['bitcoin.connector'].search([
            ('rpc_host', '=', self.node_rpc_host),
            ('rpc_port', '=', self.node_rpc_port),
            ('rpc_user', '=', self.node_rpc_user),
            ('network', '=', self.node_network),
            ('is_active', '=', True)
        ], limit=1)
        
        if existing_connector:
            return existing_connector
            
        # Create new connector
        connector = self.env['bitcoin.connector'].create({
            'name': f'{self.name} - Bitcoin Node',
            'rpc_host': self.node_rpc_host,
            'rpc_port': self.node_rpc_port,
            'rpc_user': self.node_rpc_user,
            'rpc_password': self.node_rpc_password,
            'use_ssl': self.node_use_ssl,
            'network': self.node_network,
            'is_active': True,
            'cache_duration_minutes': self.blockchain_info_cache_minutes
        })
        
        return connector

    def get_transaction_fetcher(self):
        """Get or create transaction fetcher based on current settings"""
        self.ensure_one()
        
        if self.use_local_node:
            # Bitcoin connector will handle transaction fetching
            return None
            
        # Look for existing fetcher
        fetcher = self.env['crypto.bitcoin.transaction.fetcher'].search([
            ('service_type', '=', self.external_api_provider),
            ('network', '=', self.node_network),
            ('is_active', '=', True)
        ], limit=1)
        
        if fetcher:
            # Update settings
            fetcher.write({
                'rate_limit_delay': self.api_rate_limit_delay,
                'max_retries': self.api_max_retries
            })
            return fetcher
            
        # Create new fetcher
        base_urls = {
            'blockstream': {
                'mainnet': 'https://blockstream.info/api',
                'testnet': 'https://blockstream.info/testnet/api'
            },
            'mempool': {
                'mainnet': 'https://mempool.space/api',
                'testnet': 'https://mempool.space/testnet/api'
            }
        }
        
        base_url = self.custom_api_base_url
        if self.external_api_provider in base_urls:
            base_url = base_urls[self.external_api_provider].get(self.node_network)
            
        fetcher = self.env['crypto.bitcoin.transaction.fetcher'].create({
            'name': f'{self.name} - {self.external_api_provider.title()} API',
            'service_type': self.external_api_provider,
            'base_url': base_url,
            'network': self.node_network,
            'rate_limit_delay': self.api_rate_limit_delay,
            'max_retries': self.api_max_retries,
            'is_active': True
        })
        
        return fetcher

    @api.model
    def get_import_settings(self):
        """Get transaction import settings from default configuration"""
        settings = self.get_default_settings()
        return {
            'max_addresses': settings.max_addresses_per_import,
            'chunk_size': settings.import_chunk_size,
            'delay_between_addresses': settings.import_delay_between_addresses
        }