# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError
import logging

_logger = logging.getLogger(__name__)

class MultisigPortal(http.Controller):
    
    @http.route('/my/multisig/signature/<int:signature_id>', type='http', auth='public', website=True)
    def multisig_signature_form(self, signature_id, access_token=None, **kw):
        """Display the signature form for cosigners"""
        try:
            # Get the signature record
            signature = request.env['crypto.bitcoin.multisig.signature'].sudo().browse(signature_id)
            
            if not signature.exists():
                return request.render('website.404')
            
            # Verify access token
            if signature.access_token != access_token:
                return request.render('website.403')
            
            # Check if already signed
            if signature.state != 'pending':
                values = {
                    'signature': signature,
                    'already_signed': True,
                }
                return request.render('account_cryptocurrency_bitcoin.multisig_signature_complete', values)
            
            values = {
                'signature': signature,
                'workflow': signature.workflow_id,
                'error': kw.get('error'),
                'success': kw.get('success'),
            }
            
            return request.render('account_cryptocurrency_bitcoin.multisig_signature_form', values)
            
        except Exception as e:
            _logger.error(f"Error in multisig signature form: {str(e)}")
            return request.render('website.404')
    
    @http.route('/my/multisig/signature/<int:signature_id>/submit', type='http', auth='public', website=True, methods=['POST'], csrf=True)
    def multisig_signature_submit(self, signature_id, access_token=None, **post):
        """Submit the signature form"""
        try:
            # Get the signature record
            signature = request.env['crypto.bitcoin.multisig.signature'].sudo().browse(signature_id)
            
            if not signature.exists() or signature.access_token != access_token:
                return request.render('website.403')
            
            if signature.state != 'pending':
                return request.redirect(f'/my/multisig/signature/{signature_id}?access_token={access_token}')
            
            # Validate required fields
            required_fields = ['xpub', 'hardware_wallet_model', 'master_fingerprint']
            errors = []
            
            for field in required_fields:
                if not post.get(field):
                    errors.append(f"{field.replace('_', ' ').title()} is required")
            
            if errors:
                allerrors = ', '.join(errors)
                return request.redirect(f'/my/multisig/signature/{signature_id}?access_token={access_token}&error={allerrors}')
            
            # Update signature record
            signature_data = {
                'xpub': post.get('xpub'),
                'hardware_wallet_model': post.get('hardware_wallet_model'),
                'wallet_serial_last4': post.get('wallet_serial_last4', '')[:4],
                'firmware_version': post.get('firmware_version'),
                'master_fingerprint': post.get('master_fingerprint', '')[:8],
                'verification_method': post.get('verification_method', 'email'),
                'notes': post.get('notes'),
                'state': 'signed',
                'signed_date': fields.Datetime.now(),
                'signature_method': 'portal',
                'xpub_verified': post.get('xpub_verified') == 'on',
            }
            
            signature.write(signature_data)
            
            # Check if all signatures are complete
            signature.workflow_id._check_signatures_complete()
            
            # Post message
            signature.workflow_id.message_post(
                body=f"Signature received from {signature.name} (Cosigner {signature.cosigner_index}) via portal",
                subject="Portal Signature Received"
            )
            
            return request.redirect(f'/my/multisig/signature/{signature_id}?access_token={access_token}&success=1')
            
        except Exception as e:
            _logger.error(f"Error submitting multisig signature: {str(e)}")
            return request.redirect(f'/my/multisig/signature/{signature_id}?access_token={access_token}&error=An error occurred')
