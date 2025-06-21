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


class BitcoinPriceChecker:
    def __init__(self):
        self._latest_prices = {}

    def latest_btc_price(self, currency):
        """
        Get the latest Bitcoin price, caching the result for subsequent calls.

        Returns:
            float: The latest Bitcoin price in the given currency.
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
        Fetch the latest Bitcoin price from the CoinDesk API.

        Returns:
            float: The latest Bitcoin price in USD.
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


class CryptoLightningPaymentForm(models.TransientModel):
    _name = 'crypto.lightning.payment.form'
    _description = 'Lightning Payment Form'

    address_id = fields.Many2one('crypto.lightning.address', string='Lightning Address', required=True)
    amount = fields.Float(string='Amount', required=True, default=0.0)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)

    btc_price = fields.Float(string='BTC Price', readonly=True)
    satoshis = fields.Integer(string='LN Payment Amount (sats)', readonly=True)
    callback_url = fields.Text(string='Callback URL', readonly=True)
    ln_payment_ref = fields.Text(string='LN payment ref', readonly=True)
    ln_payment_qrcode = fields.Binary(string='LN payment QR Code', readonly=True)

    lsp_id = fields.Many2one('crypto.lightning.service.provider', string='Lightning Service Provider', required=True)

    btc_price_checker = BitcoinPriceChecker()

    @api.model
    def default_get(self, fields):
        res = super(CryptoLightningPaymentForm, self).default_get(fields)

        # Default to company currency
        res['currency_id'] = self.env.company.currency_id.id

        # Default to first active LSP configured
        lsps = self.env['crypto.lightning.service.provider'].search([
            ('active', '=', 'true')
        ], limit=1)
        if not lsps:
            raise ValidationError(_("No active Lightning Service Providers available."))
        res['lsp_id'] = lsps.id

        return res

    def create(self, vals):
        """
        Create a new payment form instance.

        This method performs the following steps:
        1. Creates the payment form using the parent class method.
        2. Obtains the latest BTC price.
        3. Logs the creation of the payment form.
        4. Checks if a lightning address is associated with the form.
        5. Retrieves payment request details from the lightning payment processor.
        6. Sets the callback URL for invoice requests.

        :param vals: Dictionary containing the values to create the payment form.
        :return: The newly created payment form instance.
        :raises UserError: If no lightning address is found or if the payment request fails.
        """
        try:
            form = super(CryptoLightningPaymentForm, self).create(vals)

            # Obtain latest BTC price (once)
            form._get_exchange_rate()

            # Set up callback for wallet
            if not form.address_id:
                raise UserError("No lightning address found for the payment form.")

            # Get payment request from recipient's LN
            processor = self.env['crypto.lightning.payment.processor']
            payment_request = processor.create_payment_request(form.address_id.address)
            if not payment_request:
                raise UserError("Failed to create payment request.")

            form.callback_url = payment_request['callback']
            return form

        except Exception as e:
            raise UserError(f"An error occurred while creating the payment form: {str(e)}")

    @api.onchange('currency_id')
    def _get_exchange_rate(self):
        if self.currency_id is not None:
            self.btc_price = self.btc_price_checker.latest_btc_price(self.currency_id.name)

    def _generate_payment_ref(self):
        self.ln_payment_qrcode = None
        if not self.callback_url:
            return
        if self.satoshis <= 0:
            return

        msats = self.satoshis * 1000
        lnurl = f"{self.callback_url}?amount={msats}"

        response = requests.get(lnurl)
        response.raise_for_status()
        body = response.json()
        self.ln_payment_ref = body['pr'].encode().lower()
        if self.ln_payment_ref:
            self._generate_qr_code()

    def _generate_qr_code(self):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(self.ln_payment_ref.upper())
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        temp = io.BytesIO()
        img.save(temp, format="PNG")
        self.ln_payment_qrcode = base64.b64encode(temp.getvalue())

    @api.onchange('currency_id', 'amount')
    def _onchange_currency_amount(self):
        if not self.currency_id or not self.amount:
            return
        if self.btc_price <= 0:
            return

        # Determine requested amount in company base currency
        base_amount = self.currency_id._convert(self.amount, self.env.company.currency_id, self.env.company, fields.Date.today())
        self.satoshis = int((base_amount / self.btc_price) * 100000000)
        self._generate_payment_ref()

    def action_pay_now(self):
        try:
            processor = self.env['crypto.lightning.payment.processor']
            result = processor.submit_payment_to_lsp(self.ln_payment_ref)
            if not result:
                raise UserError("Failed to submit payment to LSP.")

            _logger.info(result)
            self.env['ir.logging'].sudo().create({
                'name': 'Payment Submission Success',
                'type': 'server',
                'message': json.dumps(result),
                'func': 'action_pay_now',
            })

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Payment Submitted',
                    'message': 'The payment request has been successfully submitted to the LSP.',
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            self.env['ir.logging'].sudo().create({
                'name': 'Payment Submission Error',
                'type': 'server',
                'message': str(e),
                'path': '/your/model/action_submit_payment',
                'line': 0,
                'func': 'action_submit_payment',
            })
            raise UserError(f"An error occurred while submitting the payment: {str(e)}")