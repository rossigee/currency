# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import UserError
import requests
import qrcode
import io
import base64
import json
import logging

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


_logger = logging.getLogger(__name__)


class CryptoLightningPayment(models.Model):
    _name = 'crypto.lightning.payment'
    _description = 'Lightning Payment Record'
    _order = 'creation_date desc'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Basic payment information
    address_id = fields.Many2one('crypto.lightning.address', string='Lightning Address', required=True)
    partner_id = fields.Many2one('res.partner', string='Partner', related='address_id.owner_id', store=True, readonly=True)
    amount = fields.Float(string='Amount', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.company.currency_id)
    btc_price = fields.Float(string='BTC Price at Time of Payment', readonly=True)
    btc_current_price = fields.Float(string='BTC Current Price', compute='_compute_btc_current_price', readonly=True)
    satoshis = fields.Integer(string='Amount (satoshis)', required=True)
    satoshis_current = fields.Integer(string='Amount (satoshis) at Current Rate', compute='_compute_satoshis_current', readonly=True)
    lsp_id = fields.Many2one('crypto.lightning.service.provider', string='Lightning Service Provider', required=True,
                          default=lambda self: self.env['crypto.lightning.service.provider'].search([], limit=1))

    # Payment status and tracking
    payment_status = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Payment Pending'),
        ('success', 'Payment Successful'),
        ('failed', 'Payment Failed'),
    ], string='Payment Status', default='draft', readonly=True, tracking=True)
    last_state_change = fields.Datetime(string='Last State Change', readonly=True, default=fields.Datetime.now, tracking=True)
    state_change_user_id = fields.Many2one('res.users', string='State Changed By', readonly=True, default=lambda self: self.env.user)

    # Transaction details
    payment_hash = fields.Char(string='Payment Hash', readonly=True, index=True)
    payment_preimage = fields.Char(string='Payment Preimage', readonly=True)
    fee_paid_sat = fields.Integer(string='Fee Paid (sats)', readonly=True)
    payment_error = fields.Text(string='Payment Error', readonly=True)
    payment_job_uuid = fields.Char(string='Job UUID', readonly=True)

    # Timing information
    creation_date = fields.Datetime(string='Created', readonly=True, default=fields.Datetime.now)
    payment_creation_date = fields.Datetime(string='Payment Created', readonly=True, default=fields.Datetime.now)
    completion_date = fields.Datetime(string='Completed', readonly=True)
    payment_completion_date = fields.Datetime(string='Payment Completed', readonly=True)

    # Route information
    payment_route_hops = fields.Integer(string='Route Hops', readonly=True)
    payment_total_time_lock = fields.Integer(string='Total Time Lock', readonly=True)

    # Technical details
    decoded_invoice_details = fields.Text(string='Invoice Details', readonly=True)
    ln_payment_ref = fields.Text(string='Payment Request', readonly=True)
    ln_payment_ref_current = fields.Text(string='Current Payment Request', compute='_compute_current_payment_ref', readonly=True)
    ln_payment_qrcode = fields.Binary(string='Payment QR Code', readonly=True)
    ln_payment_qrcode_current = fields.Binary(string='Current Payment QR Code', compute='_compute_current_qrcode', readonly=True)
    payment_attempt_id = fields.Char(string='Payment Attempt ID', readonly=True)
    callback_url = fields.Text(string='Callback URL', readonly=True)
    callback_url_current = fields.Text(string='Current Callback URL', compute='_compute_current_callback_url', readonly=True)

    # Notes and attachments
    notes = fields.Html(string='Internal Notes', help='Internal notes for this payment')
    attachment_count = fields.Integer(string='Attachment Count', compute='_compute_attachment_count')

    # Scheduled payment link
    scheduled_payment_id = fields.Many2one('crypto.lightning.scheduled.payment',
                                          string='Scheduled Payment', readonly=True,
                                          help='Link to scheduled payment if this was auto-generated')

    # Display name
    display_name = fields.Char(string='Payment Reference', compute='_compute_display_name', store=True)

    @api.depends('currency_id')
    def _compute_btc_current_price(self):
        """Compute current BTC price for draft payments"""
        for record in self:
            if record.currency_id:
                try:
                    record.btc_current_price = record.env['crypto.btc.price.service'].get_btc_price(record.currency_id.name)
                except Exception:
                    record.btc_current_price = 0.0
            else:
                record.btc_current_price = 0.0

    @api.depends('amount', 'currency_id', 'btc_current_price')
    def _compute_satoshis_current(self):
        """Compute satoshis at current BTC price for draft payments"""
        for record in self:
            if record.amount and record.currency_id and record.btc_current_price > 0:
                try:
                    # Convert amount to company base currency
                    base_amount = record.currency_id._convert(
                        record.amount,
                        record.env.company.currency_id,
                        record.env.company,
                        fields.Date.today()
                    )
                    # Convert to satoshis using current BTC price
                    record.satoshis_current = int((base_amount / record.btc_current_price) * 100000000)
                except Exception:
                    record.satoshis_current = 0
            else:
                record.satoshis_current = 0

    @api.depends('address_id')
    def _compute_current_callback_url(self):
        """Get callback URL for current lightning address"""
        for record in self:
            if record.payment_status == 'draft' and record.address_id:
                try:
                    processor = record.env['crypto.lightning.payment.processor']
                    payment_request = processor.create_payment_request(record.address_id.address)
                    record.callback_url_current = payment_request.get('callback') if payment_request else False
                except Exception:
                    record.callback_url_current = False
            else:
                record.callback_url_current = False

    @api.depends('address_id', 'satoshis_current', 'callback_url_current')
    def _compute_current_payment_ref(self):
        """Generate current payment request for draft payments"""
        for record in self:
            if (record.payment_status == 'draft' and
                record.address_id and record.satoshis_current > 0 and record.callback_url_current):
                try:
                    msats = record.satoshis_current * 1000
                    lnurl = f"{record.callback_url_current}?amount={msats}"
                    response = requests.get(lnurl, timeout=10)
                    response.raise_for_status()
                    body = response.json()
                    record.ln_payment_ref_current = body.get('pr', '').encode().lower()
                except Exception:
                    record.ln_payment_ref_current = False
            else:
                record.ln_payment_ref_current = False

    @api.depends('ln_payment_ref_current')
    def _compute_current_qrcode(self):
        """Generate QR code for current payment request"""
        for record in self:
            if record.ln_payment_ref_current:
                try:
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10,
                        border=4,
                    )
                    qr.add_data(record.ln_payment_ref_current.upper())
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    temp = io.BytesIO()
                    img.save(temp, format="PNG")
                    record.ln_payment_qrcode_current = base64.b64encode(temp.getvalue())
                except Exception:
                    record.ln_payment_qrcode_current = False
            else:
                record.ln_payment_qrcode_current = False

    def _compute_attachment_count(self):
        """Compute number of attachments for this payment"""
        for record in self:
            record.attachment_count = self.env['ir.attachment'].search_count([
                ('res_model', '=', self._name),
                ('res_id', '=', record.id)
            ])

    def action_view_attachments(self):
        """Open attachment view for this payment"""
        self.ensure_one()
        return {
            'name': 'Attachments',
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment',
            'view_mode': 'tree,form',
            'domain': [('res_model', '=', self._name), ('res_id', '=', self.id)],
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
            }
        }


    @api.depends('address_id', 'amount', 'currency_id', 'creation_date')
    def _compute_display_name(self):
        for record in self:
            if record.address_id and record.amount:
                address_name = record.address_id.address[:20] + ('...' if len(record.address_id.address) > 20 else '')
                record.display_name = f"{record.amount} {record.currency_id.name} to {address_name}"
            else:
                record.display_name = f"Payment #{record.id or 'New'}"

    def action_pay_now(self):
        """
        Initiate Lightning payment as a background job.
        This prevents UI blocking for slow payments.
        """
        self.ensure_one()

        try:
            # Validate required fields for payment
            if not self.address_id:
                raise UserError("Please select a Lightning Address before proceeding with payment.")

            if not self.amount or self.amount <= 0:
                raise UserError("Please enter a valid payment amount.")

            if not self.currency_id:
                raise UserError("Please select a currency.")

            if self.payment_status != 'draft':
                raise UserError("Payment has already been processed or is in progress.")

            # Validate that we have a service provider
            if not self.lsp_id:
                raise UserError("No Lightning Service Provider selected.")

            if not self.lsp_id.rest_url:
                raise UserError("Lightning Service Provider has no REST URL configured.")

            # Force computation of current values if not available with detailed error checking
            if not self.btc_current_price or self.btc_current_price <= 0:
                self._compute_btc_current_price()
                if not self.btc_current_price or self.btc_current_price <= 0:
                    raise UserError("Unable to get current BTC price. Please check your internet connection and try again.")

            if not self.satoshis_current or self.satoshis_current <= 0:
                self._compute_satoshis_current()
                if not self.satoshis_current or self.satoshis_current <= 0:
                    raise UserError(f"Unable to calculate satoshi amount. Current BTC price: {self.btc_current_price}, Amount: {self.amount} {self.currency_id.name}")

            if not self.callback_url_current:
                self._compute_current_callback_url()
                if not self.callback_url_current:
                    raise UserError(f"Unable to get callback URL from Lightning address: {self.address_id.address}. Please check the address is valid and accessible.")

            if not self.ln_payment_ref_current:
                self._compute_current_payment_ref()
                if not self.ln_payment_ref_current:
                    raise UserError(f"Failed to generate payment request from callback URL: {self.callback_url_current}. Amount: {self.satoshis_current} sats. Please check the Lightning address configuration.")

            # Store computed values before changing status (freeze the exchange rate/amounts)
            values_to_update = {
                'payment_status': 'pending',
                'payment_error': False,
                'payment_creation_date': fields.Datetime.now(),
                'last_state_change': fields.Datetime.now(),
                'state_change_user_id': self.env.user.id,
            }

            # Store current computed values as permanent values
            if self.btc_current_price and self.btc_current_price > 0:
                values_to_update['btc_price'] = self.btc_current_price
            else:
                raise UserError("Unable to get current BTC price. Please check your internet connection.")

            if self.satoshis_current and self.satoshis_current > 0:
                values_to_update['satoshis'] = self.satoshis_current
            else:
                raise UserError("Unable to calculate satoshi amount. Please check the amount and currency.")

            if self.callback_url_current:
                values_to_update['callback_url'] = self.callback_url_current

            if self.ln_payment_ref_current:
                values_to_update['ln_payment_ref'] = self.ln_payment_ref_current
            else:
                raise UserError("Failed to generate payment request. Please check the Lightning address configuration.")

            if self.ln_payment_qrcode_current:
                values_to_update['ln_payment_qrcode'] = self.ln_payment_qrcode_current

            # Update record with frozen values and pending status FIRST
            self.write(values_to_update)

            # Start background job AFTER status is updated
            try:
                job = self.with_delay()._process_lightning_payment()
                self.payment_job_uuid = job.uuid
            except Exception as job_error:
                # If job creation fails, revert status but keep the frozen values
                self.write({
                    'payment_status': 'draft',
                    'payment_error': f"Failed to start background job: {str(job_error)}"
                })
                raise UserError(f"Failed to start payment processing job: {str(job_error)}")

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Payment Started',
                    'message': 'Lightning payment is being processed in the background. You will be notified when complete.',
                    'type': 'info',
                    'sticky': False,
                }
            }

        except Exception as e:
            # Log the error and show user-friendly message
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Payment initiation failed for payment {self.id}: {str(e)}")

            # If it's already a UserError, just re-raise it
            if isinstance(e, UserError):
                raise
            else:
                # For other exceptions, wrap in UserError
                raise UserError(f"Payment initiation failed: {str(e)}")

    @job(default_channel='root.lightning')
    def _process_lightning_payment(self):
        """
        Background job to process Lightning payment via LND.
        This method runs in a separate worker process.
        """
        import logging
        _logger = logging.getLogger(__name__)

        _logger.info(f"Starting Lightning payment processing for payment {self.id}")

        try:
            # Import here to avoid circular import
            from .lnd_rest_client import LndRestClient

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
                # Use stored payment reference
                payment_ref = self.ln_payment_ref
                if isinstance(payment_ref, bytes):
                    payment_ref = payment_ref.decode()

                # Decode payment request first to get details
                decoded = client.decode_payment_request(payment_ref)
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
                payment_result = client.pay_invoice(payment_ref, fee_limit_sat)

                # Update payment status based on result
                if payment_result.get('payment_error'):
                    # Payment failed
                    self.write({
                        'payment_status': 'failed',
                        'payment_error': payment_result['payment_error'],
                        'payment_completion_date': fields.Datetime.now(),
                        'completion_date': fields.Datetime.now(),
                        'decoded_invoice_details': json.dumps(decoded_info, indent=2),
                        'last_state_change': fields.Datetime.now(),
                        'state_change_user_id': self.env.user.id,
                    })
                    _logger.error(f"Lightning payment failed: {payment_result['payment_error']}")

                    # Send failure notification to LSP mail channel
                    self._send_payment_notification('failed')

                else:
                    # Payment successful - extract route details
                    payment_route = payment_result.get('payment_route', {})
                    total_fees = int(payment_route.get('total_fees', 0))
                    total_time_lock = int(payment_route.get('total_time_lock', 0))
                    hops = payment_route.get('hops', [])
                    completion_date = fields.Datetime.now()

                    # Update record with success status
                    self.write({
                        'payment_status': 'success',
                        'payment_hash': payment_result.get('payment_hash'),
                        'payment_preimage': payment_result.get('payment_preimage'),
                        'fee_paid_sat': total_fees,
                        'payment_route_hops': len(hops),
                        'payment_total_time_lock': total_time_lock,
                        'payment_completion_date': completion_date,
                        'completion_date': completion_date,
                        'decoded_invoice_details': json.dumps(decoded_info, indent=2),
                        'payment_error': False,
                        'last_state_change': fields.Datetime.now(),
                        'state_change_user_id': self.env.user.id,
                    })

                    _logger.info(f"Lightning payment successful: {payment_result.get('payment_hash')} via {len(hops)} hops")

                    # Send success notification to LSP mail channel
                    self._send_payment_notification('success')

            finally:
                client.close()

        except Exception as e:
            error_msg = str(e)
            _logger.error(f"Lightning payment processing failed: {error_msg}")

            self.write({
                'payment_status': 'failed',
                'payment_error': error_msg,
                'payment_completion_date': fields.Datetime.now(),
                'completion_date': fields.Datetime.now(),
                'last_state_change': fields.Datetime.now(),
                'state_change_user_id': self.env.user.id,
            })

            # Send failure notification to LSP mail channel
            self._send_payment_notification('failed')

        # Clear job UUID when done
        self.write({'payment_job_uuid': False})

    def _send_payment_notification(self, status):
        """Send payment notification to LSP mail channel"""
        self.ensure_one()

        # Check if LSP has a notification channel configured
        if not self.lsp_id.mail_channel_id:
            return

        try:
            # Prepare notification message (use HTML format for better rendering)
            if status == 'success':
                message_body = f"""
                <p><strong>⚡ Lightning Payment Successful</strong></p>
                <ul>
                <li><strong>Amount:</strong> {self.amount} {self.currency_id.name} ({self.satoshis} sats)</li>
                <li><strong>To:</strong> {self.address_id.address}</li>
                <li><strong>LSP:</strong> {self.lsp_id.name}</li>
                <li><strong>Fee:</strong> {self.fee_paid_sat} sats</li>
                <li><strong>Route Hops:</strong> {self.payment_route_hops}</li>
                <li><strong>Payment Hash:</strong> <code>{self.payment_hash}</code></li>
                <li><strong>Completion:</strong> {self.completion_date}</li>
                """
                if self.scheduled_payment_id:
                    message_body += f"<li><strong>Scheduled Payment:</strong> {self.scheduled_payment_id.name}</li>"
                message_body += "</ul>"

            else:  # failed
                message_body = f"""
                <p><strong>❌ Lightning Payment Failed</strong></p>
                <ul>
                <li><strong>Amount:</strong> {self.amount} {self.currency_id.name} ({self.satoshis} sats)</li>
                <li><strong>To:</strong> {self.address_id.address}</li>
                <li><strong>LSP:</strong> {self.lsp_id.name}</li>
                <li><strong>Error:</strong> {self.payment_error}</li>
                <li><strong>Failed At:</strong> {self.completion_date}</li>
                """
                if self.scheduled_payment_id:
                    message_body += f"<li><strong>Scheduled Payment:</strong> {self.scheduled_payment_id.name}</li>"
                message_body += "</ul>"

            # Post message to channel with proper message type
            self.lsp_id.mail_channel_id.message_post(
                body=message_body,
                message_type='comment'
            )

            _logger.info(f"Payment notification sent to channel {self.lsp_id.mail_channel_id.name}")

        except Exception as e:
            _logger.warning(f"Failed to send payment notification: {str(e)}")
            # Don't raise exception - notification failure shouldn't block payment processing