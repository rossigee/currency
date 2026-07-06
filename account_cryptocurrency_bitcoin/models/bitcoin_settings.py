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
    
    # Bitcoin Network
    network = fields.Selection([
        ('mainnet', 'Bitcoin Mainnet'),
        ('testnet', 'Bitcoin Testnet'),
        ('regtest', 'Regtest'),
        ('signet', 'Signet')
    ], string='Bitcoin Network', default='mainnet', required=True)
    
    # Bitcoin Core Node Settings (for broadcasting, fee estimation, etc.)
    use_bitcoin_core = fields.Boolean(string='Enable Bitcoin Core Integration', default=True,
                                     help="Enable Bitcoin Core node for transaction broadcasting and advanced features")
    bitcoin_core_rpc_host = fields.Char(string='Bitcoin Core Host', default='localhost')
    bitcoin_core_rpc_port = fields.Integer(string='Bitcoin Core Port', default=8332)
    bitcoin_core_rpc_user = fields.Char(string='Bitcoin Core RPC Username')
    bitcoin_core_rpc_password = fields.Char(string='Bitcoin Core RPC Password')
    bitcoin_core_use_ssl = fields.Boolean(string='Bitcoin Core Use SSL', default=False)
    bitcoin_core_status = fields.Selection([
        ('untested', 'Not Tested'),
        ('connected', 'Connected'),
        ('failed', 'Connection Failed')
    ], string='Bitcoin Core Status', default='untested', readonly=True)
    bitcoin_core_status_message = fields.Text(string='Bitcoin Core Status', readonly=True)
    
    # Electrum Server Settings (for transaction history)
    use_electrum = fields.Boolean(string='Enable Electrum Integration', default=True,
                                 help="Enable Electrum server for transaction history and address monitoring")
    electrum_host = fields.Char(string='Electrum Host', default='electrum.blockstream.info',
                               help="Electrum server hostname")
    electrum_port = fields.Integer(string='Electrum Port', default=50002,
                                  help="Electrum server port")
    electrum_use_ssl = fields.Boolean(string='Electrum Use SSL', default=True,
                                     help="Use SSL for Electrum connection")
    electrum_status = fields.Selection([
        ('untested', 'Not Tested'),
        ('connected', 'Connected'),
        ('failed', 'Connection Failed')
    ], string='Electrum Status', default='untested', readonly=True)
    electrum_status_message = fields.Text(string='Electrum Status', readonly=True)
    
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
    
    # General Status
    last_test_date = fields.Datetime(string='Last Connection Test', readonly=True)

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

    def action_test_connections(self):
        """Test both Bitcoin Core and Electrum connections"""
        self.ensure_one()
        
        results = []
        detailed_errors = []
        
        # Test Bitcoin Core connection
        if self.use_bitcoin_core:
            try:
                _logger.info("Testing Bitcoin Core connection...")
                bitcoin_core_success = self._test_bitcoin_core_connection()
                if bitcoin_core_success:
                    results.append("✅ Bitcoin Core: Connected")
                    _logger.info(f"Bitcoin Core connected: {self.bitcoin_core_status_message}")
                else:
                    error_msg = self.bitcoin_core_status_message or "Unknown error"
                    results.append(f"❌ Bitcoin Core: Failed")
                    detailed_errors.append(f"Bitcoin Core Error: {error_msg}")
                    _logger.warning(f"Bitcoin Core connection failed: {error_msg}")
            except Exception as e:
                error_msg = str(e)
                results.append(f"❌ Bitcoin Core: Exception")
                detailed_errors.append(f"Bitcoin Core Exception: {error_msg}")
                _logger.error(f"Bitcoin Core connection exception: {error_msg}", exc_info=True)
        else:
            results.append("⚪ Bitcoin Core: Disabled")
            
        # Test Electrum connection
        if self.use_electrum:
            try:
                _logger.info("Testing Electrum connection...")
                electrum_success = self._test_electrum_connection()
                if electrum_success:
                    results.append("✅ Electrum: Connected")
                    _logger.info(f"Electrum connected: {self.electrum_status_message}")
                else:
                    error_msg = self.electrum_status_message or "Unknown error"
                    results.append(f"❌ Electrum: Failed")
                    detailed_errors.append(f"Electrum Error: {error_msg}")
                    _logger.warning(f"Electrum connection failed: {error_msg}")
            except Exception as e:
                error_msg = str(e)
                results.append(f"❌ Electrum: Exception")
                detailed_errors.append(f"Electrum Exception: {error_msg}")
                _logger.error(f"Electrum connection exception: {error_msg}", exc_info=True)
        else:
            results.append("⚪ Electrum: Disabled")
            
        # Update last test date
        self.last_test_date = fields.Datetime.now()
        
        # Prepare notification message
        message_parts = results.copy()
        if detailed_errors:
            message_parts.append("")  # Empty line
            message_parts.append("Detailed Errors:")
            message_parts.extend(detailed_errors)
        
        message = "\n".join(message_parts)
        success_count = len([r for r in results if r.startswith("✅")])
        failure_count = len([r for r in results if r.startswith("❌")])
        
        # Determine notification type and title
        if success_count > 0 and failure_count == 0:
            notification_type = 'success'
            title = f'✅ All Connections Successful ({success_count} services)'
        elif success_count > 0 and failure_count > 0:
            notification_type = 'warning'
            title = f'⚠️ Partial Success ({success_count} connected, {failure_count} failed)'
        elif failure_count > 0:
            notification_type = 'danger'
            title = f'❌ Connection Failed ({failure_count} services failed)'
        else:
            notification_type = 'info'
            title = 'ℹ️ All Services Disabled'
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': notification_type,
                'sticky': True if failure_count > 0 else False  # Keep error messages visible longer
            }
        }

    def _test_bitcoin_core_connection(self):
        """Test connection to Bitcoin Core node"""
        try:
            # Validate required fields first
            if not self.bitcoin_core_rpc_host:
                self.bitcoin_core_status = 'failed'
                self.bitcoin_core_status_message = "Bitcoin Core host is required"
                return False
                
            if not self.bitcoin_core_rpc_user or not self.bitcoin_core_rpc_password:
                self.bitcoin_core_status = 'failed'
                self.bitcoin_core_status_message = "Bitcoin Core RPC username and password are required"
                return False
            
            # Create a temporary Bitcoin connector to test
            connector_vals = {
                'name': 'Test Connection',
                'rpc_host': self.bitcoin_core_rpc_host,
                'rpc_port': self.bitcoin_core_rpc_port,
                'rpc_user': self.bitcoin_core_rpc_user,
                'rpc_password': self.bitcoin_core_rpc_password,
                'use_ssl': self.bitcoin_core_use_ssl,
                'network': self.network,
                'is_active': False  # Don't make it active
            }
            
            _logger.info(f"Testing Bitcoin Core connection to {self.bitcoin_core_rpc_host}:{self.bitcoin_core_rpc_port}")
            test_connector = self.env['bitcoin.connector'].create(connector_vals)
            
            try:
                # Test the connection
                blockchain_info = test_connector._make_rpc_call('getblockchaininfo')
                network_info = test_connector._make_rpc_call('getnetworkinfo')
                
                self.bitcoin_core_status = 'connected'
                self.bitcoin_core_status_message = (
                    f"Connected to {blockchain_info.get('chain', 'unknown')} network, "
                    f"Block {blockchain_info.get('blocks', 0)}, "
                    f"{network_info.get('connections', 0)} peers"
                )
                
                return True
                
            finally:
                # Clean up test connector
                test_connector.unlink()
                
        except Exception as e:
            self.bitcoin_core_status = 'failed'
            
            # Provide more specific error messages
            error_str = str(e)
            if "Connection refused" in error_str:
                self.bitcoin_core_status_message = f"Connection refused - Bitcoin Core not running or not accessible at {self.bitcoin_core_rpc_host}:{self.bitcoin_core_rpc_port}"
            elif "authentication failed" in error_str.lower() or "401" in error_str:
                self.bitcoin_core_status_message = f"Authentication failed - check RPC username/password"
            elif "timeout" in error_str.lower():
                self.bitcoin_core_status_message = f"Connection timeout - Bitcoin Core not responding"
            elif "Name or service not known" in error_str:
                self.bitcoin_core_status_message = f"DNS error - cannot resolve hostname '{self.bitcoin_core_rpc_host}'"
            else:
                self.bitcoin_core_status_message = f"Connection failed: {error_str}"
                
            _logger.error(f"Bitcoin Core connection test failed: {self.bitcoin_core_status_message}")
            return False

    def _test_electrum_connection(self):
        """Test connection to Electrum server"""
        try:
            # Validate required fields first
            if not self.electrum_host:
                self.electrum_status = 'failed'
                self.electrum_status_message = "Electrum host is required"
                return False
            
            if not self.electrum_port:
                self.electrum_status = 'failed'
                self.electrum_status_message = "Electrum port is required"
                return False
            
            _logger.info(f"Testing Electrum connection to {self.electrum_host}:{self.electrum_port} (SSL: {self.electrum_use_ssl})")
            
            # Use the dedicated Electrum client for testing
            electrum_client = self.env['electrum.client']
            
            # Test server connection
            result = electrum_client.test_connection(
                host=self.electrum_host,
                port=self.electrum_port,
                use_ssl=self.electrum_use_ssl
            )
            
            if result['success']:
                self.electrum_status = 'connected'
                self.electrum_status_message = result['message']
                return True
            else:
                self.electrum_status = 'failed'
                self.electrum_status_message = result['message']
                return False
            
        except Exception as e:
            self.electrum_status = 'failed'
            
            # Provide more specific error messages
            error_str = str(e)
            if "Connection refused" in error_str:
                self.electrum_status_message = f"Connection refused - Electrum server not accessible at {self.electrum_host}:{self.electrum_port}"
            elif "timeout" in error_str.lower():
                self.electrum_status_message = f"Connection timeout - Electrum server not responding"
            elif "Name or service not known" in error_str:
                self.electrum_status_message = f"DNS error - cannot resolve hostname '{self.electrum_host}'"
            elif "SSL" in error_str or "certificate" in error_str.lower():
                self.electrum_status_message = f"SSL/Certificate error - try disabling SSL or check server certificate"
            else:
                self.electrum_status_message = f"Connection failed: {error_str}"
                
            _logger.error(f"Electrum connection test failed: {self.electrum_status_message}")
            return False

    def get_bitcoin_connector(self):
        """Get or create Bitcoin Core connector based on current settings"""
        self.ensure_one()
        
        if not self.use_bitcoin_core:
            return None  # Bitcoin Core disabled
            
        # Check if we have valid credentials
        if not self.bitcoin_core_rpc_user or not self.bitcoin_core_rpc_password:
            _logger.warning("Bitcoin Core credentials not configured - skipping connector creation")
            return None
            
        # Look for existing connector with matching settings
        existing_connector = self.env['bitcoin.connector'].search([
            ('rpc_host', '=', self.bitcoin_core_rpc_host),
            ('rpc_port', '=', self.bitcoin_core_rpc_port),
            ('rpc_user', '=', self.bitcoin_core_rpc_user),
            ('network', '=', self.network),
            ('is_active', '=', True)
        ], limit=1)
        
        if existing_connector:
            return existing_connector
            
        # Create new connector
        connector = self.env['bitcoin.connector'].create({
            'name': f'{self.name} - Bitcoin Core',
            'rpc_host': self.bitcoin_core_rpc_host,
            'rpc_port': self.bitcoin_core_rpc_port,
            'rpc_user': self.bitcoin_core_rpc_user,
            'rpc_password': self.bitcoin_core_rpc_password,
            'use_ssl': self.bitcoin_core_use_ssl,
            'network': self.network,
            'is_active': True,
            'cache_duration_minutes': self.blockchain_info_cache_minutes
        })
        
        return connector

    def get_electrum_client(self):
        """Get Electrum client for transaction history"""
        self.ensure_one()
        
        if not self.use_electrum:
            return None  # Electrum disabled
            
        # Return the Electrum client (it will use our configuration)
        return self.env['electrum.client']

    @api.model
    def get_import_settings(self):
        """Get transaction import settings from default configuration"""
        settings = self.get_default_settings()
        return {
            'max_addresses': settings.max_addresses_per_import,
            'chunk_size': settings.import_chunk_size,
            'delay_between_addresses': settings.import_delay_between_addresses
        }
        
    @api.model
    def get_services_config(self):
        """Get configuration for both Bitcoin services"""
        settings = self.get_default_settings()
        # Get Bitcoin connector safely
        bitcoin_connector = None
        if settings.use_bitcoin_core:
            try:
                bitcoin_connector = settings.get_bitcoin_connector()
            except Exception as e:
                _logger.warning(f"Bitcoin Core connector not available: {str(e)}")
                
        return {
            'bitcoin_core': {
                'enabled': settings.use_bitcoin_core,
                'connector': bitcoin_connector
            },
            'electrum': {
                'enabled': settings.use_electrum,
                'client': settings.get_electrum_client() if settings.use_electrum else None,
                'host': settings.electrum_host,
                'port': settings.electrum_port,
                'use_ssl': settings.electrum_use_ssl
            },
            'network': settings.network
        }

    @api.model
    def migrate_to_new_config_models(self):
        """Migrate existing bitcoin.settings data to new configuration models"""
        _logger.info("Starting migration of bitcoin.settings to new configuration models")
        
        # Get all existing bitcoin settings
        existing_settings = self.search([])
        migration_results = {
            'bitcoin_nodes_created': 0,
            'electrum_servers_created': 0,
            'settings_processed': 0
        }
        
        for settings in existing_settings:
            try:
                # Migrate Bitcoin Core settings
                if settings.use_bitcoin_core and settings.bitcoin_core_rpc_user and settings.bitcoin_core_rpc_password:
                    # Check if Bitcoin node config already exists
                    existing_node = self.env['bitcoin.node.config'].search([
                        ('rpc_host', '=', settings.bitcoin_core_rpc_host),
                        ('rpc_port', '=', settings.bitcoin_core_rpc_port),
                        ('rpc_user', '=', settings.bitcoin_core_rpc_user),
                        ('network', '=', settings.network)
                    ])
                    
                    if not existing_node:
                        node_vals = {
                            'name': f'Migrated - {settings.name} (Bitcoin Core)',
                            'rpc_host': settings.bitcoin_core_rpc_host,
                            'rpc_port': settings.bitcoin_core_rpc_port,
                            'rpc_user': settings.bitcoin_core_rpc_user,
                            'rpc_password': settings.bitcoin_core_rpc_password,
                            'use_ssl': settings.bitcoin_core_use_ssl,
                            'network': settings.network,
                            'sequence': 10,  # Default priority
                            'is_active': True
                        }
                        
                        # Set connection status based on old status
                        if settings.bitcoin_core_status == 'connected':
                            node_vals['connection_status'] = 'connected'
                        elif settings.bitcoin_core_status == 'failed':
                            node_vals['connection_status'] = 'error'
                        else:
                            node_vals['connection_status'] = 'unknown'
                            
                        new_node = self.env['bitcoin.node.config'].create(node_vals)
                        migration_results['bitcoin_nodes_created'] += 1
                        _logger.info(f"Created Bitcoin node config: {new_node.name}")
                
                # Migrate Electrum settings
                if settings.use_electrum and settings.electrum_host:
                    # Check if Electrum server config already exists
                    existing_server = self.env['electrum.server.config'].search([
                        ('host', '=', settings.electrum_host),
                        ('port', '=', settings.electrum_port),
                        ('network', '=', settings.network)
                    ])
                    
                    if not existing_server:
                        server_vals = {
                            'name': f'Migrated - {settings.name} (Electrum)',
                            'host': settings.electrum_host,
                            'port': settings.electrum_port,
                            'use_ssl': settings.electrum_use_ssl,
                            'network': settings.network,
                            'sequence': 10,  # Default priority
                            'is_active': True
                        }
                        
                        # Set connection status based on old status
                        if settings.electrum_status == 'connected':
                            server_vals['connection_status'] = 'connected'
                        elif settings.electrum_status == 'failed':
                            server_vals['connection_status'] = 'error'
                        else:
                            server_vals['connection_status'] = 'unknown'
                            
                        new_server = self.env['electrum.server.config'].create(server_vals)
                        migration_results['electrum_servers_created'] += 1
                        _logger.info(f"Created Electrum server config: {new_server.name}")
                
                migration_results['settings_processed'] += 1
                
            except Exception as e:
                _logger.error(f"Failed to migrate settings {settings.name}: {str(e)}")
                continue
        
        # If no Electrum servers were created from migration, create default ones
        if migration_results['electrum_servers_created'] == 0:
            _logger.info("No Electrum servers created from migration, creating default servers")
            # Create default servers for mainnet and testnet
            mainnet_created = self.env['electrum.server.config'].create_default_servers('mainnet')
            testnet_created = self.env['electrum.server.config'].create_default_servers('testnet')
            migration_results['electrum_servers_created'] = mainnet_created + testnet_created
            _logger.info(f"Created {mainnet_created} mainnet and {testnet_created} testnet default Electrum servers")
        
        _logger.info(f"Migration completed: {migration_results}")
        return migration_results

    def action_migrate_to_new_models(self):
        """Action to trigger migration from UI"""
        self.ensure_one()
        
        results = self.migrate_to_new_config_models()
        
        message = f"""Migration completed successfully!

Results:
• {results['bitcoin_nodes_created']} Bitcoin Core node configurations created
• {results['electrum_servers_created']} Electrum server configurations created  
• {results['settings_processed']} settings records processed

You can now manage individual server configurations in:
• Bitcoin → Configuration → Bitcoin Core Nodes
• Bitcoin → Configuration → Electrum Servers
"""
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Migration Complete',
                'message': message,
                'type': 'success',
                'sticky': True
            }
        }