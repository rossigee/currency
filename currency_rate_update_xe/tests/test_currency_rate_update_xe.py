# Copyright 2023 Tecnativa - Ernesto Tejeda
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from unittest.mock import MagicMock, patch

import requests
from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import common

PROVIDER_MODULE = (
    "odoo.addons.currency_rate_update_xe.models.res_currency_rate_provider_XE"
)

RATES_PAGE = b"""<html><body><div id="table-section"><table><tbody>
<tr><th>USD</th><td>1.00</td><td>1.10</td></tr>
<tr><th>EUR</th><td>0.91</td><td>1.00</td></tr>
<tr><th>JOD</th><td>0.70</td><td>0.71</td></tr>
</tbody></table></div></body></html>"""

ERROR_PAGE = b"<html><body>ERROR: The request could not be satisfied</body></html>"


class TestResCurrencyRateProviderXE(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.Company = cls.env["res.company"]
        cls.CurrencyRate = cls.env["res.currency.rate"]
        cls.CurrencyRateProvider = cls.env["res.currency.rate.provider"]

        cls.today = fields.Date.today()
        cls.eur_currency = cls.env.ref("base.EUR")
        cls.usd_currency = cls.env.ref("base.USD")
        cls.company = cls.Company.create(
            {"name": "Test company", "currency_id": cls.eur_currency.id}
        )
        cls.env.user.company_ids += self.company
        cls.env.company = cls.company
        cls.xe_provider = cls.CurrencyRateProvider.create(
            {
                "service": "XE",
                "currency_ids": [
                    (4, cls.usd_currency.id),
                    (4, cls.eur_currency.id),
                ],
            }
        )
        cls.CurrencyRate.search([]).unlink()

    def _mock_xe_response(self, status_code=200, content=RATES_PAGE):
        """Stub the HTTP call so the tests do not depend on xe.com."""
        response = MagicMock(status_code=status_code, content=content)
        if status_code >= 400:
            response.raise_for_status.side_effect = requests.HTTPError(
                f"{status_code} Error", response=response
            )
        else:
            response.raise_for_status.return_value = None
        patcher = patch(f"{PROVIDER_MODULE}.requests.request", return_value=response)
        self.addCleanup(patcher.stop)
        return patcher.start()

    @freeze_time("2026-10-16")
    def test_cron(self):
        self._mock_xe_response()
        self.xe_provider._scheduled_update()
        rates = self.CurrencyRate.search([])
        self.assertEqual(len(rates), 1)
        self.assertEqual(rates.currency_id, self.usd_currency)

    @freeze_time("2026-10-19")
    def test_wizard(self):
        self._mock_xe_response()
        wizard = (
            self.env["res.currency.rate.update.wizard"]
            .with_context(default_provider_ids=[(6, False, self.xe_provider.ids)])
            .create({})
        )
        wizard.action_update()
        rates = self.CurrencyRate.search([])
        self.assertEqual(len(rates), 1)
        self.assertEqual(rates.currency_id, self.usd_currency)

    @freeze_time("2026-10-19")
    def test_wizard_jod(self):
        self._mock_xe_response()
        jod_currency = self.env.ref("base.JOD")
        jod_currency.active = True
        self.xe_provider.write(
            {
                "currency_ids": [Command.set([jod_currency.id])],
            }
        )
        wizard = (
            self.env["res.currency.rate.update.wizard"]
            .with_context(default_provider_ids=[(6, False, self.xe_provider.ids)])
            .create(
                {
                    "date_from": "2026-10-15",
                    "date_to": "2026-10-16",
                }
            )
        )
        wizard.action_update()
        self.assertEqual(len(jod_currency.rate_ids), 2)
        self.assertIn(
            fields.Date.from_string("2026-10-15"), jod_currency.rate_ids.mapped("name")
        )
        self.assertIn(
            fields.Date.from_string("2026-10-16"), jod_currency.rate_ids.mapped("name")
        )

    def test_http_error_raises(self):
        self._mock_xe_response(status_code=403, content=ERROR_PAGE)
        with self.assertRaisesRegex(UserError, "HTTP 403"):
            self.xe_provider._obtain_rates(
                "EUR", ["USD", "EUR"], self.today, self.today
            )

    def test_cron_http_error_is_reported(self):
        self._mock_xe_response(status_code=403, content=ERROR_PAGE)
        self.xe_provider._scheduled_update()
        self.assertFalse(self.CurrencyRate.search([]))
        self.assertIn(
            "Currency Rate Provider Failure",
            self.xe_provider.message_ids.mapped("subject"),
        )
