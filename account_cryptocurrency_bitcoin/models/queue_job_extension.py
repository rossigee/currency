# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class QueueJobExtension(models.Model):
    _inherit = 'queue.job'

    # Job runner status - computed field for system-wide status
    jobrunner_status = fields.Selection([
        ('unknown', 'Unknown'),
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('disabled', 'Disabled')
    ], string='Job Runner Status', compute='_compute_jobrunner_status', store=False)
    
    # Dummy field to trigger jobrunner status computation
    _jobrunner_trigger = fields.Datetime(compute='_compute_jobrunner_status')

    def _compute_jobrunner_status(self):
        """Compute job runner status for all records"""
        # This is computed once for all records since it's a system-wide status
        status = self._get_jobrunner_status()
        for record in self:
            record.jobrunner_status = status
            record._jobrunner_trigger = fields.Datetime.now()

    @api.model
    def _get_jobrunner_status(self):
        """Determine the current job runner status"""
        try:
            # Check if cron jobrunner is enabled in config
            cron_enabled = self.env['ir.config_parameter'].sudo().get_param('queue_job.cron.jobrunner', False)
            
            if not cron_enabled:
                return 'disabled'
            
            # Check if the cron job exists and is active
            cron_job = self.env['ir.cron'].sudo().search([
                ('model_id.model', '=', 'queue.job'),
                ('function', 'ilike', 'jobrunner'),
                ('active', '=', True)
            ], limit=1)
            
            if not cron_job:
                return 'inactive'
            
            # Check for recent job activity (jobs completed in last 10 minutes)
            from datetime import datetime, timedelta
            recent_threshold = datetime.now() - timedelta(minutes=10)
            
            recent_jobs = self.env['queue.job'].sudo().search([
                ('state', '=', 'done'),
                ('date_done', '>=', recent_threshold)
            ], limit=1)
            
            if recent_jobs:
                return 'active'
            
            # Check for pending jobs (if there are pending jobs but none recently completed, runner might be stuck)
            pending_jobs = self.env['queue.job'].sudo().search([
                ('state', '=', 'pending')
            ], limit=1)
            
            if pending_jobs:
                return 'inactive'  # Jobs pending but none completing = inactive runner
            else:
                return 'active'  # No pending jobs, assume runner is working
                
        except Exception as e:
            _logger.warning(f"Failed to determine job runner status: {str(e)}")
            return 'unknown'