# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import csv
import io
import base64
import datetime
import logging

_logger = logging.getLogger(__name__)

# TODO: Usar modelo de Odoo para hacer esta traduccion
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

# TODO: aplicar algo similar a los imports de facturas emitidas
def get_move_type(invoice_type):
    if invoice_type in ['NC-A','NC-B','NC-C']:
        return 'in_refund'

    return 'in_invoice'

def es_comprobante_c(invoice_type):
    return invoice_type in ['FA-C', 'ND-C', 'NC-C']

class ImportPurchaseCompRecibidosLine(models.TransientModel):
    _name = "l10n_ar.import.purchase.comprecibidos.line"
    _description = "Linea de comprobante de Comprobantes Recibidos"

    date = fields.Date(string="Fecha")
    invoice_type = fields.Char(string="Tipo de Comprobante")
    pos_number = fields.Char(string="Punto de Venta")
    invoice_number = fields.Char(string="N° Factura")
    cuit = fields.Char(string="CUIT")
    vendor = fields.Char(string="Proveedor")
    taxed_amount = fields.Float(string="Gravado")
    untaxed_amount = fields.Float(string="No Gravado")
    exempt_amount = fields.Float(string="Exento")
    iva = fields.Float(string="Monto IVA")
    total = fields.Float(string="Total")

    import_id = fields.Many2one(comodel_name="l10n_ar.import.purchase.comprecibidos", ondelete="cascade", invisible=True)

    @api.depends('taxed_amount', 'iva', 'untaxed_amount', 'exempt_amount', 'total')
    def _compute_difference(self):
        for line in self:
            line.difference = line.total - (line.taxed_amount + line.iva + line.untaxed_amount + line.exempt_amount)

    invoice_display_name = fields.Char(string="Comprobante", compute="_compute_invoice_display_name", invisible=True)
    difference = fields.Float(string="Otros", compute=_compute_difference)
    needs_attention = fields.Boolean(string="Necesita Accion", compute="compute_needs_attention", invisible=True)
    iva_type = fields.Float(string="IVA %", compute="_compute_iva_type")

    @api.depends('invoice_type', 'pos_number', 'invoice_number')
    def _compute_invoice_display_name(self):
        for line in self:
            line.invoice_display_name = "{} {}-{}".format(line.invoice_type, line.pos_number, line.invoice_number)

    @api.depends('iva', 'taxed_amount')
    def _compute_iva_type(self):
        for line in self:
            line.iva_type = 0
            if line.taxed_amount > 0:
                line.iva_type = line.iva * 100 / line.taxed_amount

    @api.depends('difference')
    def compute_needs_attention(self):
        for line in self:
            line.needs_attention = line.difference > 0.01 or line.difference < -0.01

    @api.depends('invoice_display_name')
    def _compute_invoice_id(self):
        for line in self:
            line.invoice_id = self.env['account.move'].search([
                ('move_type', 'in', ['in_invoice', 'in_refund']),
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

class ImportPurchaseCompRecibidos(models.TransientModel):
    _name = "l10n_ar.import.purchase.comprecibidos"
    _description = "Importar archivo de Comprobantes en Recibidos"

    file = fields.Binary(string="Archivo de Comprobantes (*.csv)")

    invoice_ids = fields.One2many(string="Comprobantes", comodel_name="l10n_ar.import.purchase.comprecibidos.line", inverse_name="import_id")
    existing_invoice_ids = fields.Many2many(string="Comprobantes Existentes", comodel_name="account.move")

    @api.depends('invoice_ids', 'invoice_ids.invoice_found')
    def _compute_display_invoice_ids(self):
        for imp in self:
            imp.display_invoice_ids = imp.invoice_ids.filtered(lambda i: not i.invoice_found)

    display_invoice_ids = fields.One2many(string="Comprobantes Filtrados", comodel_name="l10n_ar.import.purchase.comprecibidos.line", compute=_compute_display_invoice_ids)
    
    def compute(self):
        [data] = self.read()

        if not data['file']:
            raise UserError("Debes cargar un archivo de compras de AFIP")
        
        # Borrar registros anteriores
        self.write({ 'invoice_ids': [(5, 0, 0)] })

        # Leer archivo AFIP de compras
        file_content = base64.decodestring(data['file'])
        csvfile = io.StringIO(file_content.decode("utf-8"))
        
        # Omitir primera linea (cabecera) del archivo
        next(csvfile)

        spamreader = csv.reader(csvfile, delimiter=',', quotechar='"', )
        # print('Fecha, Tipo, Punto de Venta, Numero, CUIT, Denominacion, Imp. Neto Gravado, IVA, Imp. Total, Percepcion ARBA')
        
        count = 0

        # Computar Mis Comprobantes Recibidos AFIP
        for row in spamreader:
            # TODO: computar diferencia

            # Crear linea de compra en el wizard
            wizard_invoice_line = self.env['l10n_ar.import.purchase.comprecibidos.line'].create({ 
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
                'total': row[15],
                'import_id': self.id,
            })

            count += 1

        self.existing_invoice_ids = self.env['account.move'].search([
                ('move_type', 'in', ['in_invoice', 'in_refund']),
                ('id', 'not in', self.invoice_ids.mapped('invoice_id').mapped('id'))
        ])
        _logger.info("Otros comprobantes: {}".format(self.existing_invoice_ids))

        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'l10n_ar.import.purchase.comprecibidos',
            'res_id': self.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def generate(self):
        # Obtener tipo de identificacion CUIT
        cuit_type = self.env.ref('l10n_ar.it_cuit') 

        # Obtener condicion fiscal RI y Monotributo
        ri = self.env.ref('l10n_ar.res_IVARI')
        monotributo = self.env.ref('l10n_ar.res_RM')

        account_purchase = self.env['account.account'].search([
            # TODO: hacer dependiente de la compañia 
            ('company_id', '=', self.env.company.id),
            ('code', '=', '5.1.1.01.030'),
            ('name', '=', 'Compra de mercadería'),
        ])

        print(cuit_type, ri, monotributo, account_purchase)

        if len(self.invoice_ids) == 0:
            raise UserError('No hay facturas cargadas')

        # TODO: Validar que el CUIT sea correcto

        # TODO: USAR MIXIN
        # TODO: tener en cuenta otras alicuotas
        tax_untaxed = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', '=', 'IVA No Gravado'),
        ])

        tax_21 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', '=', 'IVA 21%'),
        ])

        tax_exempt = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', '=', 'IVA Exento'),
        ])

        tax_no_corresponde = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', '=', 'IVA No Corresponde'),
        ])
        print(tax_untaxed, tax_21, tax_exempt, tax_no_corresponde)

        for invoice in self.invoice_ids:
            # TODO: Obtener diario de proveedores
            # journal_id = self.get_pos(invoice.pos_number)
            journal = self.env['account.move'].with_context(default_move_type='in_invoice')._get_default_journal()

            # TODO: Permitir elegir que hacer con la diferencia
            # invoice.untaxed_amount = invoice.difference

            # Get or Create Vendor Partner (res.partner)
            partner = self.env['res.partner'].search([('vat', '=', invoice.cuit)])
            partner_data = { 
                'type': 'contact',
                'name': invoice.vendor,
                'vat': invoice.cuit,
                'l10n_latam_identification_type_id': cuit_type.id,
                # TODO: Si es factura C, cargar como monotributo
                'l10n_ar_afip_responsibility_type_id': monotributo.id if es_comprobante_c(invoice.invoice_type) else ri.id 
            }
            if len(partner) == 0:
                # Crear nuevo proveedor
                print("Creating partner", partner_data)
                partner = self.env['res.partner'].create(partner_data)
            else:
                # Actualizar datos del proveedor
                partner = partner[0]
                partner.write(partner_data)
            
            print("Partner", partner)
            
            # TODO: Revisar tambien montos gravados y exentos 

            # Create Invoice
            # TODO: mejorar esta query
            doc_type = self.env['l10n_latam.document.type'].search([('doc_code_prefix', '=', invoice.invoice_type)])
            print("DOC TYPE", doc_type)

            # TODO: investigar mas los casos de uso de IVA No Corresponde (account_move.py)
            # Fix a error "En la factura con id "645" debe usar IVA NO Corresponde en cada línea."
            no_iva = doc_type.purchase_aliquots == 'zero'

            move_data = {
                'move_type': get_move_type(invoice.invoice_type),
                'partner_id': partner.id,
                'journal_id': journal.id,
                'date': invoice.date,
                'invoice_date': invoice.date,
                'l10n_latam_document_type_id': doc_type.id,
                # TODO: Chequear (y validar) secuencia en PG
                'l10n_latam_document_number': '{}-{}'.format(invoice.pos_number, invoice.invoice_number),
            }
            print("Invoice Data", move_data)

            move = self.env['account.move'].create(move_data)
            print("Invoice", move)

            # TODO: determinar el tipo de IVA (21%, 10.5%, etc)

            # IVA 21% o Factura con valor $0.00
            if invoice.taxed_amount > 0 or invoice.total == 0:
                # TODO: chequear que siempre sea 21%
                # if 

                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto Gravado',
                    'account_id': account_purchase.id,
                    'quantity': 1,
                    'price_unit': invoice.taxed_amount + invoice.iva,
                })
                line.tax_ids += tax_no_corresponde if no_iva else tax_21
                print("Taxed Line", line)

            # IVA No Gravado
            if invoice.untaxed_amount > 0:
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto No Gravado',
                    'account_id': account_purchase.id,
                    'quantity': 1,
                    'price_unit': invoice.untaxed_amount,
                })
                line.tax_ids += tax_no_corresponde if no_iva else tax_untaxed
                print("Untaxed Line", line)

            # IVA Exento
            if invoice.exempt_amount > 0:
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto Exento',
                    'account_id': account_purchase.id,
                    'quantity': 1,
                    'price_unit': invoice.exempt_amount,
                })
                line.tax_ids += tax_no_corresponde if no_iva else tax_exempt
                print("Exempt Line", line)

            # Diferencia (se guarda como no gravado)
            if invoice.difference > 0:
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Otros Montos No Gravados',
                    'account_id': account_purchase.id,
                    'quantity': 1,
                    'price_unit': invoice.difference,
                })
                line.tax_ids += tax_no_corresponde if no_iva else tax_untaxed
                print("Difference Line", line)

            # Recalculate totals
            move._recompute_dynamic_lines(recompute_all_taxes=True, recompute_tax_base_amount=True)
            move._recompute_payment_terms_lines()
            move._compute_amount()

            # Post Entry
            move.action_post()