# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError

import logging
import requests
import qrcode
import io
import base64
import bech32
import json

_logger = logging.getLogger(__name__)


class BTCPriceChecker:
    def __init__(self):
        self._latest_prices = {}

    def latest_btc_price(self, currency):
        """
        Get the latest BTC price, caching the result for subsequent calls.

        Returns:
            float: The latest BTC price in the given currency.
        """
        try:
            rate = self._latest_prices[currency]
        except KeyError:
            rate = self._get_latest_btc_price(currency)
            if rate is not None:
                self._latest_prices[currency] = rate
        return rate

    def _get_latest_btc_price(self, currency):
        """
        Fetch the latest BTC price from the CoinDesk API.

        Returns:
            float: The latest BTC price in USD.
        """
        try:
            api_url = "https://api.coingecko.com/api/v3/simple/price"
            params = {
                'ids': 'bitcoin',
                'vs_currencies': currency.lower()
            }
            response = requests.get(api_url, params=params)
            response.raise_for_status()
            data = response.json()
            return data['bitcoin'][currency.lower()]
        except requests.RequestException as e:
            _logger.error(f"Error fetching BTC price: {e}")
            return None

