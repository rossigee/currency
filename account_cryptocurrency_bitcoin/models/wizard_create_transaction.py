# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class WizardCreateTransaction(models.TransientModel):
    _name = 'wizard.create.transaction'
    _description = 'Create Bitcoin Transaction Wizard'

    multisig_wallet_id = fields.Many2one('crypto.bitcoin.multisig.wallet', 
                                         string='Multisig Wallet', required=True)
    
    # Transaction details
    name = fields.Char(string='Transaction Name', required=True, 
                       default='New Transaction')
    notes = fields.Text(string='Notes')
    
    # Fee settings
    target_fee_rate = fields.Float(string='Fee Rate (sat/vB)', default=5.0,
                                   help="Target fee rate in satoshis per virtual byte")
    
    # Output lines
    output_line_ids = fields.One2many('wizard.create.transaction.line', 'wizard_id',
                                      string='Transaction Outputs')
    
    # Summary fields
    total_output_btc = fields.Float(string='Total Output (BTC)', 
                                    compute='_compute_totals', store=False)
    total_output_sat = fields.Integer(string='Total Output (sat)', 
                                      compute='_compute_totals', store=False)
    estimated_fee_sat = fields.Integer(string='Estimated Fee (sat)', 
                                       compute='_compute_totals', store=False)
    estimated_fee_btc = fields.Float(string='Estimated Fee (BTC)', 
                                     compute='_compute_totals', store=False)
    total_needed_sat = fields.Integer(string='Total Needed (sat)', 
                                      compute='_compute_totals', store=False)
    total_needed_btc = fields.Float(string='Total Needed (BTC)', 
                                    compute='_compute_totals', store=False)

    @api.depends('output_line_ids.amount_btc', 'target_fee_rate')
    def _compute_totals(self):
        """Compute transaction totals and fee estimates"""
        for record in self:
            # Calculate total output
            total_btc = sum(line.amount_btc for line in record.output_line_ids)
            total_sat = int(total_btc * 100000000)
            
            # Estimate transaction size and fee
            num_outputs = len(record.output_line_ids)
            if num_outputs > 0 and record.multisig_wallet_id:
                # Rough estimation: base + outputs + multisig overhead
                estimated_size = 50 + (num_outputs * 35) + (record.multisig_wallet_id.m_of_n_threshold * 75)
                estimated_fee_sat = int(estimated_size * record.target_fee_rate)
            else:
                estimated_fee_sat = 0
            
            record.total_output_btc = total_btc
            record.total_output_sat = total_sat
            record.estimated_fee_sat = estimated_fee_sat
            record.estimated_fee_btc = estimated_fee_sat / 100000000
            record.total_needed_sat = total_sat + estimated_fee_sat
            record.total_needed_btc = record.total_needed_sat / 100000000


    def action_create_transaction(self):
        """Create the transaction and PSBT"""
        self.ensure_one()
        
        if not self.output_line_ids:
            raise ValidationError("At least one output is required")
        
        if not self.multisig_wallet_id.is_complete:
            raise ValidationError("Multisig wallet configuration is incomplete")
        
        # Validate all outputs
        for line in self.output_line_ids:
            if not line.recipient_address:
                raise ValidationError("All outputs must have a recipient address")
            if line.amount_btc <= 0:
                raise ValidationError("All outputs must have a positive amount")
        
        try:
            # Create transaction record
            transaction = self.env['crypto.bitcoin.transaction'].create({
                'date': fields.Datetime.now(),
                'tx_hash': '[Pending]',  # Placeholder until broadcast
                'notes': self.notes,
                'amount': self.total_output_btc,
                'fee': self.estimated_fee_btc,
                'status': 'draft',
                'multisig_wallet_id': self.multisig_wallet_id.id,
                'required_signatures': self.multisig_wallet_id.m_of_n_threshold,
                'target_fee_rate': self.target_fee_rate,
                'created_by_id': self.env.user.partner_id.id,
            })
            
            # Prepare outputs for PSBT creation
            outputs = []
            for line in self.output_line_ids:
                outputs.append({
                    'address': line.recipient_address.strip(),
                    'amount': int(line.amount_btc * 100000000)  # Convert to satoshis
                })
            
            # Create PSBT using utility
            bip32_utils = self.env['crypto.bip32.utils']
            psbt_result = bip32_utils.create_psbt(
                self.multisig_wallet_id, 
                outputs, 
                self.target_fee_rate
            )
            
            # Create transaction lines for outputs
            for i, line in enumerate(self.output_line_ids):
                # Get or create address record for the recipient
                address_record = self._get_or_create_address(line.recipient_address.strip())
                
                self.env['crypto.bitcoin.transaction.line'].create({
                    'transaction_id': transaction.id,
                    'line_type': 'output',
                    'address_id': address_record.id if address_record else False,
                    'amount': line.amount_btc,
                    'sequence': i + 1,
                    'description': line.description or f'Output {i + 1}',
                })
            
            # Update transaction with PSBT data
            transaction.write({
                'psbt_base64': psbt_result['psbt_base64'],
                'amount': psbt_result['total_output'] / 100000000,  # Convert to BTC
                'fee': psbt_result['estimated_fee'] / 100000000,    # Convert to BTC
                'status': 'unsigned_psbt'
            })
            
            # Return action to view the created transaction
            return {
                'type': 'ir.actions.act_window',
                'name': 'Created Transaction',
                'res_model': 'crypto.bitcoin.transaction',
                'res_id': transaction.id,
                'view_mode': 'form',
                'target': 'current',
            }
            
        except Exception as e:
            _logger.error(f"Failed to create transaction: {str(e)}")
            raise ValidationError(f"Transaction creation failed: {str(e)}")

    def _get_or_create_address(self, address_str):
        """
        Get or create a crypto.bitcoin.address record for the given address
        """
        try:
            # Check if address already exists
            existing_address = self.env['crypto.bitcoin.address'].search([
                ('address', '=', address_str)
            ], limit=1)
            
            if existing_address:
                return existing_address
            
            # Create new address record
            address_data = {
                'address': address_str,
                'type': 'receive',
                'notes': 'Created from transaction wizard',
            }
            
            return self.env['crypto.bitcoin.address'].create(address_data)
            
        except Exception as e:
            _logger.warning(f"Failed to create address record for {address_str}: {str(e)}")
            return None


class WizardCreateTransactionLine(models.TransientModel):
    _name = 'wizard.create.transaction.line'
    _description = 'Transaction Output Line'

    wizard_id = fields.Many2one('wizard.create.transaction', string='Wizard', 
                                required=True, ondelete='cascade')
    
    recipient_address = fields.Char(string='Recipient Address', required=True,
                                    help="Bitcoin address to send to")
    amount_btc = fields.Float(string='Amount (BTC)', required=True, digits=(16, 8),
                              help="Amount to send in BTC")
    amount_sat = fields.Integer(string='Amount (sat)', 
                                compute='_compute_amount_sat', store=False,
                                help="Amount in satoshis")
    description = fields.Char(string='Description', 
                              help="Optional description for this output")

    @api.depends('amount_btc')
    def _compute_amount_sat(self):
        """Convert BTC amount to satoshis"""
        for record in self:
            record.amount_sat = int(record.amount_btc * 100000000)

    @api.constrains('recipient_address')
    def _check_address_format(self):
        """Basic validation of Bitcoin address format"""
        for record in self:
            if record.recipient_address:
                address = record.recipient_address.strip()
                if not (address.startswith('1') or address.startswith('3') or address.startswith('bc1')):
                    raise ValidationError(f"Invalid Bitcoin address format: {address}")
                
                # Basic length checks
                if address.startswith('1') and len(address) < 26:
                    raise ValidationError(f"P2PKH address too short: {address}")
                elif address.startswith('3') and len(address) < 26:
                    raise ValidationError(f"P2SH address too short: {address}")
                elif address.startswith('bc1') and len(address) < 14:
                    raise ValidationError(f"Bech32 address too short: {address}")

    @api.constrains('amount_btc')
    def _check_amount_positive(self):
        """Ensure amount is positive"""
        for record in self:
            if record.amount_btc <= 0:
                raise ValidationError("Transaction amount must be positive")