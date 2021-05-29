# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class SaleImportWebServiceLine(models.TransientModel):
    _name = "l10n_ar.import.sale.webservice.line"
    _description = "Linea de comprobante de WebService AFIP"

    date = fields.Date(string="Fecha")

    import_id = fields.Many2one(comodel_name="l10n_ar.import.sale.webservice", ondelete="cascade", invisible=True)

class SaleImportWebService(models.TransientModel):
    _name = "l10n_ar.import.sale.webservice"
    _description = "Importar desde WebService AFIP"

    pos = fields.Integer(string="Punto de Venta")
    number = fields.Integer(string="Número de Comprobante")

    # TODO: soporte para carga masiva
    # number_to = fields.Integer(string="Comprobante Hasta")

    invoice_ids = fields.One2many(string="Comprobantes", comodel_name="l10n_ar.import.sale.webservice.line", inverse_name="import_id")
    
    def compute(self):
        raise UserError("No implementado")

    def generate(self):
        raise UserError("No implementado")