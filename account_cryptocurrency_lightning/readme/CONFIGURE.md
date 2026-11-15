## Prerequisites

1.  **LND Node**: Running Lightning Network Daemon (LND) v0.19.1+ with
    REST API enabled
2.  **Dependencies**: Ensure vault_connector and queue_job modules are
    installed
3.  **Python Packages**: requests and qrcode (automatically installed)

## Initial Setup

1.  **Install the module** via Apps → Lightning
2.  **Configure Lightning Service Provider**:
    - Navigate to Cryptocurrency → Configuration → Lightning Service
      Providers
    - Click "Create" and fill in:
      - Name: Your LND node name (e.g., "Main LND Node")
      - REST URL: LND REST endpoint (e.g.,
        "https://lnd.yourserver.com:8080")
      - Public Key: Your node's public key (from lncli getinfo)
    - **Upload Macaroon**:
      - Obtain your LND macaroon: base64 /path/to/admin.macaroon
      - Paste the base64 string into the "Macaroon (Base64/Hex)" field
      - Click "Parse and Validate Macaroon" to verify
      - The system will securely store it in the vault
3.  **Test Connection**:
    - In the service provider form, click the "LND Status" tab
    - Click "Refresh Status" to verify connectivity
    - You should see node info, balances, and channel data
4.  **Configure Lightning Addresses**:
    - Navigate to Cryptocurrency → Lightning → Lightning Addresses
    - Add Lightning addresses you want to send payments to
    - Link each address to the appropriate service provider

## Security Configuration

1.  **User Groups**: Assign users to the "Lightning User" group for
    access
2.  **SSL Certificates**: Ensure your LND node has valid SSL
    certificates
3.  **Macaroon Permissions**: Use admin.macaroon or create custom
    macaroons with required permissions:
    - lncli bakemacaroon info:read invoices:read invoices:write
      offchain:read offchain:write
4.  **Firewall**: Ensure LND REST port (default 8080) is accessible from
    Odoo server

## Validation

1.  **Create Test Payment**:
    - Go to Lightning Addresses, select an address
    - Click "Create Payment"
    - Enter amount and click "Pay Now"
    - Verify payment processes through draft → pending → success states
2.  **Check Background Jobs**: Monitor via Settings → Technical → Queue
    Jobs
