# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
import logging
import base64
import json
from datetime import datetime, timedelta
import hashlib

_logger = logging.getLogger(__name__)

class CryptoBitcoinMultisigWorkflow(models.Model):
    _name = 'crypto.bitcoin.multisig.workflow'
    _description = 'Multisig Wallet Setup Workflow'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'
    
    name = fields.Char(string='Workflow Name', required=True, tracking=True)
    multisig_wallet_id = fields.Many2one('crypto.bitcoin.multisig.wallet', string='Multisig Wallet', ondelete='cascade')
    
    # Workflow metadata
    state = fields.Selection([
        ('draft', 'Draft'),
        ('collecting_signatures', 'Collecting Signatures'),
        ('signatures_complete', 'Signatures Complete'),
        ('wallet_created', 'Wallet Created'),
        ('cancelled', 'Cancelled')
    ], string='State', default='draft', tracking=True)
    
    initiated_by = fields.Many2one('res.users', string='Initiated By', default=lambda self: self.env.user, readonly=True)
    initiated_date = fields.Datetime(string='Initiated Date', default=fields.Datetime.now, readonly=True)
    completed_date = fields.Datetime(string='Completed Date', readonly=True)
    expiry_date = fields.Datetime(string='Expiry Date', compute='_compute_expiry_date', store=True)
    
    # Wallet configuration (copied from form data)
    wallet_name = fields.Char(string='Wallet Name', required=True)
    wallet_type = fields.Selection([
        ('2-3', '2-of-3'),
        ('3-5', '3-of-5'),
        ('4-7', '4-of-7'),
        ('custom', 'Custom')
    ], string='Wallet Type', required=True, default='2-3')
    m_threshold = fields.Integer(string='Required Signatures (M)', required=True, default=2)
    n_total = fields.Integer(string='Total Cosigners (N)', required=True, default=3)
    script_type = fields.Selection([
        ('p2wsh', 'P2WSH (Native SegWit)'),
        ('p2sh_p2wsh', 'P2SH-P2WSH (Nested SegWit)'),
        ('p2sh', 'P2SH (Legacy)')
    ], string='Script Type', required=True, default='p2wsh')
    derivation_path = fields.Char(string='Derivation Path', default="m/48'/0'/0'/2'")
    
    # Workflow configuration
    require_all_signatures = fields.Boolean(string='Require All Cosigner Signatures', default=True,
                                          help='If unchecked, wallet creation can proceed with minimum required signatures')
    signature_deadline_days = fields.Integer(string='Signature Deadline (Days)', default=7)
    
    # Security and verification
    form_data_hash = fields.Char(string='Form Data Hash', readonly=True, 
                                help='SHA256 hash of the wallet configuration data')
    
    # Signature collection
    signature_ids = fields.One2many('crypto.bitcoin.multisig.signature', 'workflow_id', string='Signatures')
    signatures_collected = fields.Integer(string='Signatures Collected', compute='_compute_signature_stats', store=True)
    signatures_required = fields.Integer(string='Signatures Required', compute='_compute_signature_stats', store=True)
    
    # Generated documents
    setup_form_pdf = fields.Binary(string='Setup Form PDF', attachment=True)
    setup_form_filename = fields.Char(string='Setup Form Filename')
    
    # Use case configuration
    use_case = fields.Selection([
        ('family', 'Family Wallet (Low Value)'),
        ('club', 'Sports Club/Organization Treasury'),
        ('estate', 'High Value Estate/Trust'),
        ('business', 'Business Treasury'),
        ('custom', 'Custom Configuration')
    ], string='Use Case', required=True, default='custom')
    
    notes = fields.Text(string='Notes')
    
    @api.depends('initiated_date', 'signature_deadline_days')
    def _compute_expiry_date(self):
        for record in self:
            if record.initiated_date and record.signature_deadline_days:
                record.expiry_date = record.initiated_date + timedelta(days=record.signature_deadline_days)
            else:
                record.expiry_date = False
    
    @api.depends('signature_ids.state')
    def _compute_signature_stats(self):
        for record in self:
            signatures = record.signature_ids.filtered(lambda s: s.state == 'signed')
            record.signatures_collected = len(signatures)
            record.signatures_required = record.n_total if record.require_all_signatures else record.m_threshold
    
    @api.model
    def create(self, vals):
        # Generate form data hash
        form_data = {
            'wallet_name': vals.get('wallet_name'),
            'wallet_type': vals.get('wallet_type'),
            'm_threshold': vals.get('m_threshold'),
            'n_total': vals.get('n_total'),
            'script_type': vals.get('script_type'),
            'derivation_path': vals.get('derivation_path'),
            'use_case': vals.get('use_case'),
        }
        vals['form_data_hash'] = hashlib.sha256(json.dumps(form_data, sort_keys=True).encode()).hexdigest()
        
        workflow = super().create(vals)
        
        # Auto-generate signature requests based on n_total
        workflow._create_signature_requests()
        
        return workflow
    
    def _create_signature_requests(self):
        """Create signature request records for each cosigner"""
        self.ensure_one()
        
        for i in range(self.n_total):
            self.env['crypto.bitcoin.multisig.signature'].create({
                'workflow_id': self.id,
                'cosigner_index': i + 1,
                'name': f"{self.wallet_name} - Cosigner {i + 1}",
                'state': 'pending',
            })
    
    def action_start_collection(self):
        """Start the signature collection process"""
        self.ensure_one()
        
        if self.state != 'draft':
            raise UserError("Workflow must be in draft state to start collection")
        
        # Generate PDF form
        self._generate_setup_form_pdf()
        
        # Send notification emails to cosigners
        self._send_signature_requests()
        
        self.state = 'collecting_signatures'
        
        # Create activity for follow-up
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=f"Multisig Wallet Setup: {self.wallet_name}",
            note=f"Collecting signatures for {self.n_total} cosigners. Deadline: {self.expiry_date}",
            date_deadline=self.expiry_date.date() if self.expiry_date else False,
            user_id=self.initiated_by.id
        )
    
    def action_create_wallet(self):
        """Create the actual multisig wallet once signatures are collected"""
        self.ensure_one()
        
        if self.state != 'signatures_complete':
            raise UserError("All required signatures must be collected first")
        
        # Create the multisig wallet
        wallet_vals = {
            'name': self.wallet_name,
            'description': f"Created via workflow {self.name}",
            'm_of_n_threshold': self.m_threshold,
            'total_cosigners': self.n_total,
            'script_type': self.script_type,
            'network': 'mainnet',  # TODO: Make configurable
            'notes': f"Use case: {self.use_case}\nWorkflow: {self.name}\n{self.notes or ''}"
        }
        
        wallet = self.env['crypto.bitcoin.multisig.wallet'].create(wallet_vals)
        self.multisig_wallet_id = wallet
        
        # Add cosigner public keys from signatures
        for sig in self.signature_ids.filtered(lambda s: s.state == 'signed'):
            if sig.xpub:
                # Create public key record
                self.env['crypto.bitcoin.public.key'].create({
                    'name': sig.name,
                    'xpub': sig.xpub,
                    'derivation_path': self.derivation_path,
                    'master_fingerprint': sig.master_fingerprint,
                    'cosigner_index': sig.cosigner_index,
                    'multisig_wallet_id': wallet.id,
                    'key_type': 'multisig',
                    'owner_id': sig.signer_id.partner_id.id if sig.signer_id else False,
                })
        
        self.state = 'wallet_created'
        self.completed_date = fields.Datetime.now()
        
        # Mark activity as done
        self.activity_ids.filtered(lambda a: a.summary == f"Multisig Wallet Setup: {self.wallet_name}").action_done()
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crypto.bitcoin.multisig.wallet',
            'res_id': wallet.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_cancel(self):
        """Cancel the workflow"""
        self.ensure_one()
        
        if self.state in ['wallet_created', 'cancelled']:
            raise UserError("Cannot cancel a completed or already cancelled workflow")
        
        self.state = 'cancelled'
        
        # Cancel all pending signatures
        self.signature_ids.filtered(lambda s: s.state == 'pending').write({'state': 'cancelled'})
        
        # Mark activities as done
        self.activity_ids.action_done()
    
    def _generate_setup_form_pdf(self):
        """Generate PDF version of the setup form"""
        self.ensure_one()
        
        # Get the report
        report = self.env.ref('account_cryptocurrency_bitcoin.report_multisig_setup_form')
        pdf_content, _ = report._render_qweb_pdf(self.ids)
        
        # Save as attachment
        self.setup_form_pdf = base64.b64encode(pdf_content)
        self.setup_form_filename = f"multisig_setup_{self.wallet_name.replace(' ', '_')}.pdf"
    
    def action_download_pdf(self):
        """Download the setup form PDF"""
        self.ensure_one()
        
        if not self.setup_form_pdf:
            self._generate_setup_form_pdf()
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/setup_form_pdf/{self.setup_form_filename}?download=true',
            'target': 'self',
        }
    
    def _send_signature_requests(self):
        """Send signature request emails to cosigners"""
        self.ensure_one()
        
        template = self.env.ref('account_cryptocurrency_bitcoin.email_template_multisig_signature_request', raise_if_not_found=False)
        if not template:
            _logger.warning("Email template for multisig signature request not found")
            return
        
        for signature in self.signature_ids:
            if signature.signer_email:
                template.send_mail(signature.id, force_send=True)
    
    @api.model
    def _cron_check_expired_workflows(self):
        """Cron job to check and handle expired workflows"""
        expired_workflows = self.search([
            ('state', '=', 'collecting_signatures'),
            ('expiry_date', '<', fields.Datetime.now())
        ])
        
        for workflow in expired_workflows:
            # Check if we have minimum required signatures
            if workflow.signatures_collected >= workflow.m_threshold and not workflow.require_all_signatures:
                workflow.state = 'signatures_complete'
                workflow.message_post(
                    body="Workflow expired but minimum signatures collected. Ready to create wallet.",
                    subject="Signature Collection Complete"
                )
            else:
                workflow.action_cancel()
                workflow.message_post(
                    body=f"Workflow cancelled due to expiry. Collected {workflow.signatures_collected} of {workflow.signatures_required} required signatures.",
                    subject="Workflow Expired"
                )


class CryptoBitcoinMultisigSignature(models.Model):
    _name = 'crypto.bitcoin.multisig.signature'
    _description = 'Multisig Wallet Cosigner Signature'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    
    workflow_id = fields.Many2one('crypto.bitcoin.multisig.workflow', string='Workflow', required=True, ondelete='cascade')
    cosigner_index = fields.Integer(string='Cosigner Index', required=True)
    name = fields.Char(string='Cosigner Name', required=True)
    
    # Signer information
    signer_id = fields.Many2one('res.users', string='Signer User')
    signer_email = fields.Char(string='Signer Email')
    signer_partner_id = fields.Many2one('res.partner', string='Signer Contact', compute='_compute_signer_partner', store=True)
    
    # Signature data
    state = fields.Selection([
        ('pending', 'Pending'),
        ('signed', 'Signed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled')
    ], string='State', default='pending', tracking=True)
    
    signed_date = fields.Datetime(string='Signed Date')
    signature = fields.Binary(string='Digital Signature', attachment=True)
    signature_method = fields.Selection([
        ('portal', 'Portal Signature'),
        ('email', 'Email Confirmation'),
        ('manual', 'Manual Entry'),
        ('odoo_sign', 'Odoo Sign')
    ], string='Signature Method')
    
    # Cosigner wallet data
    hardware_wallet_model = fields.Char(string='Hardware Wallet Model')
    wallet_serial_last4 = fields.Char(string='Serial Number (Last 4)', size=4)
    firmware_version = fields.Char(string='Firmware Version')
    master_fingerprint = fields.Char(string='Master Fingerprint', size=8)
    xpub = fields.Text(string='Extended Public Key (xPub)')
    xpub_verified = fields.Boolean(string='xPub Verified', default=False)
    
    # Verification
    verification_method = fields.Selection([
        ('in_person', 'In Person'),
        ('video_call', 'Video Call'),
        ('phone', 'Phone'),
        ('email', 'Email')
    ], string='Verification Method')
    verified_by_id = fields.Many2one('res.users', string='Verified By')
    
    # Access token for portal users
    access_token = fields.Char(string='Access Token', default=lambda self: self._generate_access_token())
    
    notes = fields.Text(string='Notes')
    
    @api.depends('signer_id')
    def _compute_signer_partner(self):
        for record in self:
            record.signer_partner_id = record.signer_id.partner_id if record.signer_id else False
    
    def _generate_access_token(self):
        """Generate a unique access token for portal access"""
        import secrets
        return secrets.token_urlsafe(32)
    
    def action_sign(self):
        """Mark signature as signed"""
        self.ensure_one()
        
        if self.state != 'pending':
            raise UserError("Only pending signatures can be signed")
        
        if not self.xpub:
            raise UserError("Extended public key (xPub) is required")
        
        self.write({
            'state': 'signed',
            'signed_date': fields.Datetime.now(),
            'signature_method': 'manual',
            'verified_by_id': self.env.user.id
        })
        
        # Check if all signatures are collected
        self.workflow_id._check_signatures_complete()
        
        # Post message
        self.workflow_id.message_post(
            body=f"Signature received from {self.name} (Cosigner {self.cosigner_index})",
            subject="Signature Received"
        )
    
    def action_reject(self):
        """Reject signature request"""
        self.ensure_one()
        
        if self.state != 'pending':
            raise UserError("Only pending signatures can be rejected")
        
        self.state = 'rejected'
        
        # Post message
        self.workflow_id.message_post(
            body=f"Signature rejected by {self.name} (Cosigner {self.cosigner_index})",
            subject="Signature Rejected"
        )
    
    def get_portal_url(self):
        """Get the portal URL for this signature request"""
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return f"{base_url}/my/multisig/signature/{self.id}?access_token={self.access_token}"


class CryptoBitcoinMultisigWorkflowExtension(models.Model):
    _inherit = 'crypto.bitcoin.multisig.workflow'
    
    def _check_signatures_complete(self):
        """Check if all required signatures are collected"""
        self.ensure_one()
        
        if self.state != 'collecting_signatures':
            return
        
        if self.signatures_collected >= self.signatures_required:
            self.state = 'signatures_complete'
            
            # Notify initiator
            self.message_post(
                body=f"All required signatures collected ({self.signatures_collected}/{self.n_total}). Wallet can now be created.",
                subject="Signatures Complete",
                partner_ids=[self.initiated_by.partner_id.id]
            )