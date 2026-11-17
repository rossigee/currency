# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{
    "name": "Vault Connector",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "author": "Ross Golder, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/currency",
    "summary": "Secure connection to Vault for secret storage",
    "license": "AGPL-3",
    "depends": [
        "base",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "data": [
        "security/vault_connector_security.xml",
        "security/ir.model.access.csv",
    ],
    "demo": [],
    "installable": True,
    "auto_install": False,
    "application": False,  # This is a utility module, not a standalone app
}
