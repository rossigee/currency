from odoo import models, fields, api
from odoo.exceptions import ValidationError

class WizardBitcoinXpub(models.TransientModel):
    _name = 'wizard.bitcoin.xpub'
    _description = 'Bitcoin XPUB Wizard'

    name = fields.Char(string='Name', required=True)
    xpub = fields.Char(string='XPUB', required=True)

    def validate_and_save_xpub(self):
        # Validate the XPUB string
        if not self._validate_xpub(self.xpub):
            raise ValidationError('Invalid XPUB format. Please enter a valid XPUB string.')

        # Use the existing model to create a record
        self.env['crypto.bitcoin.public.key'].create({
            'name': 'New Bitcoin Public Key',
            'xpub': self.xpub,
            # Add other fields as necessary, e.g., 'owner_id', 'wallet_id'
        })

        return {
            'type': 'ir.actions.act_window_close'
        }

    def _validate_xpub(self, xpub):
        # Use the existing validation method from the model
        return self.env['crypto.bitcoin.public.key']._validate_xpub(xpub)
