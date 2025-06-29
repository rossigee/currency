# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Bitcoin Node Connection
    bitcoin_use_local_node = fields.Boolean(
        string='Use Local Bitcoin Node',
        config_parameter='bitcoin.use_local_node',
        default=True,
        help="Use local Bitcoin Core node instead of external APIs"
    )
    
    bitcoin_node_rpc_host = fields.Char(
        string='Bitcoin Node Host',
        config_parameter='bitcoin.node_rpc_host',
        default='localhost'
    )
    
    bitcoin_node_rpc_port = fields.Integer(
        string='Bitcoin Node Port',
        config_parameter='bitcoin.node_rpc_port',
        default=8332
    )
    
    bitcoin_node_rpc_user = fields.Char(
        string='RPC Username',
        config_parameter='bitcoin.node_rpc_user'
    )
    
    bitcoin_node_rpc_password = fields.Char(
        string='RPC Password',
        config_parameter='bitcoin.node_rpc_password'
    )
    
    bitcoin_node_use_ssl = fields.Boolean(
        string='Use SSL for Node Connection',
        config_parameter='bitcoin.node_use_ssl',
        default=False
    )
    
    bitcoin_network = fields.Selection([
        ('mainnet', 'Bitcoin Mainnet'),
        ('testnet', 'Bitcoin Testnet'),
        ('regtest', 'Regtest'),
        ('signet', 'Signet')
    ], string='Bitcoin Network',
       config_parameter='bitcoin.network',
       default='mainnet',
       required=True)
    
    # External API Settings (fallback)
    bitcoin_external_api_provider = fields.Selection([
        ('blockstream', 'Blockstream API'),
        ('mempool', 'Mempool.space API'),
        ('custom', 'Custom API')
    ], string='External API Provider',
       config_parameter='bitcoin.external_api_provider',
       default='blockstream')
    
    bitcoin_custom_api_base_url = fields.Char(
        string='Custom API Base URL',
        config_parameter='bitcoin.custom_api_base_url',
        help="Base URL for custom blockchain API"
    )
    
    # Transaction Import Settings
    bitcoin_max_addresses_per_import = fields.Integer(
        string='Max Addresses per Import',
        config_parameter='bitcoin.max_addresses_per_import',
        default=50,
        help="Limit number of addresses to check in one import operation"
    )
    
    bitcoin_import_delay = fields.Float(
        string='Delay Between Address Checks (seconds)',
        config_parameter='bitcoin.import_delay',
        default=0.5,
        help="Delay between API calls to avoid rate limiting"
    )
    
    # Cache Settings
    bitcoin_cache_duration = fields.Integer(
        string='Blockchain Info Cache (minutes)',
        config_parameter='bitcoin.cache_duration',
        default=5,
        help="How long to cache current block height and network info"
    )
    
    # Connection Status (computed, not stored)
    bitcoin_connection_status = fields.Selection([
        ('untested', 'Not Tested'),
        ('connected', 'Connected'),
        ('failed', 'Connection Failed')
    ], string='Connection Status', compute='_compute_bitcoin_connection_status')
    
    bitcoin_status_message = fields.Text(
        string='Status Message',
        compute='_compute_bitcoin_connection_status'
    )

    @api.depends('bitcoin_use_local_node', 'bitcoin_node_rpc_host', 'bitcoin_node_rpc_port')
    def _compute_bitcoin_connection_status(self):
        """Compute connection status based on current settings"""
        for record in self:
            # This is just for display - actual testing is done via action
            record.bitcoin_connection_status = 'untested'
            record.bitcoin_status_message = 'Click "Test Bitcoin Connection" to verify settings'

    def action_test_bitcoin_connection(self):
        """Test Bitcoin connection and update status"""
        self.ensure_one()
        
        error_message = None
        
        try:
            if self.bitcoin_use_local_node:
                success, error_message = self._test_bitcoin_node_connection()
            else:
                success, error_message = self._test_bitcoin_api_connection()
                
            if success:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '✅ Bitcoin Connection Successful',
                        'message': 'Successfully connected to Bitcoin service',
                        'type': 'success',
                        'sticky': False
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '❌ Bitcoin Connection Failed',
                        'message': error_message or 'Failed to connect to Bitcoin service. Check your settings.',
                        'type': 'danger',
                        'sticky': True  # Keep error messages visible longer
                    }
                }
                
        except Exception as e:
            error_details = str(e)
            _logger.error(f"Bitcoin connection test exception: {error_details}", exc_info=True)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '💥 Bitcoin Connection Error',
                    'message': f'Connection test failed with exception:\n\n{error_details}',
                    'type': 'danger',
                    'sticky': True  # Keep error messages visible longer
                }
            }

    def _test_bitcoin_node_connection(self):
        """Test connection to local Bitcoin node"""
        try:
            # Validate required fields first
            if not self.bitcoin_node_rpc_host:
                return False, "Bitcoin node host is required"
                
            if not self.bitcoin_node_rpc_user or not self.bitcoin_node_rpc_password:
                return False, "Bitcoin node RPC username and password are required"
            
            _logger.info(f"Testing Bitcoin node connection to {self.bitcoin_node_rpc_host}:{self.bitcoin_node_rpc_port}")
            
            # Create a temporary Bitcoin connector to test
            connector_vals = {
                'name': 'Settings Test Connection',
                'rpc_host': self.bitcoin_node_rpc_host,
                'rpc_port': self.bitcoin_node_rpc_port,
                'rpc_user': self.bitcoin_node_rpc_user,
                'rpc_password': self.bitcoin_node_rpc_password,
                'use_ssl': self.bitcoin_node_use_ssl,
                'network': self.bitcoin_network,
                'is_active': False  # Don't make it active
            }
            
            test_connector = self.env['bitcoin.connector'].create(connector_vals)
            
            try:
                # Test the connection
                blockchain_info = test_connector._make_rpc_call('getblockchaininfo')
                network_info = test_connector._make_rpc_call('getnetworkinfo')
                
                success_message = (
                    f"✅ Connected to {blockchain_info.get('chain', 'unknown')} network\n"
                    f"📊 Block height: {blockchain_info.get('blocks', 0)}\n"
                    f"🔗 Node version: {network_info.get('subversion', 'unknown')}\n"
                    f"👥 Peer connections: {network_info.get('connections', 0)}"
                )
                
                _logger.info(f"Bitcoin node connection successful: {success_message}")
                return True, success_message
                
            finally:
                # Clean up test connector
                test_connector.unlink()
                
        except Exception as e:
            error_str = str(e)
            
            # Provide specific error messages
            if "Connection refused" in error_str:
                error_message = f"❌ Connection refused\n\nBitcoin Core is not running or not accessible at {self.bitcoin_node_rpc_host}:{self.bitcoin_node_rpc_port}\n\n🔧 Troubleshooting:\n• Check if Bitcoin Core is running\n• Verify host and port settings\n• Check firewall settings"
            elif "authentication failed" in error_str.lower() or "401" in error_str:
                error_message = f"❌ Authentication failed\n\nRPC credentials are incorrect\n\n🔧 Troubleshooting:\n• Check RPC username and password\n• Verify bitcoin.conf settings:\n  rpcuser={self.bitcoin_node_rpc_user}\n  rpcpassword=your_password"
            elif "timeout" in error_str.lower():
                error_message = f"❌ Connection timeout\n\nBitcoin Core is not responding\n\n🔧 Troubleshooting:\n• Bitcoin Core may be starting up\n• Check if node is syncing\n• Verify network connectivity"
            elif "Name or service not known" in error_str:
                error_message = f"❌ DNS resolution failed\n\nCannot resolve hostname '{self.bitcoin_node_rpc_host}'\n\n🔧 Troubleshooting:\n• Check hostname spelling\n• Use IP address instead\n• Check DNS settings"
            else:
                error_message = f"❌ Connection failed\n\nUnexpected error: {error_str}\n\n🔧 Check Bitcoin Core logs and configuration"
            
            _logger.warning(f"Bitcoin node connection test failed: {error_message}")
            return False, error_message

    def _test_bitcoin_api_connection(self):
        """Test connection to external blockchain API"""
        try:
            import requests
            
            # Build test URL based on provider
            if self.bitcoin_external_api_provider == 'blockstream':
                if self.bitcoin_network == 'mainnet':
                    test_url = 'https://blockstream.info/api/blocks/tip/height'
                    provider_name = 'Blockstream (Mainnet)'
                else:
                    test_url = 'https://blockstream.info/testnet/api/blocks/tip/height'
                    provider_name = 'Blockstream (Testnet)'
            elif self.bitcoin_external_api_provider == 'mempool':
                if self.bitcoin_network == 'mainnet':
                    test_url = 'https://mempool.space/api/blocks/tip/height'
                    provider_name = 'Mempool.space (Mainnet)'
                else:
                    test_url = 'https://mempool.space/testnet/api/blocks/tip/height'
                    provider_name = 'Mempool.space (Testnet)'
            elif self.bitcoin_external_api_provider == 'custom' and self.bitcoin_custom_api_base_url:
                test_url = f"{self.bitcoin_custom_api_base_url}/blocks/tip/height"
                provider_name = f'Custom API ({self.bitcoin_custom_api_base_url})'
            else:
                return False, "❌ Invalid API provider configuration\n\nPlease select a valid API provider or configure custom URL"
            
            _logger.info(f"Testing {provider_name} API connection: {test_url}")
            
            response = requests.get(test_url, timeout=10)
            
            if response.status_code == 200:
                block_height = response.text.strip()
                success_message = (
                    f"✅ Connected to {provider_name}\n"
                    f"📊 Current block height: {block_height}\n"
                    f"🌐 Network: {self.bitcoin_network}\n"
                    f"🔗 URL: {test_url}"
                )
                _logger.info(f"Bitcoin API connection successful: {success_message}")
                return True, success_message
            else:
                error_message = (
                    f"❌ API request failed\n\n"
                    f"HTTP {response.status_code}: {response.reason}\n"
                    f"Provider: {provider_name}\n"
                    f"URL: {test_url}\n\n"
                    f"🔧 Troubleshooting:\n"
                    f"• Check network connectivity\n"
                    f"• Try a different API provider\n"
                    f"• Verify URL is correct"
                )
                _logger.warning(f"Bitcoin API connection failed: {error_message}")
                return False, error_message
                
        except Exception as e:
            error_str = str(e)
            provider_name = getattr(self, 'bitcoin_external_api_provider', 'Unknown')
            
            if "timeout" in error_str.lower():
                error_message = f"❌ Connection timeout\n\n{provider_name} API is not responding\n\n🔧 Troubleshooting:\n• Check internet connection\n• Try again later\n• Switch to a different API provider"
            elif "Name or service not known" in error_str:
                error_message = f"❌ DNS resolution failed\n\nCannot resolve API hostname\n\n🔧 Troubleshooting:\n• Check internet connection\n• Check DNS settings\n• Try a different API provider"
            else:
                error_message = f"❌ API connection failed\n\nUnexpected error: {error_str}\n\n🔧 Try a different API provider or check network settings"
            
            _logger.warning(f"Bitcoin API connection test failed: {error_message}")
            return False, error_message

    @api.model
    def get_bitcoin_settings_values(self):
        """Get current Bitcoin settings as a dictionary"""
        return {
            'use_local_node': self.env['ir.config_parameter'].sudo().get_param('bitcoin.use_local_node', True),
            'node_rpc_host': self.env['ir.config_parameter'].sudo().get_param('bitcoin.node_rpc_host', 'localhost'),
            'node_rpc_port': int(self.env['ir.config_parameter'].sudo().get_param('bitcoin.node_rpc_port', 8332)),
            'node_rpc_user': self.env['ir.config_parameter'].sudo().get_param('bitcoin.node_rpc_user', ''),
            'node_rpc_password': self.env['ir.config_parameter'].sudo().get_param('bitcoin.node_rpc_password', ''),
            'node_use_ssl': self.env['ir.config_parameter'].sudo().get_param('bitcoin.node_use_ssl', False),
            'network': self.env['ir.config_parameter'].sudo().get_param('bitcoin.network', 'mainnet'),
            'external_api_provider': self.env['ir.config_parameter'].sudo().get_param('bitcoin.external_api_provider', 'blockstream'),
            'custom_api_base_url': self.env['ir.config_parameter'].sudo().get_param('bitcoin.custom_api_base_url', ''),
            'max_addresses_per_import': int(self.env['ir.config_parameter'].sudo().get_param('bitcoin.max_addresses_per_import', 50)),
            'import_delay': float(self.env['ir.config_parameter'].sudo().get_param('bitcoin.import_delay', 0.5)),
            'cache_duration': int(self.env['ir.config_parameter'].sudo().get_param('bitcoin.cache_duration', 5))
        }