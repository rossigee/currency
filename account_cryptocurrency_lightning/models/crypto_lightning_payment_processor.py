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
    def submit_payment_to_lsp(self, payment_request, service_provider_id=None):
        """
        Submit the payment to the configured Lightning Service Provider.

        :param payment_request: The payment request data
        :param service_provider_id: ID of the service provider to use
        :return: The result of the payment attempt
        """
        if 'error' in payment_request:
            return payment_request

        # Get service provider - use provided ID or find default
        if service_provider_id:
            service_provider = self.env['crypto.lightning.service.provider'].browse(service_provider_id)
        else:
            service_provider = self.env['crypto.lightning.service.provider'].search([
                ('active', '=', True)
            ], limit=1)

        if not service_provider:
            return {'error': 'No Lightning Service Provider configured'}

        if not service_provider.rest_url:
            return {'error': 'Lightning Service Provider has no REST URL configured'}

        try:
            # Get macaroon from vault
            vault_data = service_provider._get_data_from_vault(service_provider.token_uuid)
            macaroon = vault_data.get('macaroon')
            if not macaroon:
                return {'error': 'No macaroon available for service provider'}

            # Convert macaroon to hex if needed
            import base64
            if len(macaroon) % 2 == 0 and all(c in '0123456789abcdefABCDEF' for c in macaroon):
                macaroon_hex = macaroon
            else:
                macaroon_bytes = base64.b64decode(macaroon)
                macaroon_hex = macaroon_bytes.hex()

            # Use LND REST client
            from .lnd_rest_client import LndRestClient
            client = LndRestClient(service_provider.rest_url, macaroon_hex)
            client.connect()

            try:
                # This is now handled by the payment model's background job
                # The payment processor is mainly for LNURL-pay request creation
                return {'success': 'Payment request created successfully'}
            finally:
                client.close()

        except Exception as e:
            return {'error': f'Failed to process payment: {str(e)}'}
