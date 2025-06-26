# Copyright 2025 Ross Golder
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models, api
from odoo.exceptions import ValidationError
import json

class WizardDeriveAddresses(models.TransientModel):
    _name = 'wizard.derive.addresses'
    _description = 'Wizard to Derive Addresses from XPUB'

    public_key_id = fields.Many2one('crypto.bitcoin.public.key', string='Public Key', required=True)
    start_index = fields.Integer(string='Start Index', default=0, required=True)
    count = fields.Integer(string='Count', default=10, required=True)
    address_type = fields.Selection([
        ('receive', 'Receive Addresses (m/0/x)'),
        ('change', 'Change Addresses (m/1/x)'),
        ('both', 'Both Receive and Change')
    ], string='Address Type', default='receive', required=True)
    
    # Results
    derived_addresses_json = fields.Text(string='Derived Addresses (JSON)', readonly=True)
    derived_addresses_display = fields.Text(string='Derived Addresses', readonly=True)

    @api.onchange('public_key_id')
    def _onchange_public_key_id(self):
        """Update count limit based on selected public key"""
        if self.public_key_id:
            self.count = min(self.count, self.public_key_id.max_derivation_count)

    def action_derive_addresses(self):
        """Perform secure address derivation"""
        self.ensure_one()
        
        if not self.public_key_id:
            raise ValidationError("Public key is required")
            
        results = []
        display_lines = []
        
        try:
            if self.address_type in ('receive', 'both'):
                # Derive receive addresses
                receive_addrs = self.public_key_id.derive_addresses(
                    start_index=self.start_index,
                    count=self.count,
                    change=False
                )
                results.extend(receive_addrs)
                display_lines.append("=== RECEIVE ADDRESSES (m/0/x) ===")
                for addr in receive_addrs:
                    display_lines.append(f"{addr['path']}: {addr['address']}")
                    
            if self.address_type in ('change', 'both'):
                # Derive change addresses  
                change_addrs = self.public_key_id.derive_addresses(
                    start_index=self.start_index,
                    count=self.count,
                    change=True
                )
                results.extend(change_addrs)
                if display_lines:
                    display_lines.append("")  # Empty line separator
                display_lines.append("=== CHANGE ADDRESSES (m/1/x) ===")
                for addr in change_addrs:
                    display_lines.append(f"{addr['path']}: {addr['address']}")
                    
            # Store results
            self.derived_addresses_json = json.dumps(results, indent=2)
            self.derived_addresses_display = "\n".join(display_lines)
            
            # Return action to show results
            return {
                'type': 'ir.actions.act_window',
                'name': 'Derived Addresses',
                'res_model': 'wizard.derive.addresses',
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
                'context': {'show_results': True}
            }
            
        except Exception as e:
            raise ValidationError(f"Address derivation failed: {str(e)}")

    def action_export_addresses(self):
        """Export derived addresses as downloadable file"""
        self.ensure_one()
        
        if not self.derived_addresses_json:
            raise ValidationError("No addresses to export. Please derive addresses first.")
            
        # Create attachment for download
        attachment = self.env['ir.attachment'].create({
            'name': f'derived_addresses_{self.public_key_id.name}.json',
            'type': 'binary',
            'datas': self.derived_addresses_json.encode(),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/json'
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }