# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "Account Management Tools for Lightning",
    "version": "16.0.1.0.4",
    "category": "Account",
    "author": "Ross Golder, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/currency",
    "summary": "Tracks Lightning wallets, addresses, keys etc",
    "description": """
        This module adds the ability to manage Lightning-related data.
    """,
    "license": "AGPL-3",
    "depends": [
        "base",
        "account",
        "vault_connector",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.model.access.csv",
        "views/crypto_lightning_address_views.xml",
        "views/crypto_lightning_payment_form.xml",
        "views/crypto_lightning_service_provider.xml",
        "views/menu.xml",
        "views/res_partner_lightning_tab_view.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
}
