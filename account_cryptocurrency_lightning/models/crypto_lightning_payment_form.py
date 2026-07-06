# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError

try:
    from odoo.addons.queue_job.models.base import job
except ImportError:
    try:
        from odoo.addons.queue_job.job import job
    except ImportError:
        # Fallback if queue_job is not available
        def job(*args, **kwargs):
            def decorator(func):
                return func
            return decorator

import logging
import requests
import qrcode
import io
import base64
import json

from .lnd_rest_client import LndRestClient


_logger = logging.getLogger(__name__)


class CryptoLightningPaymentForm(models.TransientModel):
    _name = 'crypto.lightning.payment.form'
    _description = 'Lightning Payment Form Wizard'

    address_id = fields.Many2one('crypto.lightning.address', string='Lightning Address', required=False)
    amount = fields.Float(string='Amount', required=True, default=0.0)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)

    btc_price = fields.Float(string='BTC Price', readonly=True)
    satoshis = fields.Integer(string='LN Payment Amount (sats)', readonly=True)
    callback_url = fields.Text(string='Callback URL', readonly=True)
    ln_payment_ref = fields.Text(string='LN payment ref', readonly=True)
    ln_payment_qrcode = fields.Binary(string='LN payment QR Code', readonly=True)

    lsp_id = fields.Many2one('crypto.lightning.service.provider', string='Lightning Service Provider', required=True)

    # Payment status tracking
    payment_status = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Payment Pending'),
        ('success', 'Payment Successful'),
        ('failed', 'Payment Failed'),
    ], string='Payment Status', default='draft', readonly=True)
    payment_hash = fields.Char(string='Payment Hash', readonly=True)
    payment_preimage = fields.Char(string='Payment Preimage', readonly=True)
    fee_paid_sat = fields.Integer(string='Fee Paid (sats)', readonly=True)
    payment_error = fields.Text(string='Payment Error', readonly=True)
    payment_job_uuid = fields.Char(string='Job UUID', readonly=True)

    # Additional transaction details
    payment_creation_date = fields.Datetime(string='Payment Created', readonly=True, default=fields.Datetime.now)
    payment_completion_date = fields.Datetime(string='Payment Completed', readonly=True)
    payment_route_hops = fields.Integer(string='Route Hops', readonly=True, help='Number of hops in the payment route')
    payment_total_time_lock = fields.Integer(string='Total Time Lock', readonly=True)
    decoded_invoice_details = fields.Text(string='Invoice Details', readonly=True, help='Decoded BOLT11 invoice information')
    payment_attempt_id = fields.Char(string='Payment Attempt ID', readonly=True)


    @api.model
    def default_get(self, fields):
        res = super(CryptoLightningPaymentForm, self).default_get(fields)

        # Default to company currency
        res['currency_id'] = self.env.company.currency_id.id

        # Set address_id from context if provided
        if self.env.context.get('default_address_id'):
            res['address_id'] = self.env.context['default_address_id']

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
        3. Sets up callback URL if lightning address is provided.

        :param vals: Dictionary containing the values to create the payment form.
        :return: The newly created payment form instance.
        :raises UserError: If payment request creation fails.
        """
        try:
            form = super(CryptoLightningPaymentForm, self).create(vals)

            # Obtain latest BTC price (once)
            form._get_exchange_rate()

            # Set up callback for wallet only if address is provided
            if form.address_id:
                try:
                    # Get payment request from recipient's LN
                    processor = self.env['crypto.lightning.payment.processor']
                    payment_request = processor.create_payment_request(form.address_id.address)
                    if payment_request:
                        form.callback_url = payment_request['callback']
                        # Generate QR code if we have all required details
                        if form.amount and form.currency_id and form.btc_price:
                            form._onchange_currency_amount()
                except Exception as e:
                    # Log the error but don't fail creation
                    _logger.warning(f"Failed to create payment request for address {form.address_id.address}: {str(e)}")

            return form

        except Exception as e:
            raise UserError(f"An error occurred while creating the payment form: {str(e)}")

    @api.onchange('address_id')
    def _onchange_address_id(self):
        """Set up callback URL when address is selected"""
        if self.address_id and not self.callback_url:
            try:
                processor = self.env['crypto.lightning.payment.processor']
                payment_request = processor.create_payment_request(self.address_id.address)
                if payment_request:
                    self.callback_url = payment_request['callback']
                    # Generate QR code if we have all required details
                    if self.amount and self.currency_id and self.btc_price:
                        self._onchange_currency_amount()
            except Exception as e:
                _logger.warning(f"Failed to create payment request for address {self.address_id.address}: {str(e)}")

    @api.onchange('currency_id')
    def _get_exchange_rate(self):
        if self.currency_id is not None:
            try:
                self.btc_price = self.env['crypto.btc.price.service'].get_btc_price(self.currency_id.name)
            except Exception:
                self.btc_price = 0.0

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
        """
        Create permanent payment record and initiate payment processing.
        """
        self.ensure_one()

        # Validate required fields for payment
        if not self.address_id:
            raise UserError("Please select a Lightning Address before proceeding with payment.")

        if not self.amount or self.amount <= 0:
            raise UserError("Please enter a valid payment amount.")

        if not self.currency_id:
            raise UserError("Please select a currency.")

        if not self.lsp_id:
            raise UserError("No Lightning Service Provider selected.")

        # Create permanent payment record
        permanent_payment = self.env['crypto.lightning.payment'].create({
            'address_id': self.address_id.id,
            'amount': self.amount,
            'currency_id': self.currency_id.id,
            'lsp_id': self.lsp_id.id,
            'payment_status': 'draft',
        })

        # Use the permanent payment's action_pay_now method (which works!)
        result = permanent_payment.action_pay_now()

        # Close the wizard and show the payment record
        return {
            'type': 'ir.actions.act_window',
            'name': 'Lightning Payment',
            'res_model': 'crypto.lightning.payment',
            'res_id': permanent_payment.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @job(default_channel='root.lightning')
    def _process_lightning_payment(self):
        """
        Background job to process Lightning payment via LND.
        This method runs in a separate worker process.
        """
        _logger.info(f"Starting Lightning payment processing for payment form {self.id}")

        try:
            # Get service provider details
            service_provider = self.lsp_id

            # Get macaroon from vault
            vault_data = service_provider._get_data_from_vault(service_provider.token_uuid)
            macaroon = vault_data.get('macaroon')
            if not macaroon:
                raise Exception("No macaroon available for service provider")

            # Convert macaroon to hex if needed
            if len(macaroon) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in macaroon):
                macaroon_hex = macaroon
            else:
                macaroon_bytes = base64.b64decode(macaroon)
                macaroon_hex = macaroon_bytes.hex()

            # Create LND client
            client = LndRestClient(service_provider.rest_url, macaroon_hex)
            client.connect()

            try:
                # Decode payment request first to get details
                decoded = client.decode_payment_request(self.ln_payment_ref.decode())
                _logger.info(f"Decoded payment request: {decoded}")

                # Store decoded invoice details
                decoded_info = {
                    'destination': decoded.get('destination'),
                    'num_satoshis': decoded.get('num_satoshis'),
                    'timestamp': decoded.get('timestamp'),
                    'expiry': decoded.get('expiry'),
                    'description': decoded.get('description', ''),
                    'description_hash': decoded.get('description_hash', ''),
                    'payment_hash': decoded.get('payment_hash', ''),
                    'cltv_expiry': decoded.get('cltv_expiry', 0)
                }

                # Set fee limit (e.g., 1% of payment amount or max 1000 sats)
                amount_sat = int(decoded.get('num_satoshis', 0))
                fee_limit_sat = min(max(amount_sat // 100, 1), 1000)  # 1% with min 1, max 1000 sats

                # Execute payment
                _logger.info(f"Paying invoice for {amount_sat} sats with fee limit {fee_limit_sat} sats")
                payment_result = client.pay_invoice(self.ln_payment_ref.decode(), fee_limit_sat)

                # Update payment status based on result
                if payment_result.get('payment_error'):
                    # Payment failed
                    self.write({
                        'payment_status': 'failed',
                        'payment_error': payment_result['payment_error'],
                        'payment_completion_date': fields.Datetime.now(),
                        'decoded_invoice_details': json.dumps(decoded_info, indent=2)
                    })
                    _logger.error(f"Lightning payment failed: {payment_result['payment_error']}")

                else:
                    # Payment successful - extract route details
                    payment_route = payment_result.get('payment_route', {})
                    total_fees = int(payment_route.get('total_fees', 0))
                    total_time_lock = int(payment_route.get('total_time_lock', 0))
                    hops = payment_route.get('hops', [])
                    completion_date = fields.Datetime.now()

                    # Update wizard status
                    self.write({
                        'payment_status': 'success',
                        'payment_hash': payment_result.get('payment_hash'),
                        'payment_preimage': payment_result.get('payment_preimage'),
                        'fee_paid_sat': total_fees,
                        'payment_route_hops': len(hops),
                        'payment_total_time_lock': total_time_lock,
                        'payment_completion_date': completion_date,
                        'decoded_invoice_details': json.dumps(decoded_info, indent=2),
                        'payment_error': False
                    })

                    # Create permanent payment record
                    self.env['crypto.lightning.payment'].create({
                        'address_id': self.address_id.id,
                        'amount': self.amount,
                        'currency_id': self.currency_id.id,
                        'btc_price': self.btc_price,
                        'satoshis': self.satoshis,
                        'lsp_id': self.lsp_id.id,
                        'payment_status': 'success',
                        'payment_hash': payment_result.get('payment_hash'),
                        'payment_preimage': payment_result.get('payment_preimage'),
                        'fee_paid_sat': total_fees,
                        'payment_route_hops': len(hops),
                        'payment_total_time_lock': total_time_lock,
                        'payment_creation_date': self.payment_creation_date,
                        'payment_completion_date': completion_date,
                        'decoded_invoice_details': json.dumps(decoded_info, indent=2),
                        'ln_payment_ref': self.ln_payment_ref.decode() if isinstance(self.ln_payment_ref, bytes) else self.ln_payment_ref,
                        'ln_payment_qrcode': self.ln_payment_qrcode,
                    })

                    _logger.info(f"Lightning payment successful: {payment_result.get('payment_hash')} via {len(hops)} hops")

            finally:
                client.close()

        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Lightning payment processing failed: {error_msg}")

            self.write({
                'payment_status': 'failed',
                'payment_error': error_msg
            })

        # Clear job UUID when done
        self.write({'payment_job_uuid': False})