# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class SaleImportExcel(models.TransientModel):
    _name = "l10n_ar.import.sale.excel"
    _description = "Importar ventas desde archivo Excel"

    @api.model
    def action_import_menu(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'import',
            'params': {
                'model': 'account.move'
            },
            'context': {
                'default_move_type': 'out_invoice'
            }
        }
