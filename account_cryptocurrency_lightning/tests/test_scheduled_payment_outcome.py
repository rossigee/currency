# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from ..models import lnd_rest_client

BTC_PRICE = 50000.0


@tagged('post_install', '-at_install')
class TestScheduledPaymentOutcome(TransactionCase):
    """Scheduled payment counters must reflect the final payment outcome"""

    def setUp(self):
        super().setUp()
        self.lsp = self.env['crypto.lightning.service.provider'].create({
            'name': 'Test LND',
            'rest_url': 'https://lnd.example.test:8080',
            'token_uuid': str(uuid.uuid4()),
        })
        self.address = self.env['crypto.lightning.address'].create({
            'address': 'sam@example.test',
        })
        # No macaroon in Vault unless a test provides one
        self._patch_model('crypto.lightning.service.provider', '_get_data_from_vault',
                          return_value={'macaroon': '', 'status': 'no macaroon'})

    def _patch_model(self, model_name, attr, **kwargs):
        patcher = patch.object(self.env.registry[model_name], attr, **kwargs)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def _create_schedule(self):
        schedule = self.env['crypto.lightning.scheduled.payment'].create({
            'name': 'Pocket money',
            'address_id': self.address.id,
            'lsp_id': self.lsp.id,
            'amount_type': 'satoshi',
            'amount_satoshi': 1000,
            'cron_expression': '0 9 * * *',
        })
        schedule.write({
            'state': 'active',
            'next_execution_date': fields.Datetime.now() - timedelta(minutes=5),
        })
        return schedule

    def _create_payment(self, schedule):
        return self.env['crypto.lightning.payment'].create({
            'address_id': self.address.id,
            'amount': 1.0,
            'currency_id': self.env.company.currency_id.id,
            'satoshis': 1000,
            'lsp_id': self.lsp.id,
            'scheduled_payment_id': schedule.id,
            'payment_status': 'pending',
            'ln_payment_ref': 'lnbc10u1test',
        })

    def _run_cron(self):
        self.env['crypto.lightning.scheduled.payment']._cron_execute_scheduled_payments()

    def test_cron_enqueued_run_not_counted_as_success(self):
        """A run that only enqueues the payment job must not count as success"""
        self._patch_model('crypto.lightning.scheduled.payment', '_execute_payment',
                          return_value=None)
        schedule = self._create_schedule()

        self._run_cron()

        self.assertEqual(schedule.successful_executions, 0)
        self.assertEqual(schedule.failed_executions, 0)
        self.assertFalse(schedule.last_execution_status)

    def test_cron_failure_before_enqueue_counted_once(self):
        """A failure raised before the job is enqueued is counted exactly once"""
        self._patch_model('crypto.btc.price.service', 'get_btc_price', return_value=BTC_PRICE)
        self._patch_model('crypto.lightning.payment', 'action_pay_now',
                          side_effect=UserError('LND unreachable'))
        schedule = self._create_schedule()

        self._run_cron()

        self.assertEqual(schedule.failed_executions, 1)
        self.assertEqual(schedule.successful_executions, 0)
        self.assertEqual(schedule.last_execution_status, 'failed')

    def test_record_execution_outcome_success(self):
        schedule = self._create_schedule()

        schedule._record_execution_outcome(True)

        self.assertEqual(schedule.successful_executions, 1)
        self.assertEqual(schedule.failed_executions, 0)
        self.assertEqual(schedule.last_execution_status, 'success')

    def test_record_execution_outcome_failure(self):
        schedule = self._create_schedule()

        schedule._record_execution_outcome(False)

        self.assertEqual(schedule.successful_executions, 0)
        self.assertEqual(schedule.failed_executions, 1)
        self.assertEqual(schedule.last_execution_status, 'failed')

    def test_job_without_macaroon_records_failed_run(self):
        """The payment job records a failed run on the schedule when Vault has no macaroon"""
        schedule = self._create_schedule()
        payment = self._create_payment(schedule)

        payment._process_lightning_payment()

        self.assertEqual(payment.payment_status, 'failed')
        self.assertEqual(payment.payment_error, 'No macaroon available for service provider')
        self.assertEqual(schedule.failed_executions, 1)
        self.assertEqual(schedule.successful_executions, 0)
        self.assertEqual(schedule.last_execution_status, 'failed')

    def test_job_success_records_successful_run(self):
        """The payment job records a successful run on the schedule when LND pays"""
        self._patch_model('crypto.lightning.service.provider', '_get_data_from_vault',
                          return_value={'macaroon': '0201', 'status': 'ok'})
        client = MagicMock()
        client.decode_payment_request.return_value = {
            'destination': 'node',
            'num_satoshis': '1000',
            'timestamp': '1',
            'expiry': '3600',
            'description': '',
            'description_hash': '',
            'payment_hash': 'hash',
            'cltv_expiry': '40',
        }
        client.pay_invoice.return_value = {
            'payment_hash': 'hash',
            'payment_preimage': 'preimage',
            'payment_route': {'total_fees': '1', 'total_time_lock': '10', 'hops': [{}]},
        }
        patcher = patch.object(lnd_rest_client, 'LndRestClient', return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        schedule = self._create_schedule()
        payment = self._create_payment(schedule)

        payment._process_lightning_payment()

        self.assertEqual(payment.payment_status, 'success')
        self.assertEqual(schedule.successful_executions, 1)
        self.assertEqual(schedule.failed_executions, 0)
        self.assertEqual(schedule.last_execution_status, 'success')

    def test_job_without_schedule_is_unaffected(self):
        """A payment created outside a schedule has no schedule to update"""
        payment = self._create_payment(self.env['crypto.lightning.scheduled.payment'])
        payment.scheduled_payment_id = False

        payment._process_lightning_payment()

        self.assertEqual(payment.payment_status, 'failed')
