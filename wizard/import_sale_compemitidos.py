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
    if afip_invoice_type in ['1 - Factura A', '1']:
        return "FA-A"
    if afip_invoice_type in ['2 - Nota de Débito A', '2']:
        return "ND-A"
    if afip_invoice_type in ['3 - Nota de Crédito A', '3']:
        return "NC-A"
    if afip_invoice_type in ['4 - Recibo A', '4']:
        return "RE-A"
    if afip_invoice_type in ['6 - Factura B', '6']:
        return "FA-B"
    if afip_invoice_type in ['7 - Nota de Débito B', '7']:
        return "ND-B"
    if afip_invoice_type in ['8 - Nota de Crédito B', '8']:
        return "NC-B"
    if afip_invoice_type in ['9 - Recibo B', '9']:
        return "RE-B"
    if afip_invoice_type in ['11 - Factura C', '11']:
        return 'FA-C'
    if afip_invoice_type in ['12 - Nota de Débito C', '12']:
        return 'ND-C'
    if afip_invoice_type in ['13 - Nota de Crédito C', '13']:
        return 'NC-C'
    if afip_invoice_type in ['15 - Recibo C', '15']:
        return 'RE-C'
    
    raise UserError('Tipo de Comprobante invalido: {}'.format(afip_invoice_type))

# TODO: renombrar archivos para seguir un naming convention
class ImportSalesAfipLine(models.TransientModel):
    _name = "l10n_ar.afip.import_sale.line"
    _description = "Linea de venta de AFIP"
    _inherit = [ 'mixin.pyme_accounting.cbte_asociado' ]

    date = fields.Date(string="Fecha")
    invoice_type = fields.Char(string="Tipo de Comprobante")
    pos_number = fields.Char(string="Punto de Venta")
    invoice_number = fields.Char(string="N° Factura")
    
    # TODO: agregar columna tipo de documento y cambiar nombre de columna a "Documento"
    cuit = fields.Char(string="CUIT")
    partner = fields.Char(string="Cliente")
    import_id = fields.Many2one(comodel_name="l10n_ar.afip.import_sale", ondelete="cascade")

    # TODO: mover al mixin
    @api.depends('invoice_type', 'pos_number', 'invoice_number')
    def _compute_invoice_display_name(self):
        for line in self:
            line.invoice_display_name = "{} {}-{}".format(line.invoice_type, line.pos_number, line.invoice_number)

    # TODO: mover al mixin
    @api.depends('taxed_amount', 'untaxed_amount', 'exempt_amount', 'iva', 'total')
    def compute_difference(self):
        for line in self:
            line.difference = line.total - (line.taxed_amount + line.iva + line.exempt_amount + line.untaxed_amount)

    # TODO: mover al mixin
    invoice_display_name = fields.Char(string="Comprobante", compute="_compute_invoice_display_name", invisible=True)
    taxed_amount = fields.Monetary(string="Gravado")    
    untaxed_amount = fields.Monetary(string="No Gravado")
    exempt_amount = fields.Monetary(string="Exento")
    iva = fields.Monetary(string="IVA")
    difference = fields.Monetary(string="Diferencia", compute=compute_difference)
    total = fields.Monetary(string="Total")

# El metodo parse_sales esta repetido
class ImportSalesAfip(models.TransientModel):
    _name = "l10n_ar.afip.import_sale"
    _description = "Importar ventas de AFIP"
    
    afip_file = fields.Binary(string="Ventas AFIP (*.csv)")
    invoice_ids = fields.One2many(string="Facturas", comodel_name="l10n_ar.afip.import_sale.line", inverse_name="import_id")

    @api.depends('invoice_ids')
    def _compute_display_button_generate(self):
        for imp in self:
            imp.display_button_generate = imp.invoice_ids

    display_button_generate = fields.Boolean(string="Mostrar Boton Generar", compute=_compute_display_button_generate)

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
            'title': 'Importar Comprobantes Emitidos',
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
        dni_type = self.env.ref('l10n_ar.it_dni')

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
            # No procesar nuevamente los comprobantes ya existentes
            if invoice.invoice_found:
                continue

            # Obtener/Crear diario segun el PdV automaticamente
            journal_id = self.get_pos(invoice.pos_number)

            # Documentos soportados: DNI y CUIT
            if invoice.cuit:
                # Get or Create Customer Partner (res.partner)
                partner = self.env['res.partner'].search([('vat', '=', invoice.cuit)])
                
                # Los CUIT tienen 11 caracteres y nombre establecido
                # Los DNI tienen una longitud menor y no tienen nombre establecido
                partner_data = {
                    'type': 'contact',
                    'name': invoice.partner or "Consumidor Final",
                    'vat': invoice.cuit,
                    'l10n_latam_identification_type_id': cuit_type.id if len(invoice.cuit) == 11 else dni_type.id,
                    # TODO: Si es Resp Inscripto, corroborar si es monotributo/RI
                    'l10n_ar_afip_responsibility_type_id': cf.id
                }
                if len(partner) == 0:
                    partner = self.env['res.partner'].create(partner_data)
            else:
                partner = consumidor_final
            
            _logger.info("Partner: {}".format(partner))

            # TODO: mejorar esta query
            doc_type = self.env['l10n_latam.document.type'].search([('doc_code_prefix', '=', invoice.invoice_type)])
            
            # Create Invoice
            move_data = {
                'move_type': 'out_refund' if doc_type.internal_type == 'credit_note' else 'out_invoice',
                'partner_id': partner.id,
                'journal_id': journal_id,
                'date': invoice.date,
                'invoice_date': invoice.date,
                'l10n_latam_document_type_id': doc_type.id,
                # TODO: Chequear (y validar) secuencia en PG
                'l10n_latam_document_number': '{}-{}'.format(invoice.pos_number, invoice.invoice_number),
            }
            move = self.env['account.move'].create(move_data)

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

            # La diferencia entre el total y los otros campos,
            # se toma también como Monto No Gravado
            untaxed_amount = invoice.untaxed_amount + invoice.difference

            # IVA No Gravado
            if untaxed_amount > 0:
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto No Gravado',
                    'account_id': account_sale.id,
                    'quantity': 1,
                    'price_unit': untaxed_amount,
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

        # Volver a menu Empresas > Ventas > Comprobantes Emitidos
        ret = self.env["ir.actions.act_window"]._for_xml_id('pyme_accounting.action_move_out_invoice_type')
        ret["target"] = "main"
        
        return ret
