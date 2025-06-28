# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "Account Management Tools for Bitcoin",
    "version": "16.0.2.0.1",
    "category": "Account",
    "author": "Ross Golder, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/currency",
    "summary": "Tracks Bitcoin wallets, addresses, keys etc",
    "description": """
        This module adds the ability to manage Bitcoin-related data.
    """,
    "license": "AGPL-3",
    "depends": [
        "base",
        "account",
        "vault_connector",
        "queue_job",
    ],
    "external_dependencies": {
        "python": ["mnemonic", "embit"],
    },
    "data": [
        "security/res_groups.xml",
        "security/ir.model.access.csv",
        "views/wizard_bitcoin_xpub.xml",
        "views/wizard_derive_addresses.xml",
        "views/wizard_create_private_key.xml",
        "views/wizard_create_account_public_key.xml",
        "views/wizard_create_multisig_public_key.xml",
        "views/wizard_create_transaction.xml",
        "views/wizard_import_psbt.xml",
        "views/wizard_import_bsms.xml",
        "views/crypto_bitcoin_public_key_views.xml",
        "views/crypto_bitcoin_private_key_views.xml",
        "views/crypto_bitcoin_private_key_actions.xml",
        "views/crypto_bitcoin_address_views.xml",
        "views/crypto_bitcoin_multisig_wallet_views.xml",
        "views/crypto_bitcoin_transaction_views.xml",
        "views/crypto_bitcoin_transaction_fetcher_views.xml",
        "views/crypto_bitcoin_wallet_views.xml",
        "views/bitcoin_settings_views.xml",
        "views/res_config_settings_views.xml",
        "views/queue_job_views.xml",
        "views/menu.xml",
        "views/res_partner_bitcoin_tab_view.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
}
