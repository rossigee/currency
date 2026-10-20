=====================================
Bitcoin Operations for Odoo
=====================================

A comprehensive Bitcoin key management and operations module for Odoo that enables secure handling of Bitcoin private keys, public keys, addresses, and multisig wallets within your business workflow.

🚀 **Key Features**
===================

Private Key Management
----------------------
* **Secure Key Generation**: Generate new BIP39 mnemonic-based private keys with optional passphrases
* **Key Import**: Import existing private keys from mnemonic phrases or extended private keys (XPRV)
* **Vault Integration**: All sensitive key material is stored securely in HashiCorp Vault/OpenBao
* **Access Control**: Role-based permissions for basic users vs advanced operations

Public Key Derivation
----------------------
* **BIP44 Account Keys**: Create account-level public keys for standard single-signature operations
* **BIP48 Multisig Keys**: Generate cosigner keys for multisig wallet setups
* **Multiple Script Types**: Support for P2SH, P2WSH, and P2SH-P2WSH multisig formats
* **Address Generation**: Derive receive and change addresses following Bitcoin standards
* **Unique Fingerprints**: Each derived key has its own unique fingerprint for identification

Multisig Operations
-------------------
* **Advanced Security Group**: Multisig features restricted to authorized users
* **Cosigner Management**: Track multiple cosigners and their key contributions
* **Script Type Support**: Legacy (P2SH), Native SegWit (P2WSH), and Wrapped SegWit (P2SH-P2WSH)
* **Wallet Integration**: Associate multisig keys with wallet records for organization

Partner & Business Integration
------------------------------
* **Partner Assignment**: Link Bitcoin accounts and keys to business partners
* **Payment Processing**: Organize keys for different payment workflows
* **Account Segregation**: Use different accounts for different business purposes
* **Audit Trail**: Complete history of key generation and usage

🔒 **Security & Architecture**
===============================

Secure Storage
--------------
* **Vault Backend**: All private keys and XPUBs stored in external Vault instance
* **Database Tokenization**: Only UUID tokens stored in Odoo database
* **No Plain Text**: Sensitive material never stored unencrypted in Odoo
* **Access Logging**: Vault provides audit trails for key access

Permission System
-----------------
* **Bitcoin User**: Basic Bitcoin operations (private keys, accounts, addresses)
* **Bitcoin Advanced**: Multisig operations and complex derivations  
* **Bitcoin Manager**: Full access including system configuration
* **Menu Restrictions**: Bitcoin functionality hidden from unauthorized users

Standards Compliance
--------------------
* **BIP32**: Hierarchical Deterministic key derivation
* **BIP39**: Mnemonic phrase generation and validation
* **BIP44**: Standard account structure (m/44'/0'/account'/change/index)
* **BIP48**: Multisig derivation paths (m/48'/0'/account'/script_type'/change/index)
* **Bech32**: Native SegWit address encoding

🏢 **Business Use Cases**
==========================

Treasury Management
-------------------
* Generate dedicated accounts for different business units
* Create multisig setups for enhanced security controls
* Organize payment addresses by partner relationships
* Maintain audit trails for compliance

Payment Processing
------------------
* Provide unique receiving addresses per customer/invoice
* Generate payment addresses from partner-specific accounts
* Support both single-sig and multisig payment workflows
* Integrate with existing accounting processes

Partnership & Cosigning
------------------------
* Exchange XPUBs with business partners for multisig setups
* Create joint custody arrangements with multiple signers
* Manage escrow and custody services
* Support complex approval workflows

⚠️ **Security Warnings**
=========================

Production Readiness
--------------------
**BETA SOFTWARE**: This module is in active development and should be thoroughly tested before production use.

Backup Requirements
-------------------
* **Mnemonic Phrases**: Always securely backup your mnemonic phrases offline
* **Vault Data**: Ensure your Vault instance is properly backed up and replicated
* **Access Credentials**: Securely manage Vault tokens and access credentials

Network Security
-----------------
* **Vault Connection**: Use HTTPS and secure network connections to Vault
* **Access Controls**: Implement proper network segmentation and firewalls
* **Monitoring**: Monitor access patterns and implement alerting

📋 **Requirements**
===================

Technical Prerequisites
-----------------------
* **Odoo 16.0+**: Compatible with Odoo 16 and later versions
* **Python Libraries**: `mnemonic` package for BIP39 support
* **HashiCorp Vault**: External Vault or OpenBao instance for secure storage
* **Network Access**: HTTPS connectivity between Odoo and Vault

User Knowledge
--------------
* **Bitcoin Basics**: Understanding of Bitcoin addresses, transactions, and keys
* **BIP Standards**: Familiarity with BIP32/39/44/48 derivation standards
* **Multisig Concepts**: Knowledge of multisig wallet operation (for advanced features)
* **Security Practices**: Understanding of cryptocurrency security best practices

🎯 **Getting Started**
======================

See the CONFIGURE.rst file for detailed installation and setup instructions.
See the USAGE.rst file for step-by-step usage examples and workflows.

The module integrates into Odoo's Accounting menu and provides intuitive wizards for key generation, account creation, and multisig setup.

📞 **Support & Contributing**
=============================

This module is actively developed and maintained. See CONTRIBUTORS.rst for contributor information and guidelines.

For issues, feature requests, or contributions, please follow standard Odoo Community Association practices.