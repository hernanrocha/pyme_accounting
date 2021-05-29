# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class SaleImportCompEnLineaLine(models.TransientModel):
    _name = "l10n_ar.import.sale.compenlinea.line"
    _description = "Linea de comprobante de Comprobantes en Linea"

    date = fields.Date(string="Fecha")

    import_id = fields.Many2one(comodel_name="l10n_ar.import.sale.compenlinea", ondelete="cascade", invisible=True)

class SaleImportCompEnLinea(models.TransientModel):
    _name = "l10n_ar.import.sale.compenlinea"
    _description = "Importar archivo de Comprobantes en Linea"

    zip_file = fields.Binary(string="Archivo de Comprobantes (*.zip)")

    invoice_ids = fields.One2many(string="Comprobantes", comodel_name="l10n_ar.import.sale.compenlinea.line", inverse_name="import_id")
    
    def compute(self):
        raise UserError("No implementado")

    def generate(self):
        raise UserError("No implementado")