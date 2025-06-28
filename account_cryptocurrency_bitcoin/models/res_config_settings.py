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
        
        try:
            if self.bitcoin_use_local_node:
                success = self._test_bitcoin_node_connection()
            else:
                success = self._test_bitcoin_api_connection()
                
            if success:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Bitcoin Connection Successful',
                        'message': 'Successfully connected to Bitcoin service',
                        'type': 'success'
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Bitcoin Connection Failed',
                        'message': 'Failed to connect to Bitcoin service. Check your settings.',
                        'type': 'danger'
                    }
                }
                
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Bitcoin Connection Error',
                    'message': f'Connection test failed: {str(e)}',
                    'type': 'danger'
                }
            }

    def _test_bitcoin_node_connection(self):
        """Test connection to local Bitcoin node"""
        try:
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
                return True
                
            finally:
                # Clean up test connector
                test_connector.unlink()
                
        except Exception as e:
            _logger.warning(f"Bitcoin node connection test failed: {str(e)}")
            return False

    def _test_bitcoin_api_connection(self):
        """Test connection to external blockchain API"""
        try:
            import requests
            
            # Build test URL based on provider
            if self.bitcoin_external_api_provider == 'blockstream':
                if self.bitcoin_network == 'mainnet':
                    test_url = 'https://blockstream.info/api/blocks/tip/height'
                else:
                    test_url = 'https://blockstream.info/testnet/api/blocks/tip/height'
            elif self.bitcoin_external_api_provider == 'mempool':
                if self.bitcoin_network == 'mainnet':
                    test_url = 'https://mempool.space/api/blocks/tip/height'
                else:
                    test_url = 'https://mempool.space/testnet/api/blocks/tip/height'
            elif self.bitcoin_external_api_provider == 'custom' and self.bitcoin_custom_api_base_url:
                test_url = f"{self.bitcoin_custom_api_base_url}/blocks/tip/height"
            else:
                raise ValidationError("Invalid API provider configuration")
            
            response = requests.get(test_url, timeout=10)
            return response.status_code == 200
                
        except Exception as e:
            _logger.warning(f"Bitcoin API connection test failed: {str(e)}")
            return False

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