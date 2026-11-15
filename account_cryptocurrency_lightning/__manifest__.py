# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "Account Management Tools for Lightning",
    "version": "17.0.2.0.2",
    "category": "Account",
    "author": "Ross Golder, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/currency",
    "summary": "Lightning Network payment processing with LND integration",
    "description": """
        Lightning Network payment module for Odoo 16.

        Features:
        * LND node integration with macaroon authentication
        * Lightning address and payment management
        * Background job payment processing
        * Real-time BTC pricing and QR code generation
        * Complete audit trail and state tracking
        * Secure credential storage via vault connector
    """,
    "license": "AGPL-3",
    "depends": [
        "base",
        "account",
        "mail",
        "vault_connector",
        "queue_job",
    ],
    "external_dependencies": {
        "python": ["requests", "qrcode", "cron-converter", "cron-descriptor"],
    },
    "data": [
        "security/res_groups.xml",
        "security/ir.model.access.csv",
        "data/crypto_btc_price_service_data.xml",
        "views/crypto_lightning_address_views.xml",
        "views/crypto_lightning_payment_form.xml",
        "views/crypto_lightning_payment_views.xml",
        "views/crypto_lightning_scheduled_payment_views.xml",
        "views/crypto_btc_price_service_views.xml",
        "views/crypto_lightning_service_provider.xml",
        "views/menu.xml",
        "views/res_partner_lightning_tab_view.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
}
