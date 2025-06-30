# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging
import os

_logger = logging.getLogger(__name__)


class ElectrumServerConfig(models.Model):
    _name = 'electrum.server.config'
    _description = 'Electrum Server Configuration'
    _order = 'sequence, name'
    _rec_name = 'display_name'

    name = fields.Char(string='Configuration Name', required=True)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    
    # Priority and Status
    sequence = fields.Integer(string='Priority', default=10,
                             help="Lower numbers = higher priority. Used for failover ordering.")
    is_active = fields.Boolean(string='Active', default=True,
                              help="Only active servers are used for connections")
    
    # Connection Settings
    host = fields.Char(string='Server Host', required=True, default='electrum.blockstream.info')
    port = fields.Integer(string='Server Port', required=True, default=50002)
    use_ssl = fields.Boolean(string='Use SSL', default=True)
    
    # Network
    network = fields.Selection([
        ('mainnet', 'Bitcoin Mainnet'),
        ('testnet', 'Bitcoin Testnet'),
        ('regtest', 'Regtest'),
        ('signet', 'Signet')
    ], string='Network', required=True, default='mainnet')
    
    # Health Monitoring
    connection_status = fields.Selection([
        ('unknown', 'Unknown'),
        ('connected', 'Connected'),
        ('error', 'Connection Error'),
        ('timeout', 'Timeout'),
        ('ssl_error', 'SSL Error')
    ], string='Status', default='unknown', readonly=True)
    
    last_connected = fields.Datetime(string='Last Connected', readonly=True)
    last_check = fields.Datetime(string='Last Health Check', readonly=True)
    status_message = fields.Text(string='Status Message', readonly=True)
    
    # Server Information (cached)
    server_version = fields.Char(string='Server Version', readonly=True)
    protocol_version = fields.Char(string='Protocol Version', readonly=True)
    current_block_height = fields.Integer(string='Current Block Height', readonly=True)
    
    # Performance Settings
    timeout_seconds = fields.Integer(string='Timeout (seconds)', default=30,
                                   help="Connection timeout for this server")
    max_retries = fields.Integer(string='Max Retries', default=3,
                               help="Maximum retry attempts before marking as failed")
    
    # Server Type
    server_type = fields.Selection([
        ('public', 'Public Server'),
        ('private', 'Private Server'),
        ('tor', 'Tor Hidden Service')
    ], string='Server Type', default='public',
       help="Type of Electrum server for categorization")
    
    # Environment Variable Support
    use_env_variables = fields.Boolean(string='Use Environment Variables', default=False,
                                     help="Override connection settings with environment variables")
    env_prefix = fields.Char(string='Environment Variable Prefix', default='ELECTRUM',
                           help="Prefix for environment variables (e.g., ELECTRUM_HOST)")
    
    # Rate Limiting
    rate_limit_requests_per_second = fields.Float(string='Rate Limit (req/sec)', default=10.0,
                                                 help="Maximum requests per second to this server")

    @api.depends('name', 'host', 'port', 'network', 'connection_status')
    def _compute_display_name(self):
        """Compute display name with status indicator"""
        for record in self:
            status_icon = {
                'connected': '🟢',
                'error': '🔴',
                'timeout': '🟠',
                'ssl_error': '🟡',
                'unknown': '⚪'
            }.get(record.connection_status, '⚪')
            
            ssl_indicator = '🔒' if record.use_ssl else '🔓'
            
            record.display_name = f"{status_icon} {record.name} ({record.host}:{record.port}) {ssl_indicator}"

    @api.constrains('sequence')
    def _check_sequence(self):
        """Ensure sequence is positive"""
        for record in self:
            if record.sequence < 1:
                raise ValidationError("Priority must be a positive number (1 = highest priority)")

    @api.constrains('port')
    def _check_port(self):
        """Validate port number"""
        for record in self:
            if not (1 <= record.port <= 65535):
                raise ValidationError("Port must be between 1 and 65535")

    @api.model
    def create_default_servers(self, network='mainnet'):
        """Create default Electrum server configurations"""
        _logger.info(f"Creating default Electrum servers for {network}")
        
        # Define default servers for different networks
        default_servers = {
            'mainnet': [
                {'name': 'Blockstream Electrum', 'host': 'electrum.blockstream.info', 'port': 50002, 'use_ssl': True, 'sequence': 10},
                {'name': 'Blockstream Electrum (Alt)', 'host': 'electrum.blockstream.info', 'port': 50001, 'use_ssl': False, 'sequence': 20},
                {'name': 'ElectrumX Public', 'host': 'ecdsa.net', 'port': 50002, 'use_ssl': True, 'sequence': 30},
                {'name': 'ElectrumX Public (Alt)', 'host': 'ecdsa.net', 'port': 50001, 'use_ssl': False, 'sequence': 40},
            ],
            'testnet': [
                {'name': 'Blockstream Testnet', 'host': 'blockstream.info', 'port': 60002, 'use_ssl': True, 'sequence': 10},
                {'name': 'ElectrumX Testnet', 'host': 'testnet.qtornado.com', 'port': 51002, 'use_ssl': True, 'sequence': 20},
            ]
        }
        
        servers_data = default_servers.get(network, default_servers['mainnet'])
        created_count = 0
        
        for server_data in servers_data:
            # Check if server already exists
            existing = self.search([
                ('host', '=', server_data['host']),
                ('port', '=', server_data['port']),
                ('network', '=', network)
            ])
            
            if not existing:
                server_vals = {
                    'name': server_data['name'],
                    'host': server_data['host'],
                    'port': server_data['port'],
                    'use_ssl': server_data['use_ssl'],
                    'sequence': server_data['sequence'],
                    'network': network,
                    'is_active': True
                }
                
                new_server = self.create(server_vals)
                created_count += 1
                _logger.info(f"Created default Electrum server: {new_server.display_name}")
        
        return created_count

    @api.model
    def get_active_servers(self, network=None):
        """Get active servers ordered by priority"""
        domain = [('is_active', '=', True)]
        if network:
            domain.append(('network', '=', network))
        
        return self.search(domain, order='sequence, name')

    @api.model
    def get_best_server(self, network=None):
        """Get the best available server using failover logic"""
        servers = self.get_active_servers(network)
        
        if not servers:
            raise UserError(f"No active Electrum servers configured for network: {network or 'any'}")
        
        # Try servers in priority order
        for server in servers:
            try:
                if server.test_connection_quick():
                    _logger.info(f"Using Electrum server: {server.display_name}")
                    return server
            except Exception as e:
                _logger.warning(f"Electrum server {server.name} failed quick test: {str(e)}")
                continue
        
        # If no servers pass quick test, return highest priority server and let caller handle errors
        best_server = servers[0]
        _logger.warning(f"No servers passed quick test, using highest priority: {best_server.display_name}")
        return best_server

    def test_connection_quick(self):
        """Quick connection test for failover decisions"""
        try:
            # Get connection settings
            host, port, use_ssl = self._get_connection_settings()
            
            # Use Electrum client for quick test
            electrum_client = self.env['electrum.client']
            result = electrum_client.test_connection(host, port, use_ssl)
            
            return result['success']
        except Exception:
            return False

    def test_connection(self):
        """Full connection test with status update"""
        self.ensure_one()
        
        try:
            _logger.info(f"Testing Electrum server connection: {self.name}")
            
            # Get connection settings
            host, port, use_ssl = self._get_connection_settings()
            
            # Test connection
            electrum_client = self.env['electrum.client']
            result = electrum_client.test_connection(host, port, use_ssl)
            
            if result['success']:
                # Try to get additional server info
                try:
                    # Get block height for validation
                    block_height = electrum_client.get_block_height(host, port, use_ssl)
                    
                    self.write({
                        'connection_status': 'connected',
                        'last_connected': fields.Datetime.now(),
                        'last_check': fields.Datetime.now(),
                        'current_block_height': block_height,
                        'status_message': f"Connected successfully. Block height: {block_height}"
                    })
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': '✅ Connection Successful',
                            'message': f"Connected to {self.host}:{self.port}, Block height: {block_height}",
                            'type': 'success'
                        }
                    }
                    
                except Exception as e:
                    # Connection worked but couldn't get additional info
                    self.write({
                        'connection_status': 'connected',
                        'last_connected': fields.Datetime.now(),
                        'last_check': fields.Datetime.now(),
                        'status_message': "Connected successfully (limited server info)"
                    })
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': '✅ Connection Successful',
                            'message': f"Connected to {self.host}:{self.port}",
                            'type': 'success'
                        }
                    }
            else:
                # Connection failed
                error_message = result.get('message', 'Unknown error')
                status = self._determine_error_status(result.get('error', ''))
                
                self.write({
                    'connection_status': status,
                    'last_check': fields.Datetime.now(),
                    'status_message': error_message
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '❌ Connection Failed',
                        'message': error_message,
                        'type': 'danger',
                        'sticky': True
                    }
                }
                
        except Exception as e:
            error_message = self._parse_connection_error(str(e))
            status = self._determine_error_status(str(e))
            
            self.write({
                'connection_status': status,
                'last_check': fields.Datetime.now(),
                'status_message': error_message
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '💥 Connection Error',
                    'message': error_message,
                    'type': 'danger',
                    'sticky': True
                }
            }

    def _determine_error_status(self, error_str):
        """Determine status based on error type"""
        if "timeout" in error_str.lower():
            return 'timeout'
        elif "ssl" in error_str.lower() or "certificate" in error_str.lower():
            return 'ssl_error'
        else:
            return 'error'

    def _parse_connection_error(self, error_str):
        """Parse error string into user-friendly message"""
        if "Connection refused" in error_str:
            return f"Connection refused - Electrum server not accessible at {self.host}:{self.port}"
        elif "timeout" in error_str.lower():
            return "Connection timeout - Electrum server not responding"
        elif "Name or service not known" in error_str:
            return f"DNS error - cannot resolve hostname '{self.host}'"
        elif "SSL" in error_str or "certificate" in error_str.lower():
            return "SSL/Certificate error - try disabling SSL or check server certificate"
        else:
            return f"Connection failed: {error_str}"

    def _get_connection_settings(self):
        """Get connection settings with environment variable support"""
        if self.use_env_variables and self.env_prefix:
            host = os.environ.get(f'{self.env_prefix}_HOST', self.host)
            port = int(os.environ.get(f'{self.env_prefix}_PORT', self.port))
            use_ssl = os.environ.get(f'{self.env_prefix}_USE_SSL', 'true' if self.use_ssl else 'false').lower() == 'true'
        else:
            host = self.host
            port = self.port
            use_ssl = self.use_ssl
            
        return host, port, use_ssl

    def action_refresh_status(self):
        """Refresh server status and information"""
        return self.test_connection()

    @api.model
    def health_check_all(self):
        """Run health check on all active servers"""
        servers = self.search([('is_active', '=', True)])
        
        results = {
            'total': len(servers),
            'connected': 0,
            'failed': 0,
            'details': []
        }
        
        for server in servers:
            try:
                if server.test_connection_quick():
                    results['connected'] += 1
                    status = 'connected'
                else:
                    results['failed'] += 1
                    status = 'failed'
            except Exception as e:
                results['failed'] += 1
                status = 'error'
                server.write({
                    'connection_status': 'error',
                    'last_check': fields.Datetime.now(),
                    'status_message': str(e)
                })
            
            results['details'].append({
                'name': server.name,
                'status': status,
                'priority': server.sequence,
                'server_type': server.server_type
            })
        
        return results

    @api.model
    def create_default_servers(self, network='mainnet'):
        """Create default Electrum server configurations"""
        existing = self.search([('network', '=', network)], limit=1)
        if existing:
            return existing
        
        # Default public servers
        default_servers = {
            'mainnet': [
                {'name': 'Blockstream Electrum', 'host': 'electrum.blockstream.info', 'port': 50002, 'ssl': True, 'seq': 1},
                {'name': 'Electrum.org', 'host': 'electrum.villocq.com', 'port': 50002, 'ssl': True, 'seq': 2},
                {'name': 'Bitcoin.org Electrum', 'host': 'electrum3.bluewallet.io', 'port': 50002, 'ssl': True, 'seq': 3},
            ],
            'testnet': [
                {'name': 'Blockstream Testnet', 'host': 'electrum.blockstream.info', 'port': 60002, 'ssl': True, 'seq': 1},
            ]
        }
        
        servers_to_create = default_servers.get(network, [])
        created_servers = []
        
        for server_config in servers_to_create:
            # Check environment variables for override
            env_host = os.environ.get('ELECTRUM_HOST')
            env_port = os.environ.get('ELECTRUM_PORT')
            
            server = self.create({
                'name': server_config['name'],
                'host': env_host or server_config['host'],
                'port': int(env_port) if env_port else server_config['port'],
                'use_ssl': server_config['ssl'],
                'network': network,
                'sequence': server_config['seq'],
                'server_type': 'public',
                'is_active': True
            })
            created_servers.append(server)
            
        if created_servers:
            _logger.info(f"Created {len(created_servers)} default Electrum servers for {network}")
            return created_servers[0]  # Return highest priority server
        
        raise UserError(f"No default Electrum servers available for network: {network}")

    @api.model
    def get_failover_chain(self, network=None, max_servers=3):
        """Get a chain of servers for failover (limited count for performance)"""
        servers = self.get_active_servers(network)
        return servers[:max_servers] if max_servers else servers