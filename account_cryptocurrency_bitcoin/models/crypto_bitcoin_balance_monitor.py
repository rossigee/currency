# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging
from datetime import datetime, timedelta
from decimal import Decimal

_logger = logging.getLogger(__name__)

class CryptoBitcoinBalanceMonitor(models.Model):
    _name = 'crypto.bitcoin.balance.monitor'
    _description = 'Bitcoin Balance Monitor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    _order = 'priority desc, last_alert_date desc'
    
    name = fields.Char(string='Monitor Name', required=True, tracking=True)
    multisig_wallet_id = fields.Many2one('crypto.bitcoin.multisig.wallet', string='Multisig Wallet', 
                                        required=True, ondelete='cascade')
    
    # Monitoring configuration
    active = fields.Boolean(string='Active', default=True, tracking=True)
    monitor_type = fields.Selection([
        ('threshold', 'Balance Thresholds'),
        ('change', 'Balance Changes'),
        ('velocity', 'Spending Velocity'),
        ('security', 'Security Events')
    ], string='Monitor Type', required=True, default='threshold')
    
    priority = fields.Selection([
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical')
    ], string='Priority', default='medium', tracking=True)
    
    # Balance thresholds (in BTC)
    low_threshold = fields.Float(string='Low Balance Threshold (BTC)', digits=(16, 8),
                                help="Alert when balance drops below this amount")
    high_threshold = fields.Float(string='High Balance Threshold (BTC)', digits=(16, 8),
                                 help="Alert when balance exceeds this amount")
    critical_threshold = fields.Float(string='Critical Threshold (BTC)', digits=(16, 8),
                                    help="Critical alert threshold")
    
    # Change monitoring
    change_threshold_percent = fields.Float(string='Change Threshold (%)', default=10.0,
                                          help="Alert on X% balance change")
    change_threshold_absolute = fields.Float(string='Absolute Change Threshold (BTC)', digits=(16, 8),
                                           help="Alert on absolute BTC amount change")
    
    # Velocity monitoring (spending limits)
    velocity_period_hours = fields.Integer(string='Velocity Period (Hours)', default=24)
    velocity_limit_btc = fields.Float(string='Velocity Limit (BTC)', digits=(16, 8),
                                    help="Maximum spending in the specified period")
    
    # Current state
    current_balance = fields.Float(string='Current Balance (BTC)', digits=(16, 8), readonly=True)
    previous_balance = fields.Float(string='Previous Balance (BTC)', digits=(16, 8), readonly=True)
    last_check_date = fields.Datetime(string='Last Check Date', readonly=True)
    last_alert_date = fields.Datetime(string='Last Alert Date', readonly=True)
    
    # Alert configuration
    notify_users_ids = fields.Many2many('res.users', string='Notify Users',
                                       help="Users to notify when alerts are triggered")
    notify_emails = fields.Text(string='Additional Email Addresses',
                               help="Comma-separated list of additional email addresses")
    email_template_id = fields.Many2one('mail.template', string='Email Template',
                                       domain="[('model', '=', 'crypto.bitcoin.balance.monitor')]")
    
    # Alert frequency control
    alert_frequency_hours = fields.Integer(string='Alert Frequency (Hours)', default=4,
                                         help="Minimum hours between repeat alerts for same condition")
    max_alerts_per_day = fields.Integer(string='Max Alerts Per Day', default=6)
    alerts_sent_today = fields.Integer(string='Alerts Sent Today', readonly=True)
    
    # Historical tracking
    balance_history_ids = fields.One2many('crypto.bitcoin.balance.history', 'monitor_id',
                                         string='Balance History')
    alert_history_ids = fields.One2many('crypto.bitcoin.balance.alert', 'monitor_id',
                                       string='Alert History')
    
    # Statistics
    total_alerts = fields.Integer(string='Total Alerts', compute='_compute_stats', store=True)
    avg_balance_24h = fields.Float(string='24h Average Balance', compute='_compute_stats', store=True)
    balance_trend = fields.Selection([
        ('increasing', 'Increasing'),
        ('stable', 'Stable'),
        ('decreasing', 'Decreasing')
    ], string='Balance Trend', compute='_compute_stats', store=True)
    
    @api.depends('alert_history_ids', 'balance_history_ids')
    def _compute_stats(self):
        for record in self:
            # Total alerts
            record.total_alerts = len(record.alert_history_ids)
            
            # 24h average balance
            yesterday = datetime.now() - timedelta(hours=24)
            recent_balances = record.balance_history_ids.filtered(
                lambda h: h.check_date >= yesterday
            )
            if recent_balances:
                record.avg_balance_24h = sum(recent_balances.mapped('balance')) / len(recent_balances)
            else:
                record.avg_balance_24h = record.current_balance
            
            # Balance trend
            if len(recent_balances) >= 2:
                sorted_balances = recent_balances.sorted('check_date')
                first_balance = sorted_balances[0].balance
                last_balance = sorted_balances[-1].balance
                change_percent = ((last_balance - first_balance) / first_balance * 100) if first_balance > 0 else 0
                
                if change_percent > 5:
                    record.balance_trend = 'increasing'
                elif change_percent < -5:
                    record.balance_trend = 'decreasing'
                else:
                    record.balance_trend = 'stable'
            else:
                record.balance_trend = 'stable'
    
    @api.constrains('low_threshold', 'high_threshold', 'critical_threshold')
    def _check_thresholds(self):
        for record in self:
            if record.low_threshold and record.high_threshold:
                if record.low_threshold >= record.high_threshold:
                    raise ValidationError("Low threshold must be less than high threshold")
            
            if record.critical_threshold and record.low_threshold:
                if record.critical_threshold >= record.low_threshold:
                    raise ValidationError("Critical threshold must be less than low threshold")
    
    def action_check_balance_now(self):
        """Manually trigger balance check"""
        self.ensure_one()
        self._check_wallet_balance()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Balance Check Complete',
                'message': f'Current balance: {self.current_balance:.8f} BTC',
                'type': 'success'
            }
        }
    
    def _check_wallet_balance(self):
        """Check the balance of the associated multisig wallet"""
        self.ensure_one()
        
        if not self.active:
            return
        
        try:
            # Get current balance by checking all derived addresses
            wallet = self.multisig_wallet_id
            if not wallet.is_complete:
                _logger.warning(f"Cannot check balance for incomplete wallet {wallet.name}")
                return
            
            total_balance = 0.0
            
            # Check balance across all known addresses
            # This could be optimized by using address derivation and checking each address
            addresses_to_check = self._get_wallet_addresses()
            
            for address in addresses_to_check:
                try:
                    # Use existing transaction fetcher to get balance
                    fetcher = self.env['crypto.bitcoin.transaction.fetcher']
                    balance_info = fetcher.get_address_balance(address, wallet.network or 'mainnet')
                    total_balance += balance_info.get('balance', 0.0)
                except Exception as e:
                    _logger.warning(f"Failed to get balance for address {address}: {str(e)}")
                    continue
            
            # Store previous balance before updating
            self.previous_balance = self.current_balance
            self.current_balance = total_balance
            self.last_check_date = fields.Datetime.now()
            
            # Create balance history record
            self._create_balance_history(total_balance)
            
            # Check alert conditions
            self._check_alert_conditions()
            
        except Exception as e:
            _logger.error(f"Failed to check balance for monitor {self.name}: {str(e)}")
            self._create_alert('error', f'Balance check failed: {str(e)}')
    
    def _get_wallet_addresses(self):
        """Get all addresses for the multisig wallet"""
        self.ensure_one()
        addresses = []
        
        try:
            wallet = self.multisig_wallet_id
            # Generate addresses to check (both receive and change)
            for change in [0, 1]:  # 0 = receive, 1 = change
                for index in range(20):  # Check first 20 addresses of each type
                    try:
                        addr_info = wallet._generate_multisig_addresses(change=change, count=1)
                        if addr_info:
                            # Get specific address at index
                            bip32_utils = self.env['crypto.bip32.utils']
                            sorted_keys = wallet.cosigner_public_key_ids.sorted('cosigner_index')
                            xpubs_with_paths = []
                            for key in sorted_keys:
                                if key.xpub:
                                    xpubs_with_paths.append((key.xpub, key.derivation_path or "m/48'/0'/0'/2'"))
                            
                            addr_info = bip32_utils.generate_multisig_address(
                                xpubs_with_paths=xpubs_with_paths,
                                m_threshold=wallet.m_of_n_threshold,
                                script_type=wallet.script_type,
                                change=change,
                                index=index
                            )
                            addresses.append(addr_info['address'])
                    except Exception as e:
                        _logger.debug(f"Could not generate address {change}/{index}: {str(e)}")
                        break  # Stop if we can't generate more addresses
                        
        except Exception as e:
            _logger.error(f"Failed to get wallet addresses: {str(e)}")
        
        return addresses
    
    def _create_balance_history(self, balance):
        """Create a balance history record"""
        self.env['crypto.bitcoin.balance.history'].create({
            'monitor_id': self.id,
            'balance': balance,
            'check_date': fields.Datetime.now(),
        })
    
    def _check_alert_conditions(self):
        """Check if any alert conditions are met"""
        self.ensure_one()
        
        if not self.active:
            return
        
        # Check if we've hit daily alert limit
        if self.alerts_sent_today >= self.max_alerts_per_day:
            return
        
        # Check if enough time has passed since last alert
        if self.last_alert_date:
            time_since_last = datetime.now() - self.last_alert_date
            if time_since_last.total_seconds() < (self.alert_frequency_hours * 3600):
                return
        
        alerts_to_send = []
        
        if self.monitor_type == 'threshold':
            alerts_to_send.extend(self._check_threshold_alerts())
        elif self.monitor_type == 'change':
            alerts_to_send.extend(self._check_change_alerts())
        elif self.monitor_type == 'velocity':
            alerts_to_send.extend(self._check_velocity_alerts())
        
        # Send alerts
        for alert_type, message in alerts_to_send:
            self._create_alert(alert_type, message)
    
    def _check_threshold_alerts(self):
        """Check balance threshold conditions"""
        alerts = []
        balance = self.current_balance
        
        if self.critical_threshold and balance <= self.critical_threshold:
            alerts.append(('critical', f'CRITICAL: Balance {balance:.8f} BTC is at or below critical threshold {self.critical_threshold:.8f} BTC'))
        elif self.low_threshold and balance <= self.low_threshold:
            alerts.append(('low', f'LOW BALANCE: Balance {balance:.8f} BTC is at or below threshold {self.low_threshold:.8f} BTC'))
        elif self.high_threshold and balance >= self.high_threshold:
            alerts.append(('high', f'HIGH BALANCE: Balance {balance:.8f} BTC is at or above threshold {self.high_threshold:.8f} BTC'))
        
        return alerts
    
    def _check_change_alerts(self):
        """Check balance change conditions"""
        alerts = []
        
        if self.previous_balance == 0:
            return alerts
        
        balance_change = self.current_balance - self.previous_balance
        change_percent = (balance_change / self.previous_balance) * 100 if self.previous_balance > 0 else 0
        
        if self.change_threshold_percent and abs(change_percent) >= self.change_threshold_percent:
            direction = "increased" if balance_change > 0 else "decreased"
            alerts.append(('change', f'BALANCE CHANGE: Balance {direction} by {abs(change_percent):.2f}% ({balance_change:+.8f} BTC)'))
        
        if self.change_threshold_absolute and abs(balance_change) >= self.change_threshold_absolute:
            direction = "increased" if balance_change > 0 else "decreased"
            alerts.append(('change', f'BALANCE CHANGE: Balance {direction} by {abs(balance_change):.8f} BTC'))
        
        return alerts
    
    def _check_velocity_alerts(self):
        """Check spending velocity conditions"""
        alerts = []
        
        if not self.velocity_limit_btc or not self.velocity_period_hours:
            return alerts
        
        # Calculate spending in the specified period
        cutoff_time = datetime.now() - timedelta(hours=self.velocity_period_hours)
        
        # Get transactions in the period (outgoing only)
        wallet = self.multisig_wallet_id
        recent_txs = wallet.multisig_transaction_ids.filtered(
            lambda tx: tx.date >= cutoff_time and tx.amount < 0  # Negative amount = outgoing
        )
        
        total_spent = sum(abs(tx.amount) for tx in recent_txs)
        
        if total_spent >= self.velocity_limit_btc:
            alerts.append(('velocity', f'VELOCITY LIMIT: {total_spent:.8f} BTC spent in last {self.velocity_period_hours}h (limit: {self.velocity_limit_btc:.8f} BTC)'))
        
        return alerts
    
    def _create_alert(self, alert_type, message):
        """Create and send an alert"""
        self.ensure_one()
        
        # Create alert record
        alert = self.env['crypto.bitcoin.balance.alert'].create({
            'monitor_id': self.id,
            'alert_type': alert_type,
            'message': message,
            'alert_date': fields.Datetime.now(),
        })
        
        # Update counters
        self.last_alert_date = fields.Datetime.now()
        self.alerts_sent_today += 1
        
        # Send notifications
        self._send_alert_notifications(alert)
        
        # Post in chatter
        self.message_post(
            body=f"🚨 {alert_type.upper()} ALERT: {message}",
            subject=f"Balance Alert - {self.name}"
        )
    
    def _send_alert_notifications(self, alert):
        """Send email notifications for alert"""
        self.ensure_one()
        
        if not (self.notify_users_ids or self.notify_emails):
            return
        
        # Use custom template if specified, otherwise use default
        template = self.email_template_id
        if not template:
            template = self.env.ref('account_cryptocurrency_bitcoin.email_template_balance_alert', raise_if_not_found=False)
        
        if template:
            # Send to specified users
            for user in self.notify_users_ids:
                if user.email:
                    template.with_context(alert_id=alert.id).send_mail(self.id, force_send=True, email_values={
                        'email_to': user.email,
                        'recipient_ids': [(4, user.partner_id.id)]
                    })
            
            # Send to additional emails
            if self.notify_emails:
                emails = [email.strip() for email in self.notify_emails.split(',') if email.strip()]
                for email in emails:
                    template.with_context(alert_id=alert.id).send_mail(self.id, force_send=True, email_values={
                        'email_to': email
                    })
    
    @api.model
    def _cron_check_all_balances(self):
        """Cron job to check all active monitors"""
        monitors = self.search([('active', '=', True)])
        
        for monitor in monitors:
            try:
                monitor._check_wallet_balance()
            except Exception as e:
                _logger.error(f"Failed to check balance for monitor {monitor.name}: {str(e)}")
        
        # Reset daily alert counters at midnight
        now = datetime.now()
        if now.hour == 0:
            monitors.write({'alerts_sent_today': 0})
    
    @api.model
    def _cron_send_daily_summaries(self):
        """Cron job to send daily balance summaries"""
        # Only send summaries for monitors that have users configured for notifications
        monitors = self.search([
            ('active', '=', True),
            ('notify_users_ids', '!=', False)
        ])
        
        summary_template = self.env.ref('account_cryptocurrency_bitcoin.email_template_balance_summary', raise_if_not_found=False)
        if not summary_template:
            _logger.warning("Daily balance summary template not found")
            return
        
        for monitor in monitors:
            try:
                # Send to specified users
                for user in monitor.notify_users_ids:
                    if user.email:
                        summary_template.send_mail(monitor.id, force_send=True, email_values={
                            'email_to': user.email,
                            'recipient_ids': [(4, user.partner_id.id)]
                        })
                
                _logger.info(f"Daily summary sent for monitor {monitor.name}")
                
            except Exception as e:
                _logger.error(f"Failed to send daily summary for monitor {monitor.name}: {str(e)}")


class CryptoBitcoinBalanceHistory(models.Model):
    _name = 'crypto.bitcoin.balance.history'
    _description = 'Bitcoin Balance History'
    _order = 'check_date desc'
    
    monitor_id = fields.Many2one('crypto.bitcoin.balance.monitor', string='Monitor', required=True, ondelete='cascade')
    balance = fields.Float(string='Balance (BTC)', digits=(16, 8), required=True)
    check_date = fields.Datetime(string='Check Date', required=True)
    notes = fields.Text(string='Notes')


class CryptoBitcoinBalanceAlert(models.Model):
    _name = 'crypto.bitcoin.balance.alert'
    _description = 'Bitcoin Balance Alert'
    _order = 'alert_date desc'
    
    monitor_id = fields.Many2one('crypto.bitcoin.balance.monitor', string='Monitor', required=True, ondelete='cascade')
    alert_type = fields.Selection([
        ('low', 'Low Balance'),
        ('high', 'High Balance'),
        ('critical', 'Critical Balance'),
        ('change', 'Balance Change'),
        ('velocity', 'Velocity Limit'),
        ('error', 'Error')
    ], string='Alert Type', required=True)
    message = fields.Text(string='Alert Message', required=True)
    alert_date = fields.Datetime(string='Alert Date', required=True)
    acknowledged = fields.Boolean(string='Acknowledged', default=False)
    acknowledged_by = fields.Many2one('res.users', string='Acknowledged By')
    acknowledged_date = fields.Datetime(string='Acknowledged Date')
    
    def action_acknowledge(self):
        """Acknowledge the alert"""
        self.ensure_one()
        self.write({
            'acknowledged': True,
            'acknowledged_by': self.env.user.id,
            'acknowledged_date': fields.Datetime.now()
        })