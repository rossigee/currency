Prerequisites
~~~~~~~~~~~~~

#. **LND Node**: Running Lightning Network Daemon (LND) v0.19.1+ with REST API enabled
#. **Dependencies**: Ensure `vault_connector` and `queue_job` modules are installed
#. **Python Packages**: `requests` and `qrcode` (automatically installed)

Initial Setup
~~~~~~~~~~~~~

#. **Install the module** via Apps → Lightning
#. **Configure Lightning Service Provider**:
   
   * Navigate to Cryptocurrency → Configuration → Lightning Service Providers
   * Click "Create" and fill in:
     
     - Name: Your LND node name (e.g., "Main LND Node")
     - REST URL: LND REST endpoint (e.g., "https://lnd.yourserver.com:8080")
     - Public Key: Your node's public key (from `lncli getinfo`)
   
   * **Upload Macaroon**:
     
     - Obtain your LND macaroon: `base64 /path/to/admin.macaroon`
     - Paste the base64 string into the "Macaroon (Base64/Hex)" field
     - Click "Parse and Validate Macaroon" to verify
     - The system will securely store it in the vault

#. **Test Connection**:
   
   * In the service provider form, click the "LND Status" tab
   * Click "Refresh Status" to verify connectivity
   * You should see node info, balances, and channel data

#. **Configure Lightning Addresses**:
   
   * Navigate to Cryptocurrency → Lightning → Lightning Addresses
   * Add Lightning addresses you want to send payments to
   * Link each address to the appropriate service provider

Security Configuration
~~~~~~~~~~~~~~~~~~~~~~

#. **User Groups**: Assign users to the "Lightning User" group for access
#. **SSL Certificates**: Ensure your LND node has valid SSL certificates
#. **Macaroon Permissions**: Use admin.macaroon or create custom macaroons with required permissions:
   
   * `lncli bakemacaroon info:read invoices:read invoices:write offchain:read offchain:write`

#. **Firewall**: Ensure LND REST port (default 8080) is accessible from Odoo server

Validation
~~~~~~~~~~

#. **Create Test Payment**:
   
   * Go to Lightning Addresses, select an address
   * Click "Create Payment"
   * Enter amount and click "Pay Now"
   * Verify payment processes through draft → pending → success states

#. **Check Background Jobs**: Monitor via Settings → Technical → Queue Jobs