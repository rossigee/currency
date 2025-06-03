# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "Account Cryptocurrency Addresses",
    "version": "16.0.1.0.3",
    "category": "Account",
    "author": "Ross Golder, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/currency",
    "summary": "Track Cryptocurrency Wallets and Addresses",
    "description": """
        This module adds the ability to track cryptocurrency wallets and address information.
    """,
    "license": "AGPL-3",
    "depends": [
        "base",
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/crypto_bitcoin_address_views.xml",
        "views/crypto_bitcoin_transaction_views.xml",
        "views/crypto_bitcoin_wallet_views.xml",
        "views/crypto_lightning_address_views.xml",
        "views/crypto_lightning_payment_form.xml",
        "views/crypto_lightning_service_provider.xml",
        "views/menu.xml",
        "views/res_partner_bitcoin_tab_view.xml",
        "views/res_partner_lightning_tab_view.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
}
