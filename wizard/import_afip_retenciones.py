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

    # TODO: Fecha retencion/percepcion
    # TODO: Numero de certificado
    date = fields.Date(string="Fecha Cbte")
    cuit = fields.Char(string="CUIT")
    partner = fields.Char(string="Proveedor")
    impuesto = fields.Selection([
        # SICORE
        ('767', '767 - SICORE Perc/Ret IVA'),
        # SIRE
        ('216', '216 - SIRE IVA')
    ], string="Impuesto")
    regimen = fields.Selection([
        # SICORE
        ('493', '493 - Percepción IVA de Proveedores'),
        # SIRE
        ('17', '17 - Pagos con Tarjetas de Crédito')
    ], string="Regimen")
    descripcion = fields.Char(string="Descripcion")
    numero_comprobante = fields.Char(string="Numero Cbte")
    total = fields.Float(string="Total")
    descripcion_cbte = fields.Char(string="Descripcion Cbte")
    date_registered = fields.Date(string="Fecha Registración")
    # TODO: filtrar por mes y por proveedor

    import_id = fields.Many2one(comodel_name="l10n_ar.import.afip.retenciones", ondelete="cascade", invisible=True)
    invoice_id = fields.Many2one(string="Cbte Asociado", comodel_name="account.move", ondelete="set null")

    # @api.depends('taxed_amount', 'iva', 'untaxed_amount', 'exempt_amount', 'total')
    # def _compute_difference(self):
    #     for line in self:
    #         line.difference = line.total - (line.taxed_amount + line.iva + line.untaxed_amount + line.exempt_amount)

    # invoice_display_name = fields.Char(string="Comprobante", compute="_compute_invoice_display_name", invisible=True)

class ImportAfipMisRetenciones(models.TransientModel):
    _name = "l10n_ar.import.afip.retenciones"
    _description = "Importar Mis Retenciones"

    file = fields.Binary(string="Archivo de Retenciones (*.xls)")

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

        for retencion in retenciones:
            r = self.invoice_ids.create({
                'date': datetime.strptime(retencion[11], '%d/%m/%Y'),
                'cuit': retencion[0],
                'partner': retencion[1],
                'impuesto': retencion[2],
                'regimen': retencion[4],
                'descripcion': retencion[8],
                'total': float(retencion[9]),
                'numero_comprobante': retencion[10],
                'descripcion_cbte': retencion[12],
                'date_registered': datetime.strptime(retencion[13], '%d/%m/%Y'),
                'import_id': self.id
            })

            # TODO: Solo funciona para percepciones
            cbte = ''
            
            # 0000561800014834 => FA-A 05618-00014834
            if len(r.numero_comprobante) == 16:
                cbte = f'{r.numero_comprobante[3:8]}-{r.numero_comprobante[8:]}'
            # Formato desconocido. No se busca el comprobante asociado
            else:
                continue
            
            comp = self.env['account.move'].search([
                ('move_type', 'in', ['in_invoice', 'in_refund']),
                ('name', 'like', cbte),
                # TODO: buscar por CUIT
            ])
            
            if comp:
                r.invoice_id = comp

        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'l10n_ar.import.afip.retenciones',
            'res_id': self.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def generate(self):
        for retencion in self.invoice_ids:
            ret = self.env['l10n_ar.impuestos.deduccion'].create({
                'state': 'available',
                'tax': 'iva',             # TODO: convertir este valor
                'type': 'iva_percepcion', # TODO: convertir este valor
                'date': retencion.date,
                'amount': retencion.total,
                'cuit': retencion.cuit,
            })
            _logger.info("Retencion: {}".format(ret))

            # TODO: generar linea de percepcion IVA
            comp = retencion.invoice_id
            
            if comp:

                # Pasar a borrador para poder editar
                # TODO: bug que vuelve a default el valor fijo de las percepciones 
                posted = comp.state == 'posted'
                if posted:
                    comp.button_draft()

                _logger.info("Comprobante: {}".format(comp))
                _logger.info("Old Line IDs: {}".format(comp.line_ids))
                _logger.info("Old Total: {}".format(comp.amount_total))

                perc_iva = self.env['account.tax'].search([
                    ('name', '=', "Percepción IVA Sufrida")
                ])
                _logger.info("PercepcionIVA: {}".format(perc_iva))

                line = comp.invoice_line_ids[0]
                line.tax_ids += perc_iva

                # Actualizar factura
                # TODO: revisar que no interfiera con los otros impuestos
                # Revisar funcion "_recompute_dynamic_lines" y no asignar valor por defecto
                # a un impuesto ya asignado
                comp._recompute_dynamic_lines(recompute_all_taxes=True)
                comp._recompute_payment_terms_lines()
                comp._compute_amount()

                # Obtener linea de percepcion IVA
                iva_line = comp.line_ids.filtered(lambda line: line.tax_line_id.id == perc_iva.id)

                perc = retencion.total
                if perc >= 0:
                    comp.write({'line_ids': [(1, iva_line.id, { 
                        'debit': perc, 
                        'credit': 0, 
                        'amount_currency': perc,
                    })]})
                else:
                    comp.write({'line_ids': [(1, iva_line.id, { 
                        'debit': 0, 
                        'credit': -perc, 
                        'amount_currency': -perc,
                    })]})

                _logger.info("NewNew Total: {}".format(comp.amount_total))

                # Volver al estado confirmado
                if posted:
                    comp.action_post()
