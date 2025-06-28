=============================
Bitcoin Module Usage Guide
=============================

This guide provides step-by-step instructions for common Bitcoin operations in Odoo.

🚀 **Getting Started**
======================

After installation and configuration, you'll find the Bitcoin functionality under **Accounting** → **Bitcoin** in the main menu.

**Note**: Bitcoin functionality is only visible to users with appropriate permissions. See the CONFIGURE.rst file for user group setup.

📋 **Basic Workflow**
=====================

1. **Create Private Key** → 2. **Generate Account Keys** → 3. **Derive Addresses** → 4. **Use for Payments**

🔑 **Private Key Management**
=============================

Creating a New Private Key
---------------------------

1. Navigate to **Accounting** → **Bitcoin** → **Key Management** → **Create Private Key**
2. Choose your key generation method:

   **Generate New Key (Recommended)**:
   
   * Select "Generate New Private Key"
   * Choose word count (12, 15, 18, 21, or 24 words)
   * Optionally add a BIP39 passphrase for extra security
   * Click **Save**
   * **IMPORTANT**: Write down the mnemonic phrase shown - this is your only backup!

   **Import Existing Key**:
   
   * Select "Import from Mnemonic" or "Import from XPRV"
   * Enter your mnemonic phrase or extended private key
   * Add passphrase if used
   * Click **Save**

3. The private key will be created and stored securely in Vault
4. You can now create a Master Public Key if needed

Viewing Private Keys
--------------------

1. Go to **Accounting** → **Bitcoin** → **Key Management** → **Private Keys**
2. Click on any private key to view:

   * **Key Data**: XPRV and derived XPUB (click tabs to see)
   * **Account Public Keys**: List of account-level keys created from this private key
   * **Multisig Public Keys**: Multisig cosigner keys (if you have advanced permissions)

🏦 **Account Public Key Management**
====================================

Account public keys follow BIP44 standard (m/44'/0'/account') and are used for single-signature Bitcoin operations.

Creating Account Public Keys
-----------------------------

1. Open a private key record
2. Go to the **Account Public Keys** tab
3. Click **Create Account Public Key**
4. Configure the account:

   * **Account Index**: Choose account number (0, 1, 2, etc.)
   * **Auto-suggest**: Let the system suggest the next available account
   * **Partner Assignment**: Optionally assign to a business partner
   * **Name Suffix**: Add custom identifier

5. Click **Save** - the account key is created automatically
6. View the results:

   * **XPUB**: Extended public key for this account
   * **Sample Addresses**: Example addresses for verification
   * **Success Message**: Instructions for next steps

Using Account Public Keys
--------------------------

**For Receiving Payments**:

1. Open the created account public key
2. Go to **Derived Addresses** tab
3. Copy receive addresses (m/44'/0'/account'/0/x) for invoices/payments
4. Share with customers or use in payment systems

**For Payment Processing**:

1. Use the XPUB in external wallet software
2. Derive new addresses for each payment
3. Monitor transactions using the derivation path

🛡️ **Multisig Operations** (Advanced Users Only)
=================================================

Multisig functionality requires the "Bitcoin Advanced" user group.

Creating Multisig Public Keys
------------------------------

1. Open a private key record
2. Go to the **Multisig Public Keys** tab
3. Click **Create Multisig Public Key**
4. Configure the multisig setup:

   **Basic Settings**:
   
   * **Account Index**: Choose account number for this multisig setup
   * **Script Type**: Select multisig format:
     
     - **P2SH**: Legacy multisig (addresses start with '3')
     - **P2WSH**: Native SegWit multisig (addresses start with 'bc1')
     - **P2SH-P2WSH**: Wrapped SegWit multisig (addresses start with '3')
   
   * **Cosigner Index**: Your position in the multisig (0, 1, 2, etc.)

   **Optional Settings**:
   
   * **Multisig Wallet**: Associate with existing multisig wallet record
   * **Name Suffix**: Custom identifier for this key

5. Click **Save** - the multisig key is created automatically
6. Review the setup guide for next steps

Setting Up a Multisig Wallet
-----------------------------

**Step 1: Collect XPUBs**

1. Each cosigner creates their multisig public key using the same:
   
   * Account index (e.g., all use account 0)
   * Script type (e.g., all use P2WSH)
   * Different cosigner indices (0, 1, 2, etc.)

2. Exchange XPUBs securely between all cosigners

**Step 2: Create Wallet**

1. Use external wallet software (Electrum, Bitcoin Core, etc.)
2. Import all cosigner XPUBs
3. Configure m-of-n threshold (e.g., 2-of-3)
4. Verify first few addresses match across all cosigners

**Step 3: Test Setup**

1. Generate test addresses
2. Send small test transaction
3. Practice signing with multiple cosigners
4. Verify transaction broadcasts successfully

👥 **Partner Integration**
==========================

Assigning Keys to Partners
---------------------------

**During Key Creation**:

1. When creating account or multisig keys
2. Select partner in "Assign to Partner" field
3. Key will be associated with that partner's payment workflow

**After Key Creation**:

1. Open the public key record
2. Set the "Assigned Partner" field
3. Save the record

**Viewing Partner Bitcoin Data**:

1. Open any partner record
2. Go to the **Bitcoin** tab (if you have Bitcoin permissions)
3. View all Bitcoin wallets associated with this partner

📋 **Common Workflows**
=======================

Workflow 1: Single Customer Payment Setup
------------------------------------------

**Scenario**: You want unique receiving addresses for each customer

1. **Create Private Key**: Generate new key for receiving payments
2. **Create Account Keys**: One account per major customer

   * Account 0 → Customer A
   * Account 1 → Customer B
   * Account 2 → Customer C

3. **Generate Addresses**: For each customer account, derive receiving addresses
4. **Invoice Integration**: Use derived addresses in customer invoices
5. **Payment Monitoring**: Track payments to each customer's account path

Workflow 2: Partner Payment Processing
--------------------------------------

**Scenario**: Regular payments to vendor with enhanced privacy

1. **Get Vendor XPUB**: Request vendor's account-level XPUB for your payments
2. **Create Private Key**: For making payments to this vendor
3. **External Wallet**: Import your private key and vendor's XPUB
4. **Generate Addresses**: Derive new address for each payment
5. **Payment Process**: Send payments to unique addresses each time

Workflow 3: Multisig Treasury Setup
-----------------------------------

**Scenario**: Company treasury requiring multiple signatures

1. **Plan Setup**: Decide on m-of-n configuration (e.g., 2-of-3)
2. **Create Keys**: Each cosigner creates private key
3. **Generate Multisig Keys**: Each cosigner creates multisig public key

   * Same account index (e.g., 0)
   * Same script type (e.g., P2WSH)
   * Different cosigner indices (0, 1, 2)

4. **Exchange XPUBs**: Securely share XPUBs between cosigners
5. **Create Wallet**: Import all XPUBs into wallet software
6. **Test & Deploy**: Verify with small amounts before using for treasury

Workflow 4: Department Segregation
-----------------------------------

**Scenario**: Different Bitcoin accounts for different departments

1. **Create Master Key**: One private key for the organization
2. **Create Department Accounts**:

   * Account 0 → Sales Department
   * Account 1 → Marketing Department  
   * Account 2 → Operations Department
   * Account 3 → Executive Treasury

3. **Assign Partners**: Link department accounts to relevant partners
4. **Generate Addresses**: Each department gets their own address space
5. **Reporting**: Track activities by department using account paths

🔍 **Address Management**
=========================

Understanding Address Types
----------------------------

**Receive Addresses** (m/44'/0'/account'/0/index):

* Used for receiving payments
* Share these with customers/partners
* Each index generates a new address

**Change Addresses** (m/44'/0'/account'/1/index):

* Used internally for change outputs
* Not typically shared externally
* Automatically used by wallet software

Viewing Derived Addresses
--------------------------

1. Open any public key record
2. Go to the **Derived Addresses** tab
3. View sample addresses:

   * **Receive Addresses**: For customer payments
   * **Change Addresses**: For internal use

4. Copy addresses as needed for payment processing

🚨 **Security Best Practices**
==============================

Key Backup
-----------

* **Write Down Mnemonics**: Always backup mnemonic phrases offline
* **Secure Storage**: Store backups in secure, offline locations
* **Test Recovery**: Verify you can restore keys from backups

Access Control
--------------

* **User Groups**: Only grant Bitcoin permissions to authorized users
* **Vault Security**: Ensure Vault instance is properly secured
* **Network Security**: Use HTTPS for all Vault connections

Operational Security
--------------------

* **Test First**: Always test with small amounts before production use
* **Verify Addresses**: Double-check addresses before sending large payments
* **Monitor Access**: Review Vault access logs regularly
* **Update Regularly**: Keep Vault and Odoo updated with security patches

📞 **Troubleshooting**
======================

Common Issues
-------------

**"XPRV required" Error**:

* Check Vault connection status
* Verify environment variables (VAULT_ADDR, VAULT_TOKEN)
* Refresh vault status on private key record

**"Bitcoin menu not visible"**:

* Check user permissions
* Ensure user is in appropriate Bitcoin group
* Contact administrator for access

**"Invalid XPUB" Error**:

* Verify XPUB format is correct
* Check for copy/paste errors
* Ensure XPUB matches expected network (mainnet/testnet)

**Address Generation Fails**:

* Check public key has valid XPUB
* Verify Vault connectivity
* Check derivation parameters are valid

Getting Help
------------

1. **Check Logs**: Review Odoo logs for error details
2. **Vault Status**: Verify Vault connectivity and permissions
3. **User Groups**: Confirm proper user group assignments
4. **Documentation**: Refer to CONFIGURE.rst for setup issues

For advanced troubleshooting, check the Vault logs and Odoo server logs for detailed error messages.