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
    if afip_invoice_type == '1 - Factura A':
        return "FA-A"
    if afip_invoice_type == '2 - Nota de Débito A':
        return "ND-A"
    if afip_invoice_type == '3 - Nota de Crédito A':
        return "NC-A"
    if afip_invoice_type == '6 - Factura B':
        return "FA-B"
    if afip_invoice_type == '7 - Nota de Débito B':
        return "ND-B"
    if afip_invoice_type == '8 - Nota de Crédito B':
        return "NC-B"
    if afip_invoice_type == '11 - Factura C':
        return 'FA-C'
    if afip_invoice_type == '12 - Nota de Débito C':
        return 'ND-C'
    if afip_invoice_type == '13 - Nota de Crédito C':
        return 'NC-C'
    
    raise UserError('Tipo de Comprobante invalido: %s'.format(afip_invoice_type))

# TODO: renombrar archivos para seguir un naming convention
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
    exempt_amount = fields.Float(string="Exento")
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

    # TODO: usar el mixin creado para esto
    def get_pos(self, pos_number):
        journal = self.env['account.journal'].search([
            ('l10n_ar_afip_pos_number', '=', pos_number)
        ])

        if len(journal) > 1:
            raise UserError('No puede haber más de 1 punto de venta con el mismo número')

        if len(journal) == 0:
            # TODO: Sacar de account.chart.template
            account_sale = self.env['account.account'].search([
                ('code', '=', '4.1.1.01.010'),
                ('name', '=', 'Venta de mercadería'),
            ])

            # Create new journal for this POS
            journal = self.env['account.journal'].create({
                'name': 'PDV %s - Comprobantes Emitidos'.format(pos_number),
                'type': 'sale',
                'l10n_latam_use_documents': True,
                'l10n_ar_afip_pos_number': pos_number,
                # TODO: definir si es factura en linea (RLI_RLM) o webservice
                'l10n_ar_afip_pos_system': 'RLI_RLM',
                'l10n_ar_afip_pos_partner_id': self.env.company.id,
                'default_account_id': account_sale.id,
                'code': str(pos_number).zfill(5),
            })
        
        return journal.id
    
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
                'exempt_amount': row[13],
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

        if len(self.invoice_ids) == 0:
            raise UserError('No hay facturas cargadas')

        # TODO: Validar que el CUIT sea correcto

        # USAR MIXIN
        account_sale = self.env['account.account'].search([
            ('code', '=', '4.1.1.01.010'),
            ('name', '=', 'Venta de mercadería'),
        ])
        tax_untaxed = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA No Gravado'),
        ])

        for invoice in self.invoice_ids:
            # Obtener/Crear diario segun el PdV automaticamente
            journal_id = self.get_pos(invoice.pos_number)

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
                    raise UserError('Cliente con CUIT %s no encontrado'.format(invoice.cuit))

                    # TODO: Crear nuevo cliente
                    # partner = self.env['res.partner'].create(partner_data)
                else:
                    # Actualizar datos del cliente
                    partner = partner[0]
                    partner.write(partner_data)
            else:
                partner = consumidor_final
            
            print("Partner", partner)
            
            # # Crear Orden de Venta (sale.order)
            # sale_data = {
            #     'date_order': invoice.date,
            #     'partner_id': partner.id,
            # }
            # sale = self.env['sale.order'].create(sale_data)

            # print("Sale", sale)

            # TODO: Revisar tambien montos gravados y exentos 

            product_untaxed = self.env.ref('pyme_accounting.prod_varios_no_gravado')

            # Create Invoice
            # TODO: mejorar esta query
            doc_type = self.env['l10n_latam.document.type'].search([('doc_code_prefix', '=', invoice.invoice_type)])
            
            move_data = {
                'move_type': 'out_invoice',
                'partner_id': partner.id,
                'journal_id': journal_id,
                'date': invoice.date,
                'invoice_date': invoice.date,
                'l10n_latam_document_type_id': doc_type.id,
                # TODO: Chequear (y validar) secuencia en PG
                'l10n_latam_document_number': '{}-{}'.format(invoice.pos_number, invoice.invoice_number),
            }
            print("Invoice Data", move_data)
            move = self.env['account.move'].create(move_data)
            print("Invoice", move)

            # IVA No Gravado
            if invoice.untaxed_amount > 0:
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto No Gravado',
                    'account_id': account_sale.id,
                    'quantity': 1,
                    'price_unit': invoice.untaxed_amount,
                })
                line.tax_ids += tax_untaxed
                print("LINE", line)

            # Recalculate totals
            move._recompute_dynamic_lines(recompute_all_taxes=True, recompute_tax_base_amount=True)
            move._recompute_payment_terms_lines()
            move._compute_amount()

            # Post Entry
            move.action_post()

            # TODO: que pasa si faltan facturas?? al ser correlativas deberian coincidir

        # TODO: retornar a ventana con el filtro de las facturas hechas recientemente
        # return {
        #     'context': self.env.context,
        #     'view_type': 'list',
        #     'view_mode': 'list',
        #     'res_model': 'account.move',
        #     'res_ids': [ 1, 2 ],
        #     'view_id': False,
        #     'type': 'ir.actions.act_window',
        #     'target': 'main',
        # }

    # TODO: generar solo facturas y no comprobante de venta
    def generate_sales_deprecated(self):
        consumidor_final = self.env['res.partner'].search([('name', '=', 'Consumidor Final Anónimo')])
        print("CONSUMIDOR FINAL", consumidor_final) 

        if len(self.invoice_ids) == 0:
            raise UserError('No hay facturas cargadas')

        # TODO: Validar que el CUIT sea correcto

        for invoice in self.invoice_ids:
            # Obtener/Crear diario segun el PdV automaticamente
            journal_id = self.get_pos(invoice.pos_number)

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
                    raise UserError('Cliente con CUIT %s no encontrado'.format(invoice.cuit))

                    # TODO: Crear nuevo cliente
                    # partner = self.env['res.partner'].create(partner_data)
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
                'price_unit': invoice.untaxed_amount,
                'currency_id': 19, # TODO: Get currency ID
                'price_subtotal': invoice.untaxed_amount, # TODO: restar del total las percepciones y el IVA para obtener este valor
                'price_tax': invoice.iva, # TODO: buscar IVA 0%
                'price_total': invoice.total,
                'qty_delivered': 1,
                'order_id': sale.id,
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
                sale._create_invoices()

            # Establecer fecha de factura
            sale.invoice_ids.invoice_date = invoice.date
            sale.invoice_ids.date = invoice.date

            # TODO: Establecer tipo de comprobante. Primero hay que cambiar a monotributo
            # doc_type = self.env['l10n_latam.document.type'].search([('doc_code_prefix', '=', invoice.invoice_type)])
            # sale.invoice_ids.l10n_latam_document_type_id = doc_type

            # TODO: Revisar numero de secuencia
            # Establecer punto de venta y numero de comprobante
            self.invoice_ids.journal_id = journal_id
            sale.invoice_ids.l10n_latam_document_number = '{}-{}'.format(invoice.pos_number, invoice.invoice_number)

            # TODO: Publicar Factura
            sale.invoice_ids.action_post()

            # TODO: que pasa si faltan facturas?? al ser correlativas deberian coincidir

        # TODO: retornar a ventana con el filtro de las facturas hechas recientemente
        # return {
        #     'context': self.env.context,
        #     'view_type': 'list',
        #     'view_mode': 'list',
        #     'res_model': 'account.move',
        #     'res_ids': [ 1, 2 ],
        #     'view_id': False,
        #     'type': 'ir.actions.act_window',
        #     'target': 'main',
        # }
