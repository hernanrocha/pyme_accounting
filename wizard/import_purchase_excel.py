# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class PurchaseImportExcel(models.TransientModel):
    _name = "l10n_ar.import.purchase.excel"
    _description = "Importar compras desde archivo Excel"

    invoice_date = fields.Date(string="Fecha Cbte")
    name = fields.Char(string="Comprobante")
    cuit = fields.Char(string="CUIT")
    amount_taxed = fields.Float(string="Gravado")
    amount_untaxed = fields.Float(string="No Gravado")
    amount_exempt = fields.Float(string="Exento")
    tax_21 = fields.Float(string="IVA 21%")
    tax_10 = fields.Float(string="IVA 10.5%")
    tax_27 = fields.Float(string="IVA 27%")
    perc_iibb = fields.Float(string="Percepción IIBB")
    perc_iva = fields.Float(string="Percepción IVA")
    total = fields.Float(string="Total")
    @api.model
    def action_import_menu(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'import',
            'params': {
                'model': 'l10n_ar.import.purchase.excel'
            },
            'context': {
                'default_move_type': 'in_invoice'
            },
            # TODO: esto genera una ventana diferente
            # 'target': 'new'
        }
