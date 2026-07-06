# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging
import os
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)


class BitcoinNodeConfig(models.Model):
    _name = 'bitcoin.node.config'
    _description = 'Bitcoin Core Node Configuration'
    _order = 'sequence, name'
    _rec_name = 'display_name'

    name = fields.Char(string='Configuration Name', required=True)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)
    
    # Priority and Status
    sequence = fields.Integer(string='Priority', default=10, 
                             help="Lower numbers = higher priority. Used for failover ordering.")
    is_active = fields.Boolean(string='Active', default=True,
                              help="Only active nodes are used for connections")
    
    # Connection Settings
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
    
    # Health Monitoring
    connection_status = fields.Selection([
        ('unknown', 'Unknown'),
        ('connected', 'Connected'),
        ('error', 'Connection Error'),
        ('auth_failed', 'Authentication Failed'),
        ('timeout', 'Timeout')
    ], string='Status', default='unknown', readonly=True)
    
    last_connected = fields.Datetime(string='Last Connected', readonly=True)
    last_check = fields.Datetime(string='Last Health Check', readonly=True)
    status_message = fields.Text(string='Status Message', readonly=True)
    
    # Node Information (cached)
    node_version = fields.Char(string='Node Version', readonly=True)
    current_block_height = fields.Integer(string='Current Block Height', readonly=True)
    best_block_hash = fields.Char(string='Best Block Hash', readonly=True)
    chain = fields.Char(string='Chain', readonly=True)
    peer_count = fields.Integer(string='Peer Count', readonly=True)
    
    # Performance Settings
    timeout_seconds = fields.Integer(string='Timeout (seconds)', default=30,
                                   help="Connection timeout for this node")
    max_retries = fields.Integer(string='Max Retries', default=3,
                               help="Maximum retry attempts before marking as failed")
    cache_duration_minutes = fields.Integer(string='Cache Duration (minutes)', default=5,
                                          help="How long to cache blockchain info")
    
    # Environment Variable Support
    use_env_variables = fields.Boolean(string='Use Environment Variables', default=False,
                                     help="Override connection settings with environment variables")
    env_prefix = fields.Char(string='Environment Variable Prefix', default='BITCOIN_RPC',
                           help="Prefix for environment variables (e.g., BITCOIN_RPC_HOST)")

    @api.depends('name', 'rpc_host', 'rpc_port', 'network', 'connection_status')
    def _compute_display_name(self):
        """Compute display name with status indicator"""
        for record in self:
            status_icon = {
                'connected': '🟢',
                'error': '🔴', 
                'auth_failed': '🟡',
                'timeout': '🟠',
                'unknown': '⚪'
            }.get(record.connection_status, '⚪')
            
            record.display_name = f"{status_icon} {record.name} ({record.rpc_host}:{record.rpc_port})"

    @api.constrains('sequence')
    def _check_sequence(self):
        """Ensure sequence is positive"""
        for record in self:
            if record.sequence < 1:
                raise ValidationError("Priority must be a positive number (1 = highest priority)")

    @api.model
    def get_active_nodes(self, network=None):
        """Get active nodes ordered by priority"""
        domain = [('is_active', '=', True)]
        if network:
            domain.append(('network', '=', network))
        
        return self.search(domain, order='sequence, name')

    @api.model
    def get_best_node(self, network=None):
        """Get the best available node using failover logic"""
        nodes = self.get_active_nodes(network)
        
        if not nodes:
            raise UserError(f"No active Bitcoin nodes configured for network: {network or 'any'}")
        
        # Try nodes in priority order
        for node in nodes:
            try:
                if node.test_connection_quick():
                    _logger.info(f"Using Bitcoin node: {node.display_name}")
                    return node
            except Exception as e:
                _logger.warning(f"Bitcoin node {node.name} failed quick test: {str(e)}")
                continue
        
        # If no nodes pass quick test, return highest priority node and let caller handle errors
        best_node = nodes[0]
        _logger.warning(f"No nodes passed quick test, using highest priority: {best_node.display_name}")
        return best_node

    def test_connection_quick(self):
        """Quick connection test for failover decisions"""
        try:
            connector = self.get_connector()
            # Quick test - just get network info
            connector._make_rpc_call('getnetworkinfo')
            return True
        except Exception:
            return False

    def test_connection(self):
        """Full connection test with status update"""
        self.ensure_one()
        
        try:
            _logger.info(f"Testing Bitcoin node connection: {self.name}")
            
            connector = self.get_connector()
            
            # Test connection with comprehensive calls
            blockchain_info = connector._make_rpc_call('getblockchaininfo')
            network_info = connector._make_rpc_call('getnetworkinfo')
            
            # Update node information
            self.write({
                'connection_status': 'connected',
                'last_connected': fields.Datetime.now(),
                'last_check': fields.Datetime.now(),
                'node_version': network_info.get('subversion', 'Unknown'),
                'current_block_height': blockchain_info.get('blocks', 0),
                'best_block_hash': blockchain_info.get('bestblockhash', ''),
                'chain': blockchain_info.get('chain', 'unknown'),
                'peer_count': network_info.get('connections', 0),
                'status_message': f"Connected successfully. Chain: {blockchain_info.get('chain')}, Height: {blockchain_info.get('blocks', 0)}"
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': '✅ Connection Successful',
                    'message': f"Connected to {self.chain} at block {self.current_block_height}",
                    'type': 'success'
                }
            }
            
        except Exception as e:
            error_message = self._parse_connection_error(str(e))
            
            # Determine status based on error type
            if "authentication failed" in str(e).lower() or "401" in str(e):
                status = 'auth_failed'
            elif "timeout" in str(e).lower():
                status = 'timeout'
            else:
                status = 'error'
            
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

    def _parse_connection_error(self, error_str):
        """Parse error string into user-friendly message"""
        if "Connection refused" in error_str:
            return f"Connection refused - Bitcoin Core not accessible at {self.rpc_host}:{self.rpc_port}"
        elif "authentication failed" in error_str.lower() or "401" in error_str:
            return "Authentication failed - check RPC username/password"
        elif "timeout" in error_str.lower():
            return "Connection timeout - Bitcoin Core not responding"
        elif "Name or service not known" in error_str:
            return f"DNS error - cannot resolve hostname '{self.rpc_host}'"
        else:
            return f"Connection failed: {error_str}"

    def get_connector(self):
        """Get Bitcoin connector for this node configuration"""
        self.ensure_one()
        
        # Get connection settings (with environment variable override)
        host, port, user, password, ssl = self._get_connection_settings()
        
        # Look for existing connector
        connector = self.env['bitcoin.connector'].search([
            ('rpc_host', '=', host),
            ('rpc_port', '=', port),
            ('rpc_user', '=', user),
            ('network', '=', self.network)
        ], limit=1)
        
        if connector:
            return connector
        
        # Create new connector
        connector = self.env['bitcoin.connector'].create({
            'name': f'{self.name} - Connector',
            'rpc_host': host,
            'rpc_port': port,
            'rpc_user': user,
            'rpc_password': password,
            'use_ssl': ssl,
            'network': self.network,
            'is_active': True,
            'cache_duration_minutes': self.cache_duration_minutes
        })
        
        return connector

    def _get_connection_settings(self):
        """Get connection settings with environment variable support"""
        if self.use_env_variables and self.env_prefix:
            host = os.environ.get(f'{self.env_prefix}_HOST', self.rpc_host)
            port = int(os.environ.get(f'{self.env_prefix}_PORT', self.rpc_port))
            user = os.environ.get(f'{self.env_prefix}_USER', self.rpc_user)
            password = os.environ.get(f'{self.env_prefix}_PASSWORD', self.rpc_password)
            ssl = os.environ.get(f'{self.env_prefix}_SSL', 'false').lower() == 'true'
        else:
            host = self.rpc_host
            port = self.rpc_port
            user = self.rpc_user
            password = self.rpc_password
            ssl = self.use_ssl
            
        return host, port, user, password, ssl

    def action_refresh_status(self):
        """Refresh node status and information"""
        return self.test_connection()

    @api.model
    def health_check_all(self):
        """Run health check on all active nodes"""
        nodes = self.search([('is_active', '=', True)])
        
        results = {
            'total': len(nodes),
            'connected': 0,
            'failed': 0,
            'details': []
        }
        
        for node in nodes:
            try:
                if node.test_connection_quick():
                    results['connected'] += 1
                    status = 'connected'
                else:
                    results['failed'] += 1
                    status = 'failed'
            except Exception as e:
                results['failed'] += 1
                status = 'error'
                node.write({
                    'connection_status': 'error',
                    'last_check': fields.Datetime.now(),
                    'status_message': str(e)
                })
            
            results['details'].append({
                'name': node.name,
                'status': status,
                'priority': node.sequence
            })
        
        return results

    @api.model
    def create_default_node(self, network='mainnet'):
        """Create default Bitcoin node configuration"""
        existing = self.search([('network', '=', network)], limit=1)
        if existing:
            return existing
        
        # Try to get settings from environment
        host = os.environ.get('BITCOIN_RPC_HOST', 'localhost')
        port = int(os.environ.get('BITCOIN_RPC_PORT', '8332'))
        user = os.environ.get('BITCOIN_RPC_USER', '')
        password = os.environ.get('BITCOIN_RPC_PASSWORD', '')
        
        if not user or not password:
            raise UserError(
                "No Bitcoin node configured. Please create a node configuration or set environment variables:\n"
                "BITCOIN_RPC_HOST, BITCOIN_RPC_PORT, BITCOIN_RPC_USER, BITCOIN_RPC_PASSWORD"
            )
        
        node = self.create({
            'name': f'Default Bitcoin Node ({network.title()})',
            'rpc_host': host,
            'rpc_port': port,
            'rpc_user': user,
            'rpc_password': password,
            'network': network,
            'sequence': 1,
            'is_active': True
        })
        
        _logger.info(f"Created default Bitcoin node: {node.name}")
        return node