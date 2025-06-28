Daily Operations
~~~~~~~~~~~~~~~~

**Payment Processing**

* Navigate to **Cryptocurrency → Lightning → Lightning Payments**
* Click "Create Payment" to open the payment wizard
* Select Lightning address, enter amount, and click "Pay Now"
* Monitor payment status in real-time (draft → pending → success/failed)
* View detailed transaction information including fees and route hops

**Lightning Address Management**

* **View Addresses**: Cryptocurrency → Lightning → Lightning Addresses
* **Add New Address**: Click "Create" and enter Lightning address (user@domain.com)
* **Link Service Provider**: Associate addresses with your LND nodes
* **View Transactions**: Use "Fetch Transactions" to pull latest activity from LND

**Service Provider Monitoring**

* **Node Status**: Check LND node health via "LND Status" tab
* **Macaroon Management**: Upload/update authentication credentials
* **Connection Testing**: Verify REST API connectivity

**Payment History and Audit**

* **Payment Records**: All payments are permanently stored with complete audit trail
* **Status Tracking**: View state changes, timestamps, and responsible users
* **Transaction Details**: Access route information, fees, and technical data
* **Notes and Attachments**: Add internal documentation to payment records

Payment Workflow
~~~~~~~~~~~~~~~~

1. **Draft State**: Live BTC price calculation, QR code generation for mobile payments
2. **Payment Initiation**: Values freeze at current rates, background job starts
3. **Pending State**: Payment being processed by LND node
4. **Completion**: Success or failure with detailed results and error information

Mobile Payment Support
~~~~~~~~~~~~~~~~~~~~~~

* **QR Code Generation**: Automatic Lightning invoice QR codes for mobile wallet scanning
* **Out-of-band Payments**: Generate payment requests without immediate processing
* **Real-time Updates**: Live price calculations until payment confirmation

Troubleshooting
~~~~~~~~~~~~~~~

**Payment Failures**

* Check Lightning address validity and reachability
* Verify LND node connectivity and channel liquidity
* Review macaroon permissions and expiration
* Monitor background job logs for detailed error messages

**Connection Issues**

* Validate REST URL accessibility and SSL certificates
* Check firewall rules and network connectivity
* Verify macaroon encoding (base64 vs hex)
* Test with `lncli getinfo` directly on LND server

**Performance Optimization**

* Use queue_job for background payment processing
* Configure appropriate fee limits for routing
* Monitor channel balance and liquidity management
* Regular macaroon rotation for security

Customization
~~~~~~~~~~~~~

**BTC Price Service Override**

The module uses a configurable BTC price service system that can be customized:

* **Via UI**: Navigate to Configuration → BTC Price Services to add custom services
* **Priority System**: Services are tried in sequence order (lower sequence = higher priority)
* **Custom Implementation**: Create a custom module to override price sources:

.. code-block:: python

   # In your custom module
   from odoo import models

   class CryptoBtcPriceService(models.Model):
       _inherit = 'crypto.btc.price.service'
       
       def _get_custom_price(self, currency_name):
           # Your custom API integration
           return your_api_call(currency_name)

* **Service Types**: 
  
  - ``coingecko``: Default CoinGecko API integration
  - ``custom``: Override ``_get_custom_price()`` method for your implementation

* **Built-in Features**: Automatic caching, fallback handling, error tracking, and statistics