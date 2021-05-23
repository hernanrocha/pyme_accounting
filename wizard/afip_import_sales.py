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

# from odoo.addons.custom_addon_name.models.py_file_name import IMPORT_LIST
# TODO: No repetir este codigo
def helper_convert_invoice_type(afip_invoice_type):
    if afip_invoice_type == '6 - Factura B':
        return "FA-B"
    if afip_invoice_type == '8 - Nota de Crédito B':
        return "NC-B"
    if afip_invoice_type == '11 - Factura C':
        return 'FA-C'

# TODO: La informacion de este archivo esta repetida
class ImportSalesAfipLine(models.TransientModel):
    _name = "l10n_ar.afip.import_sale.line"
    _description = "Linea de venta de AFIP"

    date = fields.Date(string="Fecha")
    invoice_type = fields.Char(string="Tipo de Comprobante")
    pos_number = fields.Char(string="Punto de Venta")
    invoice_number = fields.Char(string="N° Factura")
    cuit = fields.Char(string="CUIT")
    partner = fields.Char()
    taxed_amount = fields.Float(string="Gravado")
    untaxed_amount = fields.Float(string="No Gravado")
    excempt_amount = fields.Float(string="Exento")
    iva = fields.Float(string="IVA")
    total = fields.Float(string="Total")
    import_id = fields.Many2one(comodel_name="l10n_ar.afip.import_sale", ondelete="cascade")

    invoice_display_name = fields.Char(string="Comprobante", compute="_compute_invoice_display_name", invisible=True)

    @api.depends('invoice_type', 'pos_number', 'invoice_number')
    def _compute_invoice_display_name(self):
        for line in self:
            line.invoice_display_name = "{} {}-{}".format(line.invoice_type, line.pos_number, line.invoice_number)


    @api.depends('taxed_amount', 'iva', 'total')
    def compute_difference(self):
        for line in self:
            line.difference = line.total - (line.taxed_amount + line.iva)

    difference = fields.Float(string="Diferencia", compute=compute_difference)

# El metodo parse_sales esta repetido
class ImportSalesAfip(models.TransientModel):
    _name = "l10n_ar.afip.import_sale"
    _description = "Importar ventas de AFIP"
    
    afip_file = fields.Binary(string="Ventas AFIP (*.csv)")
    invoice_ids = fields.One2many(string="Facturas", comodel_name="l10n_ar.afip.import_sale.line", inverse_name="import_id")

    notes = fields.Char(string="Notas", readonly=True)
    
    # TODO: genera problemas de seguridad
    # @api.onchange('afip_file')
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
        total_amount = 0

        # Computar ventas AFIP
        for row in spamreader:
                        
            # Crear linea de venta en el wizard
            line = self.env['l10n_ar.afip.import_sale.line'].create({ 
                'date': datetime.datetime.strptime(row[0], '%d/%m/%Y'),
                'invoice_type': helper_convert_invoice_type(row[1]),
                'pos_number': row[2].zfill(4),
                'invoice_number': row[3].zfill(8),
                'cuit': row[7],
                'partner': row[8],
                'taxed_amount': row[11], 
                'untaxed_amount': row[12],
                'excempt_amount': row[13],
                'iva': row[14],
                'total': row[15],
                'import_id': self.id,
            })

            count += 1
            total_amount += line.total

        self.notes = "{} facturas cargadas correctamente. Total: ${}".format(count, total_amount)
        
        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'l10n_ar.afip.import_sale',
            'res_id': self.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def generate_sales(self):
        consumidor_final = self.env['res.partner'].search([('name', '=', 'Consumidor Final Anónimo')])
        print("CONSUMIDOR FINAL", consumidor_final) 

        # TODO: Obtener/Crear diario segun el PdV
        # TODO: Crear vista de Puntos de Venta en AFIP (opcion a traerlos configurandolo)
        journal_id = 19

        for invoice in self.invoice_ids:
            
            # TODO: Permitir elegir que hacer con la diferencia
            invoice.untaxed_amount = invoice.difference

            if invoice.cuit:
                # Get or Create Customer Partner (res.partner)
                partner = self.env['res.partner'].search([('vat', '=', invoice.cuit)])
                partner_data = { 
                    'type': 'contact',
                    'name': invoice.partner, # TODO: rename this
                    # TODO: set CUIT Consumidor final (20000000003)
                    # 'vat': invoice.cuit,
                    # 'l10n_latam_identification_type_id': cuit_type.id,
                    # 'l10n_ar_afip_responsibility_type_id': afip_resp_inscripto_type.id
                }
                if len(partner) == 0:
                    # Crear nuevo cliente
                    partner = self.env['res.partner'].create(partner_data)
                else:
                    # Actualizar datos del cliente
                    partner = partner[0]
                    partner.write(partner_data)
            else:
                partner = consumidor_final
            
            print("Partner", partner)
            
            # Crear Orden de Venta (sale.order)
            sale_data = {
                'date_order': invoice.date,
                'partner_id': partner.id,
            }
            sale = self.env['sale.order'].create(sale_data)

            print("Sale", sale)

            # TODO: Revisar tambien montos gravados y exentos 

            # Crear Linea de Factura (sale.order.line) con monto No Gravado
            line = self.env['sale.order.line'].search([('order_id', '=', sale.id)])
            line_data = {
                'name': 'Venta No Gravada',
                'product_uom_qty': 1,
                # 'product_uom': 1,
                'price_unit': invoice.untaxed_amount,
                'currency_id': 19, # TODO: Get currency ID
                'price_subtotal': invoice.untaxed_amount, # TODO: restar del total las percepciones y el IVA para obtener este valor
                'price_tax': invoice.iva, # TODO: buscar IVA 0%
                'price_total': invoice.total,
                'qty_delivered': 1,
                # 'qty_received_manual': 1,
                'order_id': sale.id,
                # 'partner_id': partner.id,
                'product_id': 2, # TODO: obtener producto "Ventas Varias (No Gravado)"
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
                sale.action_confirm()

            # Create Invoice
            if (len(sale.invoice_ids) == 0):
                print("Crear factura...")
                sale._create_invoices() # TODO: definir si es este el metodo            

            # TODO: actualizar valor de IVA por posible error de redondeo

            # Establecer fecha de factura
            sale.invoice_ids.invoice_date = invoice.date
            sale.invoice_ids.date = invoice.date

            # Actualizar factura (modifica valor de pago a proveedores)
            # TODO: creo que esto no es necesario
            # sale.invoice_ids._recompute_payment_terms_lines()

            # TODO: Establecer tipo de comprobante. Primero hay que cambiar a monotributo
            # doc_type = self.env['l10n_latam.document.type'].search([('doc_code_prefix', '=', invoice.invoice_type)])
            # sale.invoice_ids.l10n_latam_document_type_id = doc_type

            # TODO: Revisar numero de secuencia (Y punto de venta usado)
            # Establecer numero de comprobante
            sale.invoice_ids.l10n_latam_document_number = '{}-{}'.format(invoice.pos_number, invoice.invoice_number)

            # Publicar Factura si esta en estado borrador
            if (sale.invoice_ids.state == "draft"):
                sale.invoice_ids.action_post()

            # TODO: que pasa si faltan facturas?? al ser correlativas deberian coincidir

            # TODO: en la UI sigue apareciendo el valor viejo de IIBB

            # TODO: Registrar Pago
            # account.payment.register => action_create_payments({
            #   'journal_id': 2            # Diario Banco/Efectivo
            #   'amount': 60.50            # Monto
            #   'payment_date': date.Now() # Fecha de Pago
            # })

        # TODO: retornar a ventana con el filtro de las facturas hechas recientemente

        # # Mantenerse en la misma vista del asistente
        # return {
        #     'context': self.env.context,
        #     'view_type': 'form',
        #     'view_mode': 'form',
        #     'res_model': 'l10n_ar.afip.import_sale',
        #     'res_id': self.id,
        #     'view_id': False,
        #     'type': 'ir.actions.act_window',
        #     'target': 'new',
        # }

