# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import requests
import base64
from typing import Dict, Optional


class LndRestClient:
    """
    LND REST client for making calls to Lightning Network Daemon.

    Uses LND's REST API for communication with LND nodes.
    """

    def __init__(self, rest_url: str, macaroon_hex: str):
        """
        Initialize LND REST client.

        Args:
            rest_url: REST endpoint (e.g., "https://localhost:8080")
            macaroon_hex: Macaroon in hex format
        """
        # Ensure URL has protocol
        if not rest_url.startswith(('http://', 'https://')):
            rest_url = f"https://{rest_url}"

        self.rest_url = rest_url.rstrip('/')  # Remove trailing slash
        self.macaroon_hex = macaroon_hex
        self.session = None

    def connect(self):
        """Establish REST session"""
        try:
            # Create requests session with macaroon authentication
            self.session = requests.Session()
            self.session.headers.update({
                'Grpc-Metadata-macaroon': self.macaroon_hex,
                'Content-Type': 'application/json'
            })

            # SSL verification enabled for security (use proper certificates in production)
            self.session.verify = True

            # Test connection with a simple getinfo call
            response = self.session.get(f"{self.rest_url}/v1/getinfo")
            response.raise_for_status()

            return True

        except Exception as e:
            raise Exception(f"Failed to connect to LND: {str(e)}")

    def get_info(self) -> Dict:
        """
        Get basic node information (equivalent to GetInfo RPC).

        Returns:
            Dictionary with node information
        """
        try:
            if not self.session:
                raise Exception("Not connected to LND. Call connect() first.")

            response = self.session.get(f"{self.rest_url}/v1/getinfo")
            response.raise_for_status()

            return response.json()
        except Exception as e:
            raise Exception(f"Failed to get node info: {str(e)}")

    def get_wallet_balance(self) -> Dict:
        """
        Get wallet balance (equivalent to WalletBalance RPC).

        Returns:
            Dictionary with wallet balance information
        """
        try:
            if not self.session:
                raise Exception("Not connected to LND. Call connect() first.")

            response = self.session.get(f"{self.rest_url}/v1/balance/blockchain")
            response.raise_for_status()

            return response.json()
        except Exception as e:
            raise Exception(f"Failed to get wallet balance: {str(e)}")

    def get_channel_balance(self) -> Dict:
        """
        Get channel balance (equivalent to ChannelBalance RPC).

        Returns:
            Dictionary with channel balance information
        """
        try:
            if not self.session:
                raise Exception("Not connected to LND. Call connect() first.")

            response = self.session.get(f"{self.rest_url}/v1/balance/channels")
            response.raise_for_status()

            return response.json()
        except Exception as e:
            raise Exception(f"Failed to get channel balance: {str(e)}")

    def list_channels(self) -> Dict:
        """
        List channels (equivalent to ListChannels RPC).

        Returns:
            Dictionary with channels information
        """
        try:
            if not self.session:
                raise Exception("Not connected to LND. Call connect() first.")

            response = self.session.get(f"{self.rest_url}/v1/channels")
            response.raise_for_status()

            return response.json()
        except Exception as e:
            raise Exception(f"Failed to list channels: {str(e)}")

    def list_peers(self) -> Dict:
        """
        List peers (equivalent to ListPeers RPC).

        Returns:
            Dictionary with peers information
        """
        try:
            if not self.session:
                raise Exception("Not connected to LND. Call connect() first.")

            response = self.session.get(f"{self.rest_url}/v1/peers")
            response.raise_for_status()

            return response.json()
        except Exception as e:
            raise Exception(f"Failed to list peers: {str(e)}")

    def list_invoices(self, num_max_invoices: int = 100) -> Dict:
        """
        List invoices (equivalent to ListInvoices RPC).

        Args:
            num_max_invoices: Maximum number of invoices to return

        Returns:
            Dictionary with invoices information
        """
        try:
            if not self.session:
                raise Exception("Not connected to LND. Call connect() first.")

            params = {'num_max_invoices': num_max_invoices}
            response = self.session.get(f"{self.rest_url}/v1/invoices", params=params)
            response.raise_for_status()

            return response.json()
        except Exception as e:
            raise Exception(f"Failed to list invoices: {str(e)}")

    def list_payments(self, max_payments: int = 100) -> Dict:
        """
        List payments (equivalent to ListPayments RPC).

        Args:
            max_payments: Maximum number of payments to return

        Returns:
            Dictionary with payments information
        """
        try:
            if not self.session:
                raise Exception("Not connected to LND. Call connect() first.")

            params = {'max_payments': max_payments}
            response = self.session.get(f"{self.rest_url}/v1/payments", params=params)
            response.raise_for_status()

            return response.json()
        except Exception as e:
            raise Exception(f"Failed to list payments: {str(e)}")

    def lookup_invoice(self, payment_hash: str) -> Dict:
        """
        Lookup a specific invoice by payment hash.

        Args:
            payment_hash: Payment hash of the invoice

        Returns:
            Dictionary with invoice information
        """
        try:
            if not self.session:
                raise Exception("Not connected to LND. Call connect() first.")

            response = self.session.get(f"{self.rest_url}/v1/invoice/{payment_hash}")
            response.raise_for_status()

            return response.json()
        except Exception as e:
            raise Exception(f"Failed to lookup invoice: {str(e)}")

    def pay_invoice(self, payment_request: str, fee_limit_sat: Optional[int] = None) -> Dict:
        """
        Pay a Lightning invoice (equivalent to SendPaymentSync RPC).

        Args:
            payment_request: Lightning payment request (BOLT11 invoice)
            fee_limit_sat: Maximum fee in satoshis to pay

        Returns:
            Dictionary with payment result
        """
        try:
            if not self.session:
                raise Exception("Not connected to LND. Call connect() first.")

            payload = {
                "payment_request": payment_request
            }

            if fee_limit_sat is not None:
                payload["fee_limit"] = {"fixed": str(fee_limit_sat)}

            response = self.session.post(f"{self.rest_url}/v1/channels/transactions", json=payload)
            response.raise_for_status()

            return response.json()
        except Exception as e:
            raise Exception(f"Failed to pay invoice: {str(e)}")

    def decode_payment_request(self, payment_request: str) -> Dict:
        """
        Decode a Lightning payment request to extract details.

        Args:
            payment_request: Lightning payment request (BOLT11 invoice)

        Returns:
            Dictionary with decoded payment request details
        """
        try:
            if not self.session:
                raise Exception("Not connected to LND. Call connect() first.")

            response = self.session.get(f"{self.rest_url}/v1/payreq/{payment_request}")
            response.raise_for_status()

            return response.json()
        except Exception as e:
            raise Exception(f"Failed to decode payment request: {str(e)}")

    def close(self):
        """Close REST session"""
        if self.session:
            self.session.close()
            self.session = None