# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging
import csv
import io
import base64
import datetime

_logger = logging.getLogger(__name__)

# https://www.odoo.com/es_ES/forum/ayuda-1/how-can-i-log-all-sql-queries-to-a-file-895

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

    arba_cuit = fields.Char(string="CUIT", compute="_compute_arba_cuit")
    arba_pos_number = fields.Char(string="Punto de Venta", compute="_compute_arba_pos_number")
    arba_invoice_number = fields.Char(string="Num. de Factura", compute="_compute_arba_invoice_number")
    arba_iibb = fields.Monetary(string="Percepcion IIBB", compute="_compute_arba_iibb")

    amount_total_unsigned = fields.Monetary(string="Total", compute="_compute_amount_total_unsigned")
    amount_subtotal_unsigned = fields.Monetary(string="Subtotal", compute="_compute_amount_subtotal_unsigned")

    def _check_balanced(self):
        print('Checking BALANCE')
    
    @api.depends('partner_id', 'partner_id.vat')
    def _compute_arba_cuit(self):
        for p in self:
            p.arba_cuit = p.partner_id.vat
    
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
                    print("Buscando linea de IIBB")
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

    # TODO: parse date
    # datetime.datetime.strptime('02/01/2021', '%d/%m/%Y').strftime('%a %b %d %Y')
    date = fields.Date(string="Fecha")
    pos_number = fields.Char(string="Punto de Venta")
    invoice_number = fields.Char(string="N° Factura")
    cuit = fields.Char(string="CUIT")
    vendor = fields.Char(string="Proveedor")
    taxed_amount = fields.Float(string="Gravado")
    untaxed_amount = fields.Float(string="No Gravado")
    excempt_amount = fields.Float(string="Exento")
    iva = fields.Float(string="IVA")
    percepcion_iibb = fields.Float(string="Perc. IIBB")
    total = fields.Float(string="Total")
    import_id = fields.Many2one(comodel_name="gob.ar.afip.upload", ondelete="cascade")

    @api.depends('taxed_amount', 'iva', 'percepcion_iibb', 'total')
    def compute_difference(self):
        for line in self:
            line.difference = line.total - (line.taxed_amount + line.iva + line.percepcion_iibb)

    @api.depends('difference')
    def compute_needs_attention(self):
        for line in self:
            line.needs_attention = line.difference > 0.01 or line.difference < -0.01

    difference = fields.Float(string="Diferencia", compute=compute_difference)
    needs_attention = fields.Boolean(string="Necesita Accion", compute="compute_needs_attention")

class ImpuestosImporter(models.Model):
    _name = 'gob.ar.afip.upload'
    _description = 'Importar deducciones de AFIP'

    afip_file = fields.Binary(string="Compras AFIP (*.csv)")
    iibb_file = fields.Binary(string="Percepciones IIBB (*.txt)")
    notes = fields.Char(string="Notas", readonly=True)
    invoice_ids = fields.One2many(string="Facturas", comodel_name="l10n_ar.invoice_line", inverse_name="import_id")
    purchase_ids = fields.One2many(string="Compras", comodel_name="purchase.order", inverse_name="import_id")

    iibb_report_date_from = fields.Date(string="Fecha Inicio")
    iibb_report_date_to = fields.Date(string="Fecha Fin")

    # TODO: obtain default currency_id=19
    # TODO: tener en cuenta el minimo ($615 en este caso)
    iibb_report_sale_total = fields.Float(string="Total de Ventas")
    iibb_report_tax_percentage = fields.Selection(string="Alicuota", selection=[('1.50', '1.50%')])
    
    iibb_report_tax_subtotal = fields.Float(string="Impuesto Determinado", compute="_compute_iibb_report_tax_subtotal")
    
    iibb_report_deducciones = fields.Float(string="Deducciones")
    iibb_report_tax_prev_saldo = fields.Float(string="Saldo a favor del periodo anterior")

    iibb_report_tax_total_saldo = fields.Float(string="Saldo a favor del período", compute="_compute_iibb_report_tax_total_saldo")
    iibb_report_tax_total_to_pay = fields.Float(string="Saldo a Pagar", compute="_compute_iibb_report_tax_total_to_pay")

    def calculate_iibb(self):
        # TODO: tener en cuenta notas de credito/debito
        # TODO: cancelar las facturas pendientes (state=draft)

        # Buscar Facturas de Compras
        in_invoices = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('date', '>=', self.iibb_report_date_from),
            ('date', '<=', self.iibb_report_date_to)
        ])
        print(len(in_invoices), in_invoices)

        # Buscar Facturas de Ventas
        out_invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('date', '>=', self.iibb_report_date_from),
            ('date', '<=', self.iibb_report_date_to)
        ])
        print(len(out_invoices), out_invoices)

        # Ventas
        ventas = 0
        for invoice in out_invoices:
            ventas += invoice.amount_total
        self.iibb_report_sale_total = ventas

        deducciones = 0
        for invoice in in_invoices:
            deducciones += invoice.arba_iibb
        # TODO poner negativo?
        self.iibb_report_deducciones = -deducciones

        # TODO: calcular saldo del periodo anterior

        # TODO: crear helper para mantenerse en la misma ventana o revisar los recalculate existentes
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

    @api.depends('iibb_report_sale_total', 'iibb_report_tax_percentage')
    def _compute_iibb_report_tax_subtotal(self):
        for p in self:
            p.iibb_report_tax_subtotal = p.iibb_report_sale_total * float(p.iibb_report_tax_percentage) / 100

    @api.depends('iibb_report_tax_subtotal', 'iibb_report_tax_prev_saldo', 'iibb_report_deducciones')
    def _compute_iibb_report_tax_total_saldo(self):
        self.iibb_report_tax_total_saldo = 0
        for p in self:
            saldo = p.iibb_report_tax_subtotal + p.iibb_report_tax_prev_saldo + p.iibb_report_deducciones
            if saldo <= 0:
                p.iibb_report_tax_total_saldo = saldo

    @api.depends('iibb_report_tax_subtotal', 'iibb_report_tax_prev_saldo', 'iibb_report_deducciones')
    def _compute_iibb_report_tax_total_to_pay(self):
        self.iibb_report_tax_total_to_pay = 0
        for p in self:
            saldo = p.iibb_report_tax_subtotal + p.iibb_report_tax_prev_saldo + p.iibb_report_deducciones
            if saldo > 0:
                p.iibb_report_tax_total_to_pay = saldo

    def compute_sheet(self):
        [data] = self.read()

        if not data['afip_file']:
            raise UserError("Debes cargar un archivo de compras de AFIP")

        if not data['iibb_file']:
            raise UserError("Debes cargar un archivo de percepciones de IIBB")

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

        # Computar compras AFIP
        for row in spamreader:
            num = row[2].zfill(4) + "-" + row[3].zfill(8)
            
            # Obtener percepcion de IIBB si existe
            perc = percepciones.pop(num, None)

            # Calcular importe de percepcion
            imp = float(perc["importe_percepcion"]) if perc else 0

            # if perc:
            #     imp = float(perc["importe_percepcion"])
            
            # print(row[0], row[1], row[2].zfill(4), row[3].zfill(8), row[7], row[8], row[11], row[14], row[15], imp, sep=",")
            
            # Crear linea de compra en el wizard
            wizard_invoice_line = self.env['l10n_ar.invoice_line'].create({ 
                'date': datetime.datetime.strptime(row[0], '%d/%m/%Y'),
                'pos_number': row[2].zfill(4),
                'invoice_number': row[3].zfill(8),
                'cuit': row[7],
                'vendor': row[8],
                'taxed_amount': row[11], 
                'untaxed_amount': row[12],
                'excempt_amount': row[13],
                'iva': row[14],
                'percepcion_iibb': imp,
                'total': row[15],
                'import_id': self.id,
            })

            count += 1

            # TODO: Agregar lineas para los que tienen solo percepciones pero no aparecen en AFIP
            print("------------ PERCEPCIONES PENDIENTES INICIO ------------")
            for p in percepciones.items():
                print(p[1]["fecha"], p[1]["tipo_comprobante"] + p[1]["letra_comprobante"], p[0], p[1]["cuit"], "", "", "", "", "", p[1]["importe_percepcion"], sep=",")
            print("------------ PERCEPCIONES PENDIENTES FIN ------------")

            continue

            # Mark as received (only when stock is installed)
            # picking = self.env['stock.picking'].search([('')])

            # invoice_payment_term_id (account.payment.term)


            # print(purchase.invoice_ids.invoice_line_ids)
            # print(purchase.invoice_ids.invoice_line_ids.tax_ids)
            # iibb_line = purchase.invoice_ids.line_ids.filtered(lambda line: line.tax_line_id.id == iibb.id)

            # purchase.invoice_ids.l10n_latam_document_number = '1-11'

            # print("Line IDs:", purchase.invoice_ids.line_ids)
            # purchase.invoice_ids.line_ids.recompute_tax_line = True
            # purchase.invoice_ids._recompute_tax_lines(True)
            # purchase.invoice_ids._compute_base_line_taxes(purchase.invoice_ids.invoice_line_ids)

            # print("Compute Taxes By Group")
            # purchase.invoice_ids._compute_invoice_taxes_by_group()

            # print("Recomputee")
            # account_tax_repartition_line = 4
            # purchase.invoice_ids._recompute_dynamic_lines(False)
            # purchase.invoice_ids._recompute_dynamic_lines() => _recompute_tax_lines()
            # Cannot create unbalanced journal entry. Ids:
            # print(purchase.invoice_ids.line_ids)

            # _check_balanced
            
            # print(purchase.invoice_ids.line_ids[0].tax_line_id.name)
            # print(purchase.invoice_ids.line_ids[1].tax_line_id.id)
            # print(purchase.invoice_ids.line_ids[2].tax_line_id.id)

            # https://www.odoo.com/es_ES/forum/ayuda-1/many2many-write-replaces-all-existing-records-in-the-set-by-the-ids-148267
            # purchase.invoice_ids.write({'line_ids': [(1, iibb_line.id, { 'debit': 11, 'credit': 0, 'amount_currency': 11 })]})

            # purchase.invoice_ids._onchange_recompute_dynamic_lines()
            # purchase.invoice_ids.write({'line_ids': [(1, iibb_line.id, { 'debit': 11, 'credit': 0, 'amount_currency': 11 })]})
            # print(purchase.invoice_ids._inverse_amount_total())
            # purchase.invoice_ids.write({})
            # purchase.invoice_ids.write({'line_ids': [(1, iibb_line.id, { 'debit': 11, 'credit': 0, 'amount_currency': 11 })]})
            # purchase.invoice_ids._recompute_payment_terms_lines()
            
            # purchase.invoice_ids._recompute_dynamic_lines()
            # purchase.invoice_ids._onchange_recompute_dynamic_lines()
            # purchase.invoice_ids._move_autocomplete_invoice_lines_values()
            # account/static/src/js/tax_group.js => tax-group-custom-field
            # iibb_line._onchange_amount_currency()
            # purchase.invoice_ids._move_autocomplete_invoice_lines_values()
            # purchase.invoice_ids._recompute_tax_lines(True)
            
            # to_check = True
            # _compute_invoice_taxes_by_group => amount_by_group

            # DEBITO: 
            # price_unit, debit, balance, amount_currency, price_subtotal, price_total = 37
            # CREDITO:
            # price_unit, balance, amount_currency, price_subtotal, price_total = -37
            # credit = 37

            # to_check: True ???
            
            # afip_barcode al descargar PDF

        self.notes = "{} facturas cargadas correctamente".format(count)
        
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
            if len(purchase) == 0:
                # Crear nueva orden de compra
                purchase = self.env['purchase.order'].create(purchase_data)
            else:
                # Obtener orden de compra existente
                purchase = purchase[0]

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
                'product_id': 2, # TODO: obtener producto "Compras Varias"
            }
            if len(line) == 0:
                # Crear Linea de Compra
                line = self.env['purchase.order.line'].create(line_data)
            else:
                # Actualizar Linea de Compra
                line = line[0]
                line.write(line_data)

            print("Purchase Line", line)

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
            purchase.invoice_ids.write({'line_ids': [(1, iibb_line.id, { 
                'debit': invoice.percepcion_iibb, 
                'credit': 0, 
                'amount_currency': invoice.percepcion_iibb,
            })]})

            # TODO: actualizar valor de IVA por posible error de redondeo

            # Establecer fecha de factura
            purchase.invoice_ids.invoice_date = invoice.date
            purchase.invoice_ids.date = invoice.date

            # Actualizar factura (modifica valor de pago a proveedores)
            purchase.invoice_ids._recompute_payment_terms_lines()

            # Establecer numero de documento
            purchase.invoice_ids.l10n_latam_document_number = '{}-{}'.format(invoice.pos_number, invoice.invoice_number)

            # Publicar Factura si esta en estado borrador
            if (purchase.invoice_ids.state == "draft"):
                purchase.invoice_ids.action_post()

            # TODO: en la UI sigue apareciendo el valor viejo de IIBB

            # TODO: Registrar Pago
            # account.payment.register => action_create_payments({
            #   'journal_id': 2            # Diario Banco/Efectivo
            #   'amount': 60.50            # Monto
            #   'payment_date': date.Now() # Fecha de Pago
            # })

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

    def parse_sales(self):
        [data] = self.read()

        if not data['afip_file']:
            raise UserError("Debes cargar un archivo de ventas de AFIP")

        # Leer archivo AFIP de ventas
        file_content = base64.decodestring(data['afip_file'])
        csvfile = io.StringIO(file_content.decode("utf-8"))
        
        # Omitir primera linea (cabecera) del archivo
        next(csvfile)

        spamreader = csv.reader(csvfile, delimiter=',', quotechar='"', )
        
        count = 0

        # Computar ventas AFIP
        for row in spamreader:
            # num = row[2].zfill(4) + "-" + row[3].zfill(8)
                        
            # Crear linea de compra en el wizard
            self.env['l10n_ar.invoice_line'].create({ 
                'date': datetime.datetime.strptime(row[0], '%d/%m/%Y'),
                'pos_number': row[2].zfill(4),
                'invoice_number': row[3].zfill(8),
                'cuit': row[7],
                'vendor': row[8],
                'taxed_amount': row[11], 
                'untaxed_amount': row[12],
                'excempt_amount': row[13],
                'iva': row[14],
                # 'percepcion_iibb': imp,
                'total': row[15],
                'import_id': self.id,
            })

            count += 1

        self.notes = "{} facturas cargadas correctamente".format(count)
        
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

    def generate_sales(self):
        for invoice in self.invoice_ids:
            # Get or Create Customer Partner (res.partner)
            partner = self.env['res.partner'].search([('vat', '=', invoice.cuit)])
            partner_data = { 
                'type': 'contact',
                'name': invoice.vendor, # TODO: rename this
                # TODO: set CUIT Consumidor final (20000000003)
                # 'vat': invoice.cuit,
                # 'l10n_latam_identification_type_id': cuit_type.id,
                # 'l10n_ar_afip_responsibility_type_id': afip_resp_inscripto_type.id
            }
            if len(partner) == 0:
                # Crear nuevo proveedor
                partner = self.env['res.partner'].create(partner_data)
            else:
                # Actualizar datos del cliente
                partner = partner[0]
                partner.write(partner_data)
            
            print("Partner", partner)
            
            # Crear/Obtener Orden de Venta (sale.order)
            saleName = 'Venta {}-{}'.format(invoice.pos_number, invoice.invoice_number)
            sale = self.env['sale.order'].search([('partner_ref', '=', saleName)])
            sale_data = {
                'partner_ref': saleName,
                'date_planned': invoice.date,
                'partner_id': partner.id,
                'import_id': self.id,
            }
            if len(sale) == 0:
                # Crear nueva orden de venta
                sale = self.env['sale.order'].create(sale_data)
            else:
                # Obtener orden de venta existente
                sale = sale[0]

            print("Sale", sale)

            # Crear Linea de Factura (sale.order.line)
            line = self.env['sale.order.line'].search([('order_id', '=', sale.id)])
            line_data = {
                'name': 'Venta de Mercaderia',
                'product_qty': 1,
                'product_uom': 1,
                'price_unit': invoice.taxed_amount,
                'currency_id': 19, # TODO: Get currency ID
                'price_subtotal': invoice.taxed_amount, # TODO: restar del total las percepciones y el IVA para obtener este valor
                'price_tax': invoice.iva,
                'price_total': invoice.total,
                'qty_received': 1,
                'qty_received_manual': 1,
                'order_id': sale.id,
                'partner_id': partner.id,
                'product_id': 2, # TODO: obtener producto "Ventas Varias"
            }
            if len(line) == 0:
                # Crear Linea de Venta
                line = self.env['sale.order.line'].create(line_data)
            else:
                # Actualizar Linea de Compra
                line = line[0]
                line.write(line_data)

            print("Sale Line", line)

            # Confirmar compra si esta en borrador
            if sale.state == 'draft':
                sale.button_confirm()

            # Create Invoice
            if (len(sale.invoice_ids) == 0):
                print("Crear factura...")
                sale.action_create_invoice()            

            # TODO: actualizar valor de IVA por posible error de redondeo

            # Establecer fecha de factura
            sale.invoice_ids.invoice_date = invoice.date
            sale.invoice_ids.date = invoice.date

            # Actualizar factura (modifica valor de pago a proveedores)
            sale.invoice_ids._recompute_payment_terms_lines()

            # Establecer numero de documento
            sale.invoice_ids.l10n_latam_document_number = '{}-{}'.format(invoice.pos_number, invoice.invoice_number)

            # Publicar Factura si esta en estado borrador
            if (sale.invoice_ids.state == "draft"):
                sale.invoice_ids.action_post()

            # TODO: en la UI sigue apareciendo el valor viejo de IIBB

            # TODO: Registrar Pago
            # account.payment.register => action_create_payments({
            #   'journal_id': 2            # Diario Banco/Efectivo
            #   'amount': 60.50            # Monto
            #   'payment_date': date.Now() # Fecha de Pago
            # })

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