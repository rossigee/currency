# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api

import requests
import json


class CryptoLightningPaymentProcessor(models.Model):
    #_inherit = 'payment.processor'  # Assuming you have a payment processor model
    _name = "crypto.lightning.payment.processor"
    _description = "Lightning Network payment processor"

    @api.model
    def process_lightning_payment(self, address, amount_sats):
        """
        Process a Lightning Network payment using the configured LSP.

        This method performs the following steps:
        1. Creates a payment request on the recipient's LN node.
        2. Submits the payment to the LSP for processing.
        3. Returns the result of the payment attempt.

        :param address: The address to convert to a well-known URL.
        :param amount_sats: The amount to pay in satoshis.
        :return: A dictionary containing the result of the payment attempt.
        :raises UserError: If the payment request creation or submission fails.
        """
        try:
            # Step 1: Create payment request on recipient's LN node
            payment_request = self.create_payment_request(address)
            if not payment_request:
                raise UserError("Failed to create payment request.")

            # Step 2: Submit payment to LSP for payment
            payment_result = self.submit_payment_to_lsp(payment_request, amount_sats)
            if not payment_result:
                raise UserError("Failed to submit payment to LSP.")

            # Log successful payment processing
            self.env['ir.logging'].sudo().create({
                'name': 'Payment Processed',
                'type': 'server',
                'message': f"Payment processed successfully: {payment_result}",
                'func': 'process_lightning_payment',
            })

            return payment_result
        except Exception as e:
            # Log any errors that occur during the payment processing
            self.env['ir.logging'].sudo().create({
                'name': 'Payment Processing Error',
                'type': 'server',
                'message': str(e),
                'func': 'process_lightning_payment',
            })
            raise UserError(f"An error occurred while processing the payment: {str(e)}")

    @api.model
    def create_payment_request(self, address):
        """
        Create a payment request using the well-known URL for the given address.

        :param well_known_url: The well-known URL to query
        :return: The payment request data
        """

        username, domain = address.split('@')
        well_known_url = f"https://{domain}/.well-known/lnurlp/{username}"

        try:
            response = requests.get(well_known_url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            return {'error': f"Failed to create payment request: {str(e)}"}

    @api.model
    def submit_payment_to_lsp(self, payment_request):
        """
        Submit the payment to the configured LND Integration for invoice.

        :param payment_request: The payment request data
        :return: The result of the payment attempt
        """
        if 'error' in payment_request:
            return payment_request

        lnd_grpc_url = self.env['ir.config_parameter'].sudo().get_param('lnd.integration.lnd_grpc_url')
        lnd_macaroon = self.env['ir.config_parameter'].sudo().get_param('lnd.integration.lnd_macaroon')

        headers = {
            'Authorization': f'Bearer {lnd_macaroon}',
            'Content-Type': 'application/json'
        }

        response = requests.post(
            f"{lnd_grpc_url}/pay_invoice",
            headers=headers,
            data=json.dumps(payment_request)
        )
        response.raise_for_status()
        return response.json()
