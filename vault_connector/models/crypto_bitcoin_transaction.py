# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import base64
import logging

_logger = logging.getLogger(__name__)


class CryptoBitcoinTransactionLine(models.Model):
    _name = 'crypto.bitcoin.transaction.line'
    _description = 'Crypto Bitcoin Transaction Line'

    transaction_id = fields.Many2one('crypto.transaction', "Transaction")
    line_hash = fields.Char(string="Line hash", required=True)
    address_id = fields.Many2one('crypto.address', string='Address')
    amount = fields.Float(string='Amount', required=True)


class CryptoBitcoinTransaction(models.Model):
    _name = 'crypto.bitcoin.transaction'
    _description = 'Crypto Bitcoin Transaction'

    date = fields.Datetime(string='Date')
    tx_hash = fields.Char(string='Transaction Hash', required=True)
    notes = fields.Text(string='Notes')
    size = fields.Integer(string="Size (vb)")
    inputs = fields.Many2one('crypto.bitcoin.transaction.line', string='Input TXs')
    outputs = fields.Many2one('crypto.bitcoin.transaction.line', string='Output TXs')
    amount = fields.Float(string='Amount', required=True)
    fee = fields.Float(string='Fee', required=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('unsigned_psbt', 'Unsigned PSBT'),
        ('partial_psbt', 'Partially Signed PSBT'),
        ('signed_psbt', 'Fully Signed PSBT'),
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
    ], string='Status', required=True)
    rbf_enabled = fields.Boolean(string="Replace by fee enabled")
    lock_time = fields.Integer(string="Lock time (height)")
    mined_block = fields.Integer(string="Mined in block")

    from_wallet_id = fields.Many2one('crypto.bitcoin.wallet', string='From Wallet')
    to_wallet_id = fields.Many2one('crypto.bitcoin.wallet', string='To Wallet')
    
    # PSBT-specific fields
    multisig_wallet_id = fields.Many2one('crypto.bitcoin.multisig.wallet', string='Multisig Wallet')
    psbt_base64 = fields.Text(string='PSBT (Base64)', help="Partially Signed Bitcoin Transaction in base64 format")
    raw_transaction = fields.Text(string='Raw Transaction (Hex)', help="Final transaction in hex format")
    
    # Signing tracking
    required_signatures = fields.Integer(string='Required Signatures', help="M threshold from multisig wallet")
    current_signatures = fields.Integer(string='Current Signatures', compute='_compute_signature_count', store=False)
    signatures_complete = fields.Boolean(string='Signatures Complete', compute='_compute_signature_count', store=False)
    
    # Transaction creation metadata
    created_by_id = fields.Many2one('res.partner', string='Created By')
    target_fee_rate = fields.Float(string='Target Fee Rate (sat/vB)', help="Target fee rate for transaction")

    @api.depends('psbt_base64', 'required_signatures')
    def _compute_signature_count(self):
        """Compute current signature count from PSBT"""
        for record in self:
            if not record.psbt_base64:
                record.current_signatures = 0
                record.signatures_complete = False
                continue
                
            try:
                # Use PSBT parsing utility
                bip32_utils = self.env['crypto.bip32.utils']
                sig_info = bip32_utils.parse_psbt_signatures(record.psbt_base64)
                
                record.current_signatures = sig_info['signature_count']
                record.signatures_complete = (
                    record.required_signatures > 0 and 
                    record.current_signatures >= record.required_signatures
                )
            except Exception as e:
                _logger.warning(f"Failed to parse PSBT signatures: {str(e)}")
                record.current_signatures = 0
                record.signatures_complete = False

    def action_create_psbt(self):
        """Create unsigned PSBT for this transaction"""
        self.ensure_one()
        
        if not self.multisig_wallet_id:
            raise ValidationError("Multisig wallet required for PSBT creation")
            
        if not self.multisig_wallet_id.is_complete:
            raise ValidationError("Multisig wallet configuration incomplete")
        
        # For now, create a simple test output
        # In a real implementation, this would come from user input
        test_outputs = [
            {
                'address': 'bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh',
                'amount': 100000  # 0.001 BTC in satoshis
            }
        ]
        
        try:
            # Use PSBT creation utility
            bip32_utils = self.env['crypto.bip32.utils']
            psbt_result = bip32_utils.create_psbt(
                self.multisig_wallet_id, 
                test_outputs, 
                self.target_fee_rate
            )
            
            # Update transaction with PSBT data
            self.write({
                'psbt_base64': psbt_result['psbt_base64'],
                'required_signatures': self.multisig_wallet_id.m_of_n_threshold,
                'amount': psbt_result['total_output'] / 100000000,  # Convert to BTC
                'fee': psbt_result['estimated_fee'] / 100000000,    # Convert to BTC
                'target_fee_rate': psbt_result['fee_rate'],
                'status': 'unsigned_psbt'
            })
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'PSBT Created',
                    'message': f'Created PSBT with {psbt_result["total_output"]} sat output + {psbt_result["estimated_fee"]} sat fee',
                    'type': 'success'
                }
            }
            
        except Exception as e:
            raise ValidationError(f"PSBT creation failed: {str(e)}")

    def action_export_psbt(self):
        """Export PSBT file for external signing"""
        self.ensure_one()
        
        if not self.psbt_base64:
            raise ValidationError("No PSBT available for export")
        
        # Generate filename
        filename = f"transaction_{self.id}.psbt"
        
        # Create attachment
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': self.psbt_base64,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/octet-stream',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_import_psbt(self):
        """Import signed PSBT"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Import Signed PSBT',
            'res_model': 'wizard.import.psbt',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_transaction_id': self.id,
            }
        }
