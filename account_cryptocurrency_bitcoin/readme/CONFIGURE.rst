=======================================
Bitcoin Module Configuration Guide
=======================================

This guide covers installation, configuration, and setup of the Bitcoin operations module for Odoo.

📋 **Prerequisites**
====================

System Requirements
-------------------
* **Odoo 16.0 or later**: Compatible with Odoo 16+
* **Python 3.8+**: Required for mnemonic library support
* **External Vault**: HashiCorp Vault or OpenBao instance
* **Network Access**: HTTPS connectivity between Odoo and Vault

Required Knowledge
------------------
* **Odoo Administration**: Module installation and user management
* **Vault Administration**: Basic Vault setup and token management
* **Bitcoin Concepts**: Understanding of Bitcoin keys, addresses, and BIP standards
* **Security Practices**: Cryptocurrency security best practices

🚀 **Installation**
===================

Step 1: Install Python Dependencies
------------------------------------

The module requires the `mnemonic` Python library for BIP39 support.

**On Ubuntu/Debian**::

    sudo apt update
    sudo apt install python3-pip
    pip3 install mnemonic

**On CentOS/RHEL**::

    sudo yum install python3-pip
    pip3 install mnemonic

**Using Conda**::

    conda install -c conda-forge mnemonic

**Using Poetry (if used in your Odoo deployment)**::

    poetry add mnemonic

Step 2: Install Odoo Module
----------------------------

**Method 1: Manual Installation**

1. Copy the module to your Odoo addons directory::

    cp -r account_cryptocurrency_bitcoin /path/to/odoo/addons/

2. Restart Odoo server
3. Update the apps list in Odoo
4. Install the "Bitcoin Operations" module

**Method 2: Git Clone**

1. Clone into addons directory::

    cd /path/to/odoo/addons/
    git clone <repository-url> account_cryptocurrency_bitcoin

2. Follow steps 2-4 from Method 1

Step 3: Verify Installation
----------------------------

1. Log into Odoo as administrator
2. Go to **Apps** → **Update Apps List**
3. Search for "Bitcoin Operations"
4. Click **Install**
5. Verify no error messages during installation

🔐 **Vault Setup**
==================

The module requires an external Vault instance for secure key storage. This section covers basic setup.

HashiCorp Vault Installation
-----------------------------

**Using Docker (Recommended for Testing)**::

    # Run Vault in development mode (DO NOT USE IN PRODUCTION)
    docker run --cap-add=IPC_LOCK -d --name=vault-dev -p 8200:8200 vault:latest

    # Get the root token
    docker logs vault-dev

**Production Installation on Ubuntu/Debian**::

    # Add HashiCorp GPG key
    curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo apt-key add -

    # Add repository
    sudo apt-add-repository "deb [arch=amd64] https://apt.releases.hashicorp.com $(lsb_release -cs) main"

    # Install Vault
    sudo apt update && sudo apt install vault

**Production Installation on CentOS/RHEL**::

    # Add repository
    sudo yum install -y yum-utils
    sudo yum-config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo

    # Install Vault
    sudo yum -y install vault

OpenBao Alternative
-------------------

OpenBao is an open-source Vault fork that's fully compatible::

    # Download and install OpenBao
    wget https://github.com/openbao/openbao/releases/download/v1.0.0/bao_1.0.0_linux_amd64.zip
    unzip bao_1.0.0_linux_amd64.zip
    sudo mv bao /usr/local/bin/

Vault Configuration
-------------------

**Basic Production Configuration** (`/etc/vault.d/vault.hcl`)::

    ui = true
    
    storage "file" {
      path = "/opt/vault/data"
    }
    
    listener "tcp" {
      address     = "0.0.0.0:8200"
      tls_cert_file = "/path/to/cert.pem"
      tls_key_file  = "/path/to/key.pem"
    }

**Initialize Vault**::

    # Start Vault
    sudo systemctl start vault
    
    # Initialize (save these keys securely!)
    vault operator init
    
    # Unseal Vault (use 3 of the 5 unseal keys)
    vault operator unseal <key1>
    vault operator unseal <key2>
    vault operator unseal <key3>

**Create Odoo Policy**::

    # Login with root token
    vault auth <root-token>
    
    # Create policy for Odoo
    vault policy write odoo-bitcoin - <<EOF
    path "secret/*" {
      capabilities = ["create", "read", "update", "delete", "list"]
    }
    EOF
    
    # Create token for Odoo
    vault token create -policy=odoo-bitcoin -ttl=8760h

🔧 **Odoo Configuration**
=========================

Environment Variables
---------------------

Set these environment variables for your Odoo instance:

**Option 1: Environment File** (`.env` or in Docker)::

    VAULT_ADDR=https://your-vault-server.com:8200
    VAULT_TOKEN=hvs.XXXXXXXXXXXXXXXXXXXX

**Option 2: System Environment**::

    export VAULT_ADDR=https://your-vault-server.com:8200
    export VAULT_TOKEN=hvs.XXXXXXXXXXXXXXXXXXXX

**Option 3: Docker Compose**::

    version: '3'
    services:
      odoo:
        image: odoo:16
        environment:
          - VAULT_ADDR=https://your-vault-server.com:8200
          - VAULT_TOKEN=hvs.XXXXXXXXXXXXXXXXXXXX

**Option 4: Kubernetes**::

    apiVersion: v1
    kind: Secret
    metadata:
      name: odoo-vault-config
    type: Opaque
    data:
      VAULT_ADDR: <base64-encoded-url>
      VAULT_TOKEN: <base64-encoded-token>

Testing Vault Connection
-------------------------

1. Restart Odoo after setting environment variables
2. Go to **Accounting** → **Bitcoin** → **Key Management**
3. Try creating a private key
4. Check Odoo logs for any Vault connection errors

👥 **User Management**
======================

The module uses security groups to control access to Bitcoin functionality.

Security Groups
---------------

**Bitcoin User** (`group_bitcoin_user`):
* Basic Bitcoin operations
* Private key management
* Account public key creation
* Address derivation
* Partner Bitcoin tab access

**Bitcoin Advanced** (`group_bitcoin_advanced`):
* All Bitcoin User permissions
* Multisig public key creation
* Complex derivation operations
* Multisig wallet management

**Bitcoin Manager** (`group_bitcoin_manager`):
* All permissions
* System configuration
* User permission management
* Full Vault access

Assigning User Permissions
---------------------------

**Method 1: Through User Form**

1. Go to **Settings** → **Users & Companies** → **Users**
2. Open a user record
3. Go to **Access Rights** tab
4. In **Application** section, find **Bitcoin Operations**
5. Select appropriate level:
   * **User**: Basic Bitcoin operations
   * **Advanced**: Include multisig features
   * **Manager**: Full administrative access

**Method 2: Through Groups**

1. Go to **Settings** → **Users & Companies** → **Groups**
2. Search for "Bitcoin"
3. Open the appropriate group
4. Add users to the **Users** tab

**Method 3: Bulk Assignment**

For multiple users, you can assign groups programmatically::

    # In Odoo shell or data import
    users = self.env['res.users'].search([('login', 'in', ['user1', 'user2'])])
    group = self.env.ref('account_cryptocurrency_bitcoin.group_bitcoin_user')
    group.users = [(4, user.id) for user in users]

Initial Administrator Setup
---------------------------

**Automatic**: The main administrator automatically gets Bitcoin Manager permissions.

**Manual Setup**:

1. Login as main administrator
2. Go to **Settings** → **Users & Companies** → **Users**
3. Find your user record
4. Assign "Bitcoin Operations / Manager" permission
5. Refresh your browser to see Bitcoin menu

🔒 **Security Configuration**
=============================

Vault Security Hardening
-------------------------

**Production Vault Security**:

1. **Use TLS**: Always use HTTPS for Vault communication
2. **Network Segmentation**: Isolate Vault on secure network
3. **Regular Backups**: Backup Vault data and unseal keys
4. **Monitor Access**: Enable Vault audit logging
5. **Rotate Tokens**: Regularly rotate Odoo's Vault token

**Vault Audit Logging**::

    vault audit enable file file_path=/vault/logs/audit.log

**Token Rotation**::

    # Create new token
    vault token create -policy=odoo-bitcoin -ttl=8760h
    
    # Update Odoo environment variables
    # Restart Odoo
    
    # Revoke old token
    vault token revoke <old-token>

Network Security
----------------

**Firewall Rules**:

* Only allow Odoo server IP to connect to Vault
* Use VPN or private networks when possible
* Block public access to Vault unless necessary

**TLS Configuration**:

* Use valid SSL certificates
* Implement certificate pinning if possible
* Monitor certificate expiration

Odoo Security Settings
----------------------

**Database Security**:

* Enable database encryption at rest
* Use strong database passwords
* Regular database backups
* Monitor database access logs

**Session Security**:

* Short session timeouts for Bitcoin users
* Two-factor authentication where possible
* Regular password changes
* Monitor user login patterns

🧪 **Testing Configuration**
=============================

Vault Connectivity Test
-----------------------

**Manual Test**::

    # Test Vault connection
    curl -H "X-Vault-Token: $VAULT_TOKEN" $VAULT_ADDR/v1/sys/health

**Odoo Test**:

1. Create a test private key
2. Verify it appears in private key list
3. Check Vault for stored data::

    vault kv get secret/<token-uuid>

**Connection Troubleshooting**:

* Verify environment variables are set
* Check network connectivity to Vault
* Verify Vault token has proper permissions
* Check Odoo logs for connection errors

Module Functionality Test
--------------------------

**Basic Workflow Test**:

1. **Create Private Key**: Generate new mnemonic-based key
2. **Create Account Key**: Generate account 0 public key
3. **View Addresses**: Check derived addresses tab
4. **Partner Assignment**: Assign key to test partner
5. **Multisig Test**: Create multisig key (if advanced user)

**Expected Results**:

* Private keys stored securely in Vault
* Public keys display valid XPUBs
* Addresses generate correctly
* Partner integration works
* Appropriate permissions enforced

📊 **Monitoring & Maintenance**
===============================

Log Monitoring
--------------

**Odoo Logs to Monitor**:

* Bitcoin module operations
* Vault connection attempts
* User permission denials
* Key generation activities

**Vault Logs to Monitor**:

* Odoo authentication attempts
* Key storage/retrieval operations
* Failed authentication attempts
* Token usage patterns

Regular Maintenance
-------------------

**Weekly Tasks**:

* Review Vault access logs
* Check system connectivity
* Verify backup procedures
* Monitor user activity

**Monthly Tasks**:

* Rotate Vault tokens
* Review user permissions
* Update security patches
* Test disaster recovery

**Quarterly Tasks**:

* Full security audit
* Review backup restoration
* Update documentation
* Training for new users

🚨 **Troubleshooting**
======================

Common Configuration Issues
---------------------------

**Vault Connection Failed**:

* **Symptoms**: "Vault not accessible" errors, empty private key data
* **Solutions**: 
  * Check VAULT_ADDR and VAULT_TOKEN environment variables
  * Verify network connectivity to Vault server
  * Check Vault server status and unseal state
  * Verify token has proper permissions

**Bitcoin Menu Not Visible**:

* **Symptoms**: No Bitcoin menu in Accounting section
* **Solutions**:
  * Check user group assignments
  * Verify module installation completed successfully
  * Clear browser cache and refresh
  * Check Odoo logs for permission errors

**Module Installation Fails**:

* **Symptoms**: Error during module installation
* **Solutions**:
  * Install required Python dependencies (mnemonic)
  * Check Odoo version compatibility
  * Verify addons path configuration
  * Review installation logs

**Permission Denied Errors**:

* **Symptoms**: Users can't access Bitcoin features
* **Solutions**:
  * Assign appropriate security groups
  * Check group hierarchy and implications
  * Verify user is active and confirmed
  * Restart user session after permission changes

Performance Issues
------------------

**Slow Key Generation**:

* **Cause**: Network latency to Vault
* **Solutions**: Move Vault closer to Odoo, optimize network

**Address Derivation Slow**:

* **Cause**: Complex cryptographic operations
* **Solutions**: Limit derivation count, use caching

Getting Support
---------------

**Before Requesting Support**:

1. Check all configuration steps
2. Review logs for specific error messages
3. Test Vault connectivity independently
4. Verify user permissions and groups
5. Try with fresh browser session

**Information to Provide**:

* Odoo version and installation method
* Vault version and configuration
* Environment variable settings (without tokens!)
* Relevant log excerpts
* Steps to reproduce issues
* Expected vs actual behavior

**Support Channels**:

* Module documentation and README files
* Odoo Community Association forums
* Bitcoin development community
* Professional Odoo support services