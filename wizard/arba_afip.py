# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
import logging
import csv
import io
import base64
import datetime

_logger = logging.getLogger(__name__)

try:
    import xlrd
    try:
        from xlrd import xlsx
    except ImportError:
        xlsx = None
except ImportError:
    xlrd = xlsx = None

# https://www.odoo.com/es_ES/forum/ayuda-1/how-can-i-log-all-sql-queries-to-a-file-895

FIELDS_RECURSION_LIMIT = 2

# TODO: traducir "file seems to have no content."
# TODO: mostrar como warning los registros ya existentes
#  - El valor del campo "name" ya existe (probablemente sea "Nombre de la compañía" en el modelo actual). en 2 diferentes filas:
#  - Fila2 (Cliente Uno)
#  - Fila3 (Diego Moreno)
# TODO: Traducir "This is a preview of the first 10 rows of your file"
# TODO: Soportar carga masiva por "Consultar CUIT" y definir que campo
# Override base_import/models/base_import.py
class BaseImport(models.TransientModel):
    _inherit = 'base_import.import'

    # read_file calls dynamically to read_xls
    # read_xls calls to read_xls_book

    # get_fields(self, model, depth=FIELDS_RECURSION_LIMIT):
    # TODO: Basado en el modelo, deberia devolverse un set predeterminado de campos

    def get_fields(self, model, depth=FIELDS_RECURSION_LIMIT):
        depth = super(BaseImport, self).get_fields(model, depth)

        print("[base_import.import] get_fields: {} campos encontrados para el model {}".format(len(depth), model))
        return depth
        

    def _read_xls_book(self, book, sheet_name):
        print("PARSING BOOK")

        sheet = book.sheet_by_name(sheet_name)

        start = 1
        # start = 5

        # emulate Sheet.get_rows for pre-0.9.4
        for rowx, row in enumerate(map(sheet.row, range(sheet.nrows)), 1):
            if rowx < start or rowx > 100:
                continue

            values = []
            for colx, cell in enumerate(row, 1):
                if cell.ctype is xlrd.XL_CELL_NUMBER:
                    is_float = cell.value % 1 != 0.0
                    values.append(
                        str(cell.value)
                        if is_float
                        else str(int(cell.value))
                    )
                elif cell.ctype is xlrd.XL_CELL_DATE:
                    is_datetime = cell.value % 1 != 0.0
                    # emulate xldate_as_datetime for pre-0.9.3
                    dt = datetime.datetime(*xlrd.xldate.xldate_as_tuple(cell.value, book.datemode))
                    values.append(
                        dt.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                        if is_datetime
                        else dt.strftime(DEFAULT_SERVER_DATE_FORMAT)
                    )
                elif cell.ctype is xlrd.XL_CELL_BOOLEAN:
                    values.append(u'True' if cell.value else u'False')
                elif cell.ctype is xlrd.XL_CELL_ERROR:
                    raise ValueError(
                        _("Invalid cell value at row %(row)s, column %(col)s: %(cell_value)s") % {
                            'row': rowx,
                            'col': colx,
                            'cell_value': xlrd.error_text_from_code.get(cell.value, _("unknown error code %s", cell.value))
                        }
                    )
                else:
                    values.append(cell.value)
            if any(x for x in values if x.strip()):
                print("ROW", values)
                yield values

    def do(self, fields, columns, options, dryrun=False):
        print(fields)
        print(columns)
        print(options)
        print(dryrun)

        return super(BaseImport, self).do(fields, columns, options, dryrun)

        return {
            'messages': [{
                'type': 'error',
                'message': 'Not implemented yet',
                'record': False,
            }]
        }

# TODO: Crear asistente para importar todo junto


class IngresosBrutosReport(models.AbstractModel):
    _name = 'l10n_ar.arba.iibb_report'

    def _get_report_values(self, docids, data=None):
        print("RENDERING", docids)
        # get the report action back as we will need its data
        # report = self.env['ir.actions.report']._get_report_from_name('module.report_name')
        # get the records selected for this rendering of the report
        # obj = self.env[report.model].browse(docids)
        # return a custom rendering context
        return {
            'name': 'Hernan', #docids.get_lines()
        }

class AccountMove(models.Model):
    _inherit = 'account.move'

    # invoice_partner_display_name = fields.Char(string="Proveedor")

    arba_cuit = fields.Char(string='CUIT', related='partner_id.vat')
    arba_pos_number = fields.Char(string="Punto de Venta", compute="_compute_arba_pos_number")
    arba_invoice_number = fields.Char(string="Num. de Factura", compute="_compute_arba_invoice_number")
    arba_iibb = fields.Monetary(string="Percepcion IIBB", compute="_compute_arba_iibb")

    amount_total_unsigned = fields.Monetary(string="Total", compute="_compute_amount_total_unsigned")
    amount_subtotal_unsigned = fields.Monetary(string="Subtotal", compute="_compute_amount_subtotal_unsigned")

    def _check_balanced(self):
        # TODO: remove this
        # print('Checking BALANCE')
        pass
    
    @api.depends('name')
    def _compute_arba_pos_number(self):
        for p in self:
            p.arba_pos_number = p.name[-14:-9]

    @api.depends('name')
    def _compute_arba_invoice_number(self):
        for p in self:
            p.arba_invoice_number = p.name[-8:]

    @api.depends('invoice_line_ids', 'invoice_line_ids.tax_ids')
    def _compute_arba_iibb(self):
        # Always assign a value to a computed field.
        # https://www.odoo.com/es_ES/forum/ayuda-1/getting-issue-in-compute-field-for-integer-field-in-odoo-13-177264
        self.arba_iibb = 0
        
        for p in self:
            for tax in p.invoice_line_ids.tax_ids:
                if tax.name == "Percepción IIBB ARBA Sufrida":
                    # Contiene IIBB, buscar movimiento asociado
                    line = p.line_ids.filtered(lambda line: line.tax_line_id.id == tax.id)
                    p.arba_iibb = line.amount_currency

    @api.depends('amount_total_signed')
    def _compute_amount_total_unsigned(self):
        for p in self:
            if p.amount_total_signed > 0:
                p.amount_total_unsigned = p.amount_total_signed
            else:
                p.amount_total_unsigned = -p.amount_total_signed
    
    @api.depends('amount_total_unsigned', 'arba_iibb')
    def _compute_amount_subtotal_unsigned(self):
        for p in self:
            p.amount_subtotal_unsigned = p.amount_total_unsigned - p.arba_iibb

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'
    
    import_id = fields.Many2one(comodel_name="gob.ar.afip.upload", ondelete="cascade")

class InvoiceLine(models.Model):
    _name = 'l10n_ar.invoice_line'
    _description = 'Factura importada de AFIP'
    _order = "cuit asc, date asc, id"

    # TODO: parse date
    # datetime.datetime.strptime('02/01/2021', '%d/%m/%Y').strftime('%a %b %d %Y')
    date = fields.Date(string="Fecha")
    invoice_type = fields.Char(string="Tipo de Comprobante")
    pos_number = fields.Char(string="Punto de Venta")
    invoice_number = fields.Char(string="N° Factura")
    cuit = fields.Char(string="CUIT")
    vendor = fields.Char(string="Proveedor")
    taxed_amount = fields.Float(string="Gravado")
    untaxed_amount = fields.Float(string="No Gravado")
    exempt_amount = fields.Float(string="Exento")
    iva = fields.Float(string="IVA")
    percepcion_iibb = fields.Float(string="Perc. IIBB")
    total = fields.Float(string="Total")
    import_id = fields.Many2one(comodel_name="gob.ar.afip.upload", ondelete="cascade", invisible=True)

    @api.depends('taxed_amount', 'iva', 'percepcion_iibb', 'untaxed_amount', 'total')
    def compute_difference(self):
        for line in self:
            line.difference = line.total - (line.taxed_amount + line.iva + line.percepcion_iibb + line.untaxed_amount)

    @api.depends('difference')
    def compute_needs_attention(self):
        for line in self:
            line.needs_attention = line.difference > 0.01 or line.difference < -0.01
    
    @api.depends('invoice_type', 'pos_number', 'invoice_number')
    def _compute_invoice_display_name(self):
        for line in self:
            line.invoice_display_name = "{} {}-{}".format(line.invoice_type, line.pos_number, line.invoice_number)

    difference = fields.Float(string="Diferencia", compute=compute_difference)
    needs_attention = fields.Boolean(string="Necesita Accion", compute="compute_needs_attention", invisible=True)
    invoice_display_name = fields.Char(string="Comprobante", compute="_compute_invoice_display_name", invisible=True)

# TODO: Usar modelo de Odoo para hacer esta traduccion
# TODO: No repetir este codigo
def helper_convert_invoice_type(afip_invoice_type):
    if afip_invoice_type == '1 - Factura A':
        return "FA-A"
    if afip_invoice_type == '2 - Nota de Débito A':
        return "ND-A"
    if afip_invoice_type == '3 - Nota de Crédito A':
        return "NC-A"
    if afip_invoice_type == '4 - Recibo A':
        return "RE-A"
    if afip_invoice_type == '6 - Factura B':
        return "FA-B"
    if afip_invoice_type == '7 - Nota de Débito B':
        return "ND-B"
    if afip_invoice_type == '8 - Nota de Crédito B':
        return "NC-B"
    if afip_invoice_type == '9 - Recibo B':
        return "RE-B"
    if afip_invoice_type == '11 - Factura C':
        return 'FA-C'
    if afip_invoice_type == '12 - Nota de Débito C':
        return 'ND-C'
    if afip_invoice_type == '13 - Nota de Crédito C':
        return 'NC-C'
    if afip_invoice_type == '15 - Recibo C':
        return 'RE-C'
    
    raise UserError('Tipo de Comprobante invalido: {}'.format(afip_invoice_type))

class ImpuestosImporter(models.Model):
    _name = 'gob.ar.afip.upload'
    _description = 'Importar deducciones de AFIP'

    afip_file = fields.Binary(string="Archivo de Compras AFIP (*.csv)")
    iibb_file = fields.Binary(string="Archivo de Percepciones IIBB (*.txt)")
    fix_difference = fields.Boolean(string="Computar diferencias como No Gravado", default=True)
    
    invoice_ids = fields.One2many(string="Facturas", comodel_name="l10n_ar.invoice_line", inverse_name="import_id")
    notes = fields.Char(string="Notas", readonly=True)    

    def compute_sheet(self):

        [data] = self.read()

        if not data['afip_file']:
            raise UserError("Debes cargar un archivo de compras de AFIP")

        if not data['iibb_file']:
            raise UserError("Debes cargar un archivo de percepciones de IIBB")

        # TODO: Chequear esto
        self.invoice_ids.write([(5, 0, 0)])

        # Leer archivo AFIP de compras
        file_content = base64.decodestring(data['afip_file'])
        csvfile = io.StringIO(file_content.decode("utf-8"))
        
        # Omitir primera linea (cabecera) del archivo
        next(csvfile)

        # Leer archivo ARBA de percepciones de IIBB sufridas
        iibb_content = base64.decodestring(data['iibb_file'])
        iibb = io.StringIO(iibb_content.decode("utf-8"))
        
        percepciones = dict()

        # Computar percepciones de IIBB
        for x in iibb:
            percepcion = { 
                "cuit": x[:13], 
                "fecha": x[13:23], 
                "tipo_comprobante": x[23:24], 
                "letra_comprobante": x[24:25], 
                "numero_sucursal": x[25:29], 
                "numero_emision": x[29:37], 
                "importe_percepcion": x[37:48].replace(",", ".")
            }
            percepciones[percepcion["numero_sucursal"] + "-" + percepcion["numero_emision"]] = percepcion

        spamreader = csv.reader(csvfile, delimiter=',', quotechar='"', )
        # print('Fecha, Tipo, Punto de Venta, Numero, CUIT, Denominacion, Imp. Neto Gravado, IVA, Imp. Total, Percepcion ARBA')
        
        count = 0

        # Computar Mis Comprobantes Recibidos AFIP
        for row in spamreader:
            num = row[2].zfill(5) + "-" + row[3].zfill(8)
            
            # Obtener percepcion de IIBB si existe
            perc = percepciones.pop(num, None)

            # Calcular importe de percepcion
            imp = float(perc["importe_percepcion"]) if perc else 0
            
            # TODO: borrar registros viejos la segunda vez que se carga

            _logger.info("LINE: {} - {}".format(row, row[1]))

            # Crear linea de compra en el wizard
            wizard_invoice_line = self.env['l10n_ar.invoice_line'].create({ 
                'date': datetime.datetime.strptime(row[0], '%d/%m/%Y'),
                'invoice_type': helper_convert_invoice_type(row[1]),
                'pos_number': row[2].zfill(5),
                'invoice_number': row[3].zfill(8),
                'cuit': row[7],
                'vendor': row[8],
                'taxed_amount': row[11], 
                'untaxed_amount': row[12],
                'exempt_amount': row[13],
                'iva': row[14],
                'percepcion_iibb': imp,
                'total': row[15],
                'import_id': self.id,
            })

            count += 1

        facturas_con_diferencia = 0
        perc_sin_factura = 0

        for invoice in self.invoice_ids:
            if invoice.needs_attention:
                # invoice.untaxed_amount = invoice.difference
                facturas_con_diferencia += 1

        # TODO: Agregar lineas para los que tienen solo percepciones pero no aparecen en AFIP
        print("------------ PERCEPCIONES PENDIENTES INICIO ------------")
        for p in percepciones.items():
            perc_sin_factura += 1
            print(p[1]["fecha"], p[1]["tipo_comprobante"] + p[1]["letra_comprobante"], p[0], p[1]["cuit"], "", "", "", "", "", p[1]["importe_percepcion"], sep=",")
        print("------------ PERCEPCIONES PENDIENTES FIN ------------")
        # { 'description': 'Varios', 'price_unit': 0, iva: 'IVA No Corresponde' + 'Percepcion IIBB' }

        self.notes = """{} facturas cargadas correctamente.
{} de ellas contienen diferencias entre los diferentes montos y el total.

NOTA: Existen {} percepciones que no tienen factura correspondiente.""".format(count, facturas_con_diferencia, perc_sin_factura)
        
        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'gob.ar.afip.upload',
            'res_id': self.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }
        # return {'type': 'ir.actions.act_window_close'}
    
    def generate_data(self):
        [data] = self.read()

        # Obtener tipo de identificacion CUIT
        cuit_type = self.env['l10n_latam.identification.type'].search([('name', '=', 'CUIT')])
        if len(cuit_type) != 1:
            raise UserError("Debe haber cargado un tipo de identificacion llamada CUIT")
        cuit_type = cuit_type[0]
            
        # Obtener tipo de responsabilidad AFIP Responsable Inscripto
        # TODO: Dependiendo el tipo de factura, cargar como RI o Monotributo
        afip_resp_inscripto_type = self.env['l10n_ar.afip.responsibility.type'].search([('name', '=', 'IVA Responsable Inscripto')])
        if len(afip_resp_inscripto_type) != 1:
            raise UserError("Debe haber cargado un tipo de responsabilidad AFIP 'IVA Responsable Inscripto'")
        afip_resp_inscripto_type = afip_resp_inscripto_type[0]

        # Obtener impuesto de Percepcion IIBB 
        iibb = self.env['account.tax'].search([('name', '=', "Percepción IIBB ARBA Sufrida")])
        if (len(iibb)) != 1:
            raise UserError("Debe haber cargado un tipo de impuesto 'Percepción IIBB ARBA Sufrida'")
        iibb = iibb[0]

        for invoice in self.invoice_ids:
            # Compute difference as untaxed
            if invoice.needs_attention:
                invoice.untaxed_amount = invoice.difference

            # Get or Create Vendor Partner (res.partner)
            partner = self.env['res.partner'].search([('vat', '=', invoice.cuit)])
            partner_data = { 
                'type': 'contact',
                'name': invoice.vendor,
                'vat': invoice.cuit,
                'l10n_latam_identification_type_id': cuit_type.id,
                'l10n_ar_afip_responsibility_type_id': afip_resp_inscripto_type.id
            }
            if len(partner) == 0:
                # Crear nuevo proveedor
                partner = self.env['res.partner'].create(partner_data)
            else:
                # Actualizar datos del proveedor
                partner = partner[0]
                partner.write(partner_data)
            
            print("Partner", partner)
            
            # Crear/Obtener Orden de Compra (purchase.order)
            purchaseName = 'Compra {}-{}'.format(invoice.pos_number, invoice.invoice_number)
            purchase = self.env['purchase.order'].search([('partner_ref', '=', purchaseName)])
            purchase_data = {
                'partner_ref': purchaseName,
                'date_planned': invoice.date,
                'partner_id': partner.id,
                'import_id': self.id,
            }
            # TODO: No actualizar una compra ya existente
            purchase = self.env['purchase.order'].create(purchase_data)

            print("Purchase", purchase)

            # Crear Linea de Factura (purchase.order.line)
            line = self.env['purchase.order.line'].search([('order_id', '=', purchase.id)])
            line_data = {
                'name': 'Compra de Mercaderia',
                'product_qty': 1,
                'product_uom': 1,
                'price_unit': invoice.taxed_amount,
                'currency_id': 19, # TODO: Get currency ID
                'price_subtotal': invoice.taxed_amount, # TODO: restar del total las percepciones y el IVA para obtener este valor
                'price_tax': invoice.iva,
                'price_total': invoice.total,
                'qty_received': 1,
                'qty_received_manual': 1,
                'order_id': purchase.id,
                'partner_id': partner.id,
                'product_id': 1, # TODO: obtener producto "Compras Varias"
            }
            if len(line) == 0:
                # Crear Linea de Compra
                line = self.env['purchase.order.line'].create(line_data)
            else:
                # Actualizar Linea de Compra
                line = line[0]
                line.write(line_data)

            print("Purchase Line", line)

            # Agregar linea de compra para valor no gravado
            if invoice.untaxed_amount > 0:
                print("Creando linea de compra para no gravado", invoice.untaxed_amount)
                line_data = {
                    'name': 'Compra - Monto No Gravado',
                    'product_qty': 1,
                    'product_uom': 1,
                    'price_unit': invoice.untaxed_amount,
                    'currency_id': 19, # TODO: Get currency ID
                    'price_subtotal': invoice.untaxed_amount, # TODO: restar del total las percepciones y el IVA para obtener este valor
                    # 'price_tax': invoice.iva,
                    'price_total': invoice.untaxed_amount,
                    'qty_received': 1,
                    'qty_received_manual': 1,
                    'order_id': purchase.id,
                    'partner_id': partner.id,
                    'product_id': 2, # TODO: obtener producto "Compra No Gravada"
                }

                print(line_data)
                line_untaxed = self.env['purchase.order.line'].create(line_data)
                print("Creada linea de compra no gravada", invoice.untaxed_amount, line_untaxed)

            # Confirmar compra si esta en borrador
            if purchase.state == 'draft':
                purchase.button_confirm()

            # Agregar percepción IIBB
            line.taxes_id += iibb

            # Create Invoice
            if (len(purchase.invoice_ids) == 0):
                print("Crear factura...")
                purchase.action_create_invoice()            

            # Obtener linea de percepcion IIBB
            iibb_line = purchase.invoice_ids.line_ids.filtered(lambda line: line.tax_line_id.id == iibb.id)
            
            # Actualizar valor de percepcion IIBB
            if invoice.percepcion_iibb >= 0:
                purchase.invoice_ids.write({'line_ids': [(1, iibb_line.id, { 
                    'debit': invoice.percepcion_iibb, 
                    'credit': 0, 
                    'amount_currency': invoice.percepcion_iibb,
                })]})
            else:
                purchase.invoice_ids.write({'line_ids': [(1, iibb_line.id, { 
                    'debit': 0, 
                    'credit': -invoice.percepcion_iibb, 
                    'amount_currency': -invoice.percepcion_iibb,
                })]})

            # TODO: actualizar valor de IVA por posible error de redondeo

            # Establecer fecha de factura
            purchase.invoice_ids.invoice_date = invoice.date
            purchase.invoice_ids.date = invoice.date

            # Actualizar factura (modifica valor de pago a proveedores)
            purchase.invoice_ids._recompute_payment_terms_lines()

            # Establecer tipo de comprobante
            doc_type = self.env['l10n_latam.document.type'].search([('doc_code_prefix', '=', invoice.invoice_type)])
            purchase.invoice_ids.l10n_latam_document_type_id = doc_type

            # Establecer numero de comprobante 
            purchase.invoice_ids.l10n_latam_document_number = '{}-{}'.format(invoice.pos_number, invoice.invoice_number)

            # Publicar Factura si esta en estado borrador
            if False:
                if (purchase.invoice_ids.state == "draft"):
                    if invoice.needs_attention:
                        print("Marcando factura con diferencia para revisar", invoice.pos_number, invoice.invoice_number)
                    else:
                        purchase.invoice_ids.action_post()

            # TODO: en la UI sigue apareciendo el valor viejo de IIBB

            # TODO: Registrar Pago
            # account.payment.register => action_create_payments({
            #   'journal_id': 2            # Diario Banco/Efectivo
            #   'amount': 60.50            # Monto
            #   'payment_date': date.Now() # Fecha de Pago
            # })

            # TODO: remove this
            break

        # TODO: Redirigir a la vista de los elementos creados
        # Mantenerse en la misma vista del asistente
        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'gob.ar.afip.upload',
            'res_id': self.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }
