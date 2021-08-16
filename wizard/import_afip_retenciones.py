# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import xml.etree.ElementTree as ET
import base64
import logging
import xlrd
from datetime import datetime

_logger = logging.getLogger(__name__)

class ImportAfipMisRetencionesLine(models.TransientModel):
    _name = "l10n_ar.import.afip.retenciones.line"
    _description = "Linea de Mis Retenciones"

    date = fields.Date(string="Fecha")
    # invoice_type = fields.Char(string="Tipo de Comprobante")
    # pos_number = fields.Char(string="Punto de Venta")
    # invoice_number = fields.Char(string="N° Factura")
    # cuit = fields.Char(string="CUIT")
    # vendor = fields.Char(string="Proveedor")
    # taxed_amount = fields.Float(string="Gravado")
    # untaxed_amount = fields.Float(string="No Gravado")
    # exempt_amount = fields.Float(string="Exento")
    # iva = fields.Float(string="Monto IVA")
    total = fields.Float(string="Total")

    import_id = fields.Many2one(comodel_name="l10n_ar.import.afip.retenciones", ondelete="cascade", invisible=True)

    # @api.depends('taxed_amount', 'iva', 'untaxed_amount', 'exempt_amount', 'total')
    # def _compute_difference(self):
    #     for line in self:
    #         line.difference = line.total - (line.taxed_amount + line.iva + line.untaxed_amount + line.exempt_amount)

    # invoice_display_name = fields.Char(string="Comprobante", compute="_compute_invoice_display_name", invisible=True)

class ImportAfipMisRetenciones(models.TransientModel):
    _name = "l10n_ar.import.afip.retenciones"
    _description = "Importar Mis Retenciones"

    file = fields.Binary(string="Archivo de Retenciones (*.csv)")

    invoice_ids = fields.One2many(string="Retenciones", comodel_name="l10n_ar.import.afip.retenciones.line", inverse_name="import_id")
    
    def parse(self):
        [data] = self.read()

        if not data['file']:
            raise UserError("Debes cargar un archivo de compras de AFIP")
        
        # Borrar registros anteriores
        self.write({ 'invoice_ids': [(5, 0, 0)] })

        # Leer archivo AFIP de compras
        file_content = base64.decodestring(data['file'])

        book = xlrd.open_workbook(file_contents=file_content or b'')
        sheets = book.sheet_names()
        sheet_name = sheets[0]
        _logger.info(sheet_name)
        sheet = book.sheet_by_name(sheet_name)

        # 0 CUIT Agente Ret./Perc.
        # 1 Denominación o Razón Social
        # 2 Impuesto
        # 3 Descripción Impuesto
        # 4 Régimen
        # 5 Descripción Régimen
        # 6 Fecha Ret./Perc.
        # 7 Número Certificado
        # 8 Descripción Operación
        # 9 Importe Ret./Perc.
        # 10 Número Comprobante
        # 11 Fecha Comprobante
        # 12 Descripción Comprobante
        # 13 Fecha Registración DJ Ag.Ret.

        retenciones = []

        for rowx, row in enumerate(map(sheet.row, range(sheet.nrows)), 1):
            values = []
            
            # Skip first line
            if rowx == 1:
                continue

            for colx, cell in enumerate(row, 1):
                values.append(str(cell.value))

            retenciones.append(values)
            _logger.info(values)

        self.generate(retenciones)

    def generate(self, retenciones):
        for retencion in retenciones:
            ret = self.env['l10n_ar.impuestos.deduccion'].create({
                'state': 'available',
                'tax': 'iva',
                'type': 'iva_percepcion',
                'date': datetime.strptime(retencion[11], '%d/%m/%Y'),
                'amount': float(retencion[9]),
                'cuit': retencion[0],
            })
            _logger.info("Retencion: {}".format(ret))