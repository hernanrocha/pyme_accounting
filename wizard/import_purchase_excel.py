# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class PurchaseImportExcel(models.TransientModel):
    _name = "l10n_ar.import.purchase.excel"
    _description = "Importar compras desde archivo Excel"

    @api.model
    def action_import_menu(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'import',
            'params': {
                'model': 'account.move'
            },
            'context': {
                'default_move_type': 'in_invoice'
            }
        }
