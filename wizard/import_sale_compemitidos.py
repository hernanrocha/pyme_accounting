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
    
    @api.depends('taxed_amount')
    def _compute_taxed_amount_21(self):
        for line in self:
            line.taxed_amount_21 = line.taxed_amount * 0.21

    taxed_amount_21 = fields.Float(string=".21", compute=_compute_taxed_amount_21)
    
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


    @api.depends('taxed_amount', 'untaxed_amount', 'exempt_amount', 'iva', 'total')
    def compute_difference(self):
        for line in self:
            line.difference = line.total - (line.taxed_amount + line.iva + line.exempt_amount + line.untaxed_amount)

    difference = fields.Float(string="Diferencia", compute=compute_difference)

    # TODO: generalizar esto en todos los metodos de importacion
    @api.depends('invoice_display_name')
    def _compute_invoice_id(self):
        for line in self:
            line.invoice_id = self.env['account.move'].search([
                ('move_type', 'in', ['out_invoice', 'out_refund']),
                ('name', '=', line.invoice_display_name),
                # TODO: filtrar por CUIT y por estado
            ])

    @api.depends('invoice_id')
    def _compute_invoice_found(self):
        for line in self:
            line.invoice_found = bool(line.invoice_id)

    invoice_id = fields.Many2one(string="Cbte Asociado", comodel_name="account.move", ondelete="set null", compute=_compute_invoice_id)
    invoice_found = fields.Boolean(string="Existente", compute=_compute_invoice_found)
    currency_id = fields.Many2one('res.currency', related="invoice_id.currency_id")
    invoice_amount_total = fields.Monetary(string='Cbte Total', related="invoice_id.amount_total")
    
    def _compute_match_total(self):
        for line in self:
            line.match_total = round(line.total, 2) == round(line.invoice_amount_total, 2)

    match_total = fields.Boolean(string="Coincide", compute=_compute_match_total)

# El metodo parse_sales esta repetido
class ImportSalesAfip(models.TransientModel):
    _name = "l10n_ar.afip.import_sale"
    _description = "Importar ventas de AFIP"
    
    afip_file = fields.Binary(string="Ventas AFIP (*.csv)")
    invoice_ids = fields.One2many(string="Facturas", comodel_name="l10n_ar.afip.import_sale.line", inverse_name="import_id")

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
                # TODO: hacer dependiente de la compañia
                ('company_id', '=', self.env.company.id),
                ('code', '=', '4.1.1.01.010'),
                ('name', '=', 'Venta de mercadería'),
            ])

            # Create new journal for this POS
            journal = self.env['account.journal'].create({
                'name': 'PDV {} - Comprobantes Emitidos'.format(int(pos_number)),
                'type': 'sale',
                'l10n_latam_use_documents': True,
                'l10n_ar_afip_pos_number': pos_number,
                # TODO: definir si es factura en linea (RLI_RLM) o webservice
                'l10n_ar_afip_pos_system': 'RLI_RLM',
                'l10n_ar_afip_pos_partner_id': self.env.company.partner_id.id,
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

        # Borrar comprobantes anteriores
        self.write({ 'invoice_ids': [(5, 0, 0)] })

        # Computar ventas AFIP
        for row in spamreader:
                        
            # Crear linea de venta en el wizard
            line = self.env['l10n_ar.afip.import_sale.line'].create({ 
                'date': datetime.datetime.strptime(row[0], '%d/%m/%Y'),
                'invoice_type': helper_convert_invoice_type(row[1]),
                'pos_number': row[2].zfill(5),
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
        
        return {
            # TODO: agregar titulo a la ventana
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

        # Obtener tipo de identificacion CUIT
        cuit_type = self.env.ref('l10n_ar.it_cuit') 

        # Obtener condicion fiscal consumidor final, RI, Monotributo
        cf = self.env.ref('l10n_ar.res_CF')
        # ri = self.env.ref('l10n_ar.res_IVARI')
        # monotributo = self.env.ref('l10n_ar.res_RM')

        if len(self.invoice_ids) == 0:
            raise UserError('No hay facturas cargadas')

        # TODO: Validar que el CUIT sea correcto

        # USAR MIXIN
        account_sale = self.env['account.account'].search([
            # TODO: hacer dependiente de la compañia
            ('company_id', '=', self.env.company.id),
            ('code', '=', '4.1.1.01.010'),
            ('name', '=', 'Venta de mercadería'),
        ])

        tax_21 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA 21%'),
        ])
        tax_untaxed = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA No Gravado'),
        ])
        tax_exempt = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA Exento'),
        ])

        for invoice in self.invoice_ids:
            # Omitir los comprobantes ya existentes
            if invoice.invoice_found:
                continue

            # Obtener/Crear diario segun el PdV automaticamente
            journal_id = self.get_pos(invoice.pos_number)

            # TODO: Permitir elegir que hacer con la diferencia
            invoice.untaxed_amount = invoice.difference

            if invoice.cuit:
                # Get or Create Customer Partner (res.partner)
                partner = self.env['res.partner'].search([('vat', '=', invoice.cuit)])
                partner_data = {
                    'type': 'contact',
                    'name': invoice.partner,
                    'vat': invoice.cuit,
                    'l10n_latam_identification_type_id': cuit_type.id,
                    # TODO: Si es Resp Inscripto, corroborar si es monotributo/RI
                    'l10n_ar_afip_responsibility_type_id': cf.id
                }
                if len(partner) == 0:
                    partner = self.env['res.partner'].create(partner_data)
            else:
                partner = consumidor_final
            
            _logger.info("Partner: {}".format(partner))

            # TODO: Revisar tambien montos gravados y exentos 

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

            # TODO: revisar que no haya otro tipo de IVA en los comprobantes
            if invoice.taxed_amount > 0:
                # IVA 21%
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto Gravado al 21%',
                    'account_id': account_sale.id,
                    'quantity': 1,
                    'price_unit': invoice.taxed_amount + (invoice.iva if tax_21.price_include else 0),
                })
                line.tax_ids += tax_21

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
                _logger.info("No Gravado: {}".format(line))

            # IVA Exento
            if invoice.exempt_amount > 0:
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto Exento',
                    'account_id': account_sale.id,
                    'quantity': 1,
                    'price_unit': invoice.exempt_amount,
                })
                line.tax_ids += tax_exempt
                _logger.info("No Exento: {}".format(line))

            # Recalculate totals
            move._recompute_dynamic_lines(recompute_all_taxes=True, recompute_tax_base_amount=True)
            move._recompute_payment_terms_lines()
            move._compute_amount()

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
