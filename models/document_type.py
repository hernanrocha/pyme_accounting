from odoo import api, fields, models, _
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)

class DocumentType(models.Model):
    _inherit = "l10n_latam.document.type"

    @api.model
    def get_by_afip_code(self, code):
        return self.search([
            ('code', '=', code)
        ])

    @api.model
    def get_by_prefix(self, prefix):
        prefix_to_afip_code = {
            'FA-A': '1',
            'ND-A': '2',
            'NC-A': '3',
            'RE-A': '4',
            'FA-B': '6',
            'ND-B': '7',
            'NC-B': '8',
            'RE-B': '9',
            'FA-C': '11',
            'ND-C': '12',
            'NC-C': '13',
            'RE-C': '15',
        }
        
        if not prefix in prefix_to_afip_code:
            return False

        return self.get_by_afip_code(prefix_to_afip_code[prefix])