# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import logging
import re

_logger = logging.getLogger(__name__)


class CryptoLightningScheduledPayment(models.Model):
    _name = 'crypto.lightning.scheduled.payment'
    _description = 'Lightning Scheduled Payment'
    _order = 'next_execution_date asc'
    _rec_name = 'display_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # Basic Information
    name = fields.Char(string='Schedule Name', required=True, tracking=True)
    address_id = fields.Many2one('crypto.lightning.address', string='Lightning Address', required=True, tracking=True)
    lsp_id = fields.Many2one('crypto.lightning.service.provider', string='Lightning Service Provider', required=True, tracking=True)

    # Amount Configuration
    amount_type = fields.Selection([
        ('fiat', 'Fixed Fiat Amount'),
        ('satoshi', 'Fixed Satoshi Amount')
    ], string='Amount Type', required=True, default='fiat', tracking=True)

    # Fiat amount fields
    amount_fiat = fields.Float(string='Fiat Amount', digits=(16, 2))
    currency_id = fields.Many2one('res.currency', string='Currency',
                                 default=lambda self: self.env.company.currency_id)

    # Satoshi amount field
    amount_satoshi = fields.Integer(string='Satoshi Amount')

    # Schedule Configuration - Cron expression only
    cron_expression = fields.Char(string='Cron Expression', required=True,
                                 help='Unix cron format: minute hour day month weekday\nExamples:\n* * * * * = every minute\n*/5 * * * * = every 5 minutes\n0 * * * * = every hour\n0 9 * * 1 = every Monday at 9 AM')
    cron_description = fields.Char(string='Schedule Description', compute='_compute_cron_description', store=False)

    # Date Management
    start_date = fields.Date(string='Start Date', required=True, default=fields.Date.today, tracking=True)
    end_date = fields.Date(string='End Date', help='Leave empty for indefinite schedule')
    next_execution_date = fields.Datetime(string='Next Execution', readonly=True, tracking=True)
    last_execution_date = fields.Datetime(string='Last Execution', readonly=True)

    # Status and Control
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', readonly=True, tracking=True)

    # Statistics
    total_executions = fields.Integer(string='Total Executions', readonly=True)
    successful_executions = fields.Integer(string='Successful Executions', readonly=True)
    failed_executions = fields.Integer(string='Failed Executions', readonly=True)
    last_execution_status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed')
    ], string='Last Status', readonly=True)

    # Related Payment Records
    payment_ids = fields.One2many('crypto.lightning.payment', 'scheduled_payment_id',
                                 string='Generated Payments', readonly=True)
    payment_count = fields.Integer(string='Payment Count', compute='_compute_payment_count')

    # Display
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('name', 'address_id', 'amount_type', 'amount_fiat', 'amount_satoshi', 'currency_id')
    def _compute_display_name(self):
        for record in self:
            if record.amount_type == 'fiat' and record.amount_fiat and record.currency_id:
                amount_str = f"{record.amount_fiat} {record.currency_id.name}"
            elif record.amount_type == 'satoshi' and record.amount_satoshi:
                amount_str = f"{record.amount_satoshi} sats"
            else:
                amount_str = "No amount"

            if record.address_id:
                address_short = record.address_id.address[:20] + ('...' if len(record.address_id.address) > 20 else '')
                record.display_name = f"{record.name or 'Scheduled Payment'}: {amount_str} to {address_short}"
            else:
                record.display_name = f"{record.name or 'Scheduled Payment'}: {amount_str}"

    @api.depends('payment_ids')
    def _compute_payment_count(self):
        for record in self:
            record.payment_count = len(record.payment_ids)

    @api.depends('cron_expression')
    def _compute_cron_description(self):
        for record in self:
            if record.cron_expression:
                record.cron_description = record._parse_cron_description(record.cron_expression)
            else:
                record.cron_description = "Not configured"

    @api.constrains('amount_fiat', 'amount_satoshi', 'amount_type')
    def _check_amount_configuration(self):
        for record in self:
            if record.amount_type == 'fiat':
                if not record.amount_fiat or record.amount_fiat <= 0:
                    raise ValidationError("Fiat amount must be greater than 0")
                if not record.currency_id:
                    raise ValidationError("Currency is required for fiat amounts")
            elif record.amount_type == 'satoshi':
                if not record.amount_satoshi or record.amount_satoshi <= 0:
                    raise ValidationError("Satoshi amount must be greater than 0")

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        for record in self:
            if record.end_date and record.start_date and record.end_date < record.start_date:
                raise ValidationError("End date must be after start date")

    @api.constrains('cron_expression')
    def _check_cron_expression(self):
        for record in self:
            if not record.cron_expression:
                raise ValidationError("Cron expression is required")
            if not record._validate_cron_expression(record.cron_expression):
                raise ValidationError("Invalid cron expression format. Use: minute hour day month weekday")

            # Warning for very frequent schedules
            if record.cron_expression in ["* * * * *"] or (record.cron_expression.startswith("*/") and
                                                          record.cron_expression.split()[0].endswith("1")):
                _logger.warning(f"High-frequency scheduled payment created: {record.cron_expression} for {record.name}")

    @api.onchange('cron_expression')
    def _onchange_cron_expression(self):
        # Trigger recomputation of description
        self._compute_cron_description()

    @api.onchange('amount_type')
    def _onchange_amount_type(self):
        if self.amount_type == 'fiat':
            self.amount_satoshi = 0
        else:
            self.amount_fiat = 0.0

    def _validate_cron_expression(self, cron_expr):
        """Validate cron expression format"""
        if not cron_expr:
            return False

        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return False

        # Basic validation for each field
        patterns = [
            r'^(\*|([0-5]?\d)(,([0-5]?\d))*|([0-5]?\d)-([0-5]?\d)|\*/([1-9]\d*))$',  # minute (0-59)
            r'^(\*|([01]?\d|2[0-3])(,([01]?\d|2[0-3]))*|([01]?\d|2[0-3])-([01]?\d|2[0-3])|\*/([1-9]\d*))$',  # hour (0-23)
            r'^(\*|([0-2]?\d|3[01])(,([0-2]?\d|3[01]))*|([0-2]?\d|3[01])-([0-2]?\d|3[01])|\*/([1-9]\d*))$',  # day (1-31)
            r'^(\*|([0]?\d|1[0-2])(,([0]?\d|1[0-2]))*|([0]?\d|1[0-2])-([0]?\d|1[0-2])|\*/([1-9]\d*))$',  # month (1-12)
            r'^(\*|[0-6](,[0-6])*|[0-6]-[0-6]|\*/([1-7]))$'  # weekday (0-6)
        ]

        for i, part in enumerate(parts):
            if not re.match(patterns[i], part):
                return False

        return True

    def _parse_cron_description(self, cron_expr):
        """Parse cron expression into human-readable description"""
        if not cron_expr:
            return "Invalid cron expression"

        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return "Invalid cron format"

        minute, hour, day, month, weekday = parts

        # Simple cases
        if cron_expr == "* * * * *":
            return "Every minute"
        elif cron_expr == "*/5 * * * *":
            return "Every 5 minutes"
        elif cron_expr == "0 * * * *":
            return "Every hour"
        elif cron_expr == "0 0 * * *":
            return "Every day at midnight"
        elif cron_expr == "0 9 * * 1":
            return "Every Monday at 9:00 AM"
        elif minute.startswith("*/"):
            interval = minute[2:]
            return f"Every {interval} minutes"
        else:
            return f"Custom schedule: {cron_expr}"

    def action_activate(self):
        """Activate the scheduled payment"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError("Only draft schedules can be activated")

        # Calculate next execution date
        self._calculate_next_execution()

        self.write({
            'state': 'active',
            'next_execution_date': self.next_execution_date
        })

        self.message_post(body="Scheduled payment activated")

    def action_pause(self):
        """Pause the scheduled payment"""
        self.ensure_one()
        if self.state != 'active':
            raise UserError("Only active schedules can be paused")

        self.write({'state': 'paused'})
        self.message_post(body="Scheduled payment paused")

    def action_resume(self):
        """Resume the scheduled payment"""
        self.ensure_one()
        if self.state != 'paused':
            raise UserError("Only paused schedules can be resumed")

        # Recalculate next execution from current time
        self._calculate_next_execution()

        self.write({
            'state': 'active',
            'next_execution_date': self.next_execution_date
        })

        self.message_post(body="Scheduled payment resumed")

    def action_cancel(self):
        """Cancel the scheduled payment"""
        self.ensure_one()
        if self.state in ['completed', 'cancelled']:
            raise UserError("Schedule is already completed or cancelled")

        self.write({'state': 'cancelled'})
        self.message_post(body="Scheduled payment cancelled")

    def action_execute_now(self):
        """Manually execute the payment now"""
        self.ensure_one()
        if self.state not in ['active', 'paused']:
            raise UserError("Only active or paused schedules can be executed")

        return self._execute_payment()

    def action_view_payments(self):
        """View generated payments"""
        self.ensure_one()
        return {
            'name': 'Generated Payments',
            'type': 'ir.actions.act_window',
            'res_model': 'crypto.lightning.payment',
            'view_mode': 'tree,form',
            'domain': [('scheduled_payment_id', '=', self.id)],
            'context': {'default_scheduled_payment_id': self.id}
        }

    def _calculate_next_execution(self):
        """Calculate the next execution date based on cron expression"""
        self.ensure_one()

        current_datetime = fields.Datetime.now()
        next_date = self._calculate_cron_next_execution(current_datetime)

        # Check if we've passed the end date
        if self.end_date and next_date and next_date.date() > self.end_date:
            self.next_execution_date = False
            if self.state == 'active':
                self.state = 'completed'
        else:
            self.next_execution_date = next_date

    def _calculate_cron_next_execution(self, current_datetime):
        """Calculate next execution for cron expression"""
        if not self.cron_expression:
            return False

        parts = self.cron_expression.strip().split()
        if len(parts) != 5:
            return False

        minute, hour, day, month, weekday = parts

        # Handle simple minute intervals (*/N format)
        if minute.startswith("*/") and hour == "*" and day == "*" and month == "*" and weekday == "*":
            try:
                interval = int(minute[2:])
                base_datetime = self.last_execution_date if self.last_execution_date else current_datetime
                next_date = base_datetime + timedelta(minutes=interval)

                # Ensure next execution is in the future
                if next_date <= current_datetime:
                    next_date = current_datetime + timedelta(minutes=interval)

                return next_date
            except ValueError:
                return False

        # Handle every minute (* * * * *)
        if self.cron_expression == "* * * * *":
            base_datetime = self.last_execution_date if self.last_execution_date else current_datetime
            next_date = base_datetime + timedelta(minutes=1)

            if next_date <= current_datetime:
                next_date = current_datetime + timedelta(minutes=1)

            return next_date

        # Handle hourly (0 * * * *)
        if minute == "0" and hour == "*" and day == "*" and month == "*" and weekday == "*":
            next_date = current_datetime.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            return next_date

        # Handle daily (0 0 * * *)
        if minute == "0" and hour == "0" and day == "*" and month == "*" and weekday == "*":
            next_date = current_datetime.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            return next_date

        # For complex cron expressions, fall back to simple calculation
        # TODO: Implement full cron parsing or integrate croniter library
        _logger.warning(f"Complex cron expression not fully supported: {self.cron_expression}")
        return current_datetime + timedelta(minutes=1)

    def _execute_payment(self):
        """Execute the scheduled payment"""
        self.ensure_one()

        try:
            # Get company currency and BTC price (needed for both calculation types)
            company_currency = self.env.company.currency_id
            btc_price = self.env['crypto.btc.price.service'].get_btc_price(company_currency.name)

            # Determine amount based on type
            if self.amount_type == 'fiat':
                amount = self.amount_fiat
                currency = self.currency_id
                # Convert fiat amount to satoshis
                base_amount = currency._convert(amount, company_currency, self.env.company, fields.Date.today())
                satoshis = int((base_amount / btc_price) * 100000000)
            else:
                # For satoshi amounts, we need to convert to fiat for the payment model
                satoshis = self.amount_satoshi
                amount = (self.amount_satoshi / 100000000) * btc_price
                currency = company_currency

            # Create payment record
            payment_vals = {
                'address_id': self.address_id.id,
                'amount': amount,
                'currency_id': currency.id,
                'satoshis': satoshis,
                'lsp_id': self.lsp_id.id,
                'scheduled_payment_id': self.id,
                'payment_status': 'draft',
            }

            payment = self.env['crypto.lightning.payment'].create(payment_vals)

            # Execute the payment
            result = payment.action_pay_now()

            # Update execution statistics
            self.write({
                'total_executions': self.total_executions + 1,
                'last_execution_date': fields.Datetime.now()
            })

            # Calculate next execution
            self._calculate_next_execution()

            _logger.info(f"Scheduled payment {self.id} executed successfully, created payment {payment.id}")

            return {
                'type': 'ir.actions.act_window',
                'name': 'Executed Payment',
                'res_model': 'crypto.lightning.payment',
                'res_id': payment.id,
                'view_mode': 'form',
                'target': 'current',
            }

        except Exception as e:
            _logger.error(f"Scheduled payment {self.id} execution failed: {str(e)}")

            self.write({
                'total_executions': self.total_executions + 1,
                'failed_executions': self.failed_executions + 1,
                'last_execution_status': 'failed',
                'last_execution_date': fields.Datetime.now()
            })

            # Calculate next execution even after failure
            self._calculate_next_execution()

            # Post message about failure
            self.message_post(
                body=f"Scheduled payment execution failed: {str(e)}",
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )

            raise UserError(f"Payment execution failed: {str(e)}")

    @api.model
    def _cron_execute_scheduled_payments(self):
        """Cron job to execute scheduled payments"""
        current_time = fields.Datetime.now()

        # Find all active scheduled payments due for execution
        scheduled_payments = self.search([
            ('state', '=', 'active'),
            ('next_execution_date', '<=', current_time),
            ('next_execution_date', '!=', False)
        ])

        _logger.info(f"Found {len(scheduled_payments)} scheduled payments due for execution")

        for schedule in scheduled_payments:
            try:
                schedule._execute_payment()
                schedule.write({
                    'successful_executions': schedule.successful_executions + 1,
                    'last_execution_status': 'success'
                })
            except Exception as e:
                _logger.error(f"Failed to execute scheduled payment {schedule.id}: {str(e)}")
                schedule.write({
                    'failed_executions': schedule.failed_executions + 1,
                    'last_execution_status': 'failed'
                })
                continue