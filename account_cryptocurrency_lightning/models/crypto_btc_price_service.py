# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api, _
from odoo.exceptions import UserError
import logging
import requests

_logger = logging.getLogger(__name__)


class CryptoBtcPriceService(models.Model):
    _name = 'crypto.btc.price.service'
    _description = 'Bitcoin Price Service'
    _order = 'sequence, id'

    name = fields.Char(string='Service Name', required=True)
    sequence = fields.Integer(string='Priority', default=10,
                             help='Lower numbers = higher priority')
    active = fields.Boolean(string='Active', default=True)
    service_type = fields.Selection([
        ('coingecko', 'CoinGecko API'),
        ('custom', 'Custom Implementation')
    ], string='Service Type', required=True, default='coingecko')

    # Service configuration
    api_url = fields.Char(string='API URL')
    api_key = fields.Char(string='API Key')
    rate_limit_seconds = fields.Integer(string='Rate Limit (seconds)', default=60)
    timeout_seconds = fields.Integer(string='Timeout (seconds)', default=10)

    # Caching
    cache_duration_minutes = fields.Integer(string='Cache Duration (minutes)', default=5)
    last_update = fields.Datetime(string='Last Update', readonly=True)
    cached_prices = fields.Text(string='Cached Prices JSON', readonly=True)

    # Statistics
    success_count = fields.Integer(string='Successful Requests', readonly=True)
    error_count = fields.Integer(string='Failed Requests', readonly=True)
    last_error = fields.Text(string='Last Error', readonly=True)

    @api.model
    def get_btc_price(self, currency_name):
        """
        Get BTC price in specified currency using the highest priority active service.

        Args:
            currency_name (str): Currency code (e.g., 'USD', 'EUR')

        Returns:
            float: BTC price in specified currency
        """
        # Find active services in priority order
        services = self.search([('active', '=', True)], order='sequence, id')

        if not services:
            raise UserError("No active BTC price services configured")

        last_error = None

        for service in services:
            try:
                price = service._get_price_from_service(currency_name)
                if price and price > 0:
                    service._update_success_stats()
                    return price
            except Exception as e:
                last_error = str(e)
                service._update_error_stats(last_error)
                _logger.warning(f"BTC price service {service.name} failed: {last_error}")
                continue

        # All services failed
        raise UserError(f"All BTC price services failed. Last error: {last_error}")

    def _get_price_from_service(self, currency_name):
        """
        Get price from this specific service. Override this method for custom implementations.

        Args:
            currency_name (str): Currency code

        Returns:
            float: BTC price in specified currency
        """
        self.ensure_one()

        # Check cache first
        cached_price = self._get_cached_price(currency_name)
        if cached_price:
            return cached_price

        if self.service_type == 'coingecko':
            price = self._get_coingecko_price(currency_name)
        elif self.service_type == 'custom':
            # This method should be overridden by custom modules
            price = self._get_custom_price(currency_name)
        else:
            raise UserError(f"Unknown service type: {self.service_type}")

        # Cache the result
        if price:
            self._cache_price(currency_name, price)

        return price

    def _get_coingecko_price(self, currency_name):
        """Default CoinGecko implementation"""
        api_url = self.api_url or "https://api.coingecko.com/api/v3/simple/price"

        params = {
            'ids': 'bitcoin',
            'vs_currencies': currency_name.lower()
        }

        response = requests.get(api_url, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()

        data = response.json()
        return data['bitcoin'][currency_name.lower()]

    def _get_custom_price(self, currency_name):
        """
        Override this method in custom modules to implement your own price source.

        Example in a custom module:

        class CryptoBtcPriceService(models.Model):
            _inherit = 'crypto.btc.price.service'

            def _get_custom_price(self, currency_name):
                # Your custom implementation here
                return your_custom_price_logic(currency_name)
        """
        raise UserError("Custom price service not implemented. Please override _get_custom_price method.")

    def _get_cached_price(self, currency_name):
        """Get price from cache if still valid"""
        if not self.cached_prices or not self.last_update:
            return None

        # Check if cache is still valid
        cache_age = fields.Datetime.now() - self.last_update
        if cache_age.total_seconds() > (self.cache_duration_minutes * 60):
            return None

        try:
            import json
            cached_data = json.loads(self.cached_prices)
            return cached_data.get(currency_name.lower())
        except (json.JSONDecodeError, KeyError):
            return None

    def _cache_price(self, currency_name, price):
        """Cache the price"""
        try:
            import json
            cached_data = {}
            if self.cached_prices:
                cached_data = json.loads(self.cached_prices)

            cached_data[currency_name.lower()] = price

            self.write({
                'cached_prices': json.dumps(cached_data),
                'last_update': fields.Datetime.now()
            })
        except Exception as e:
            _logger.warning(f"Failed to cache price: {str(e)}")

    def _update_success_stats(self):
        """Update success statistics"""
        self.write({'success_count': self.success_count + 1})

    def _update_error_stats(self, error_msg):
        """Update error statistics"""
        self.write({
            'error_count': self.error_count + 1,
            'last_error': error_msg
        })

    def action_test_service(self):
        """Test the service with USD"""
        try:
            price = self._get_price_from_service('USD')
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Service Test Successful',
                    'message': f'BTC Price: ${price:,.2f} USD',
                    'type': 'success',
                }
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Service Test Failed',
                    'message': str(e),
                    'type': 'danger',
                }
            }

    def action_clear_cache(self):
        """Clear the price cache"""
        self.write({
            'cached_prices': False,
            'last_update': False
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Cache Cleared',
                'message': 'Price cache has been cleared',
                'type': 'info',
            }
        }


class CryptoBtcPriceManager(models.AbstractModel):
    """Helper model to provide easy access to BTC prices"""
    _name = 'crypto.btc.price.manager'
    _description = 'BTC Price Manager'

    @api.model
    def get_btc_price(self, currency_name):
        """Convenience method to get BTC price"""
        return self.env['crypto.btc.price.service'].get_btc_price(currency_name)