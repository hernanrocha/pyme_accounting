# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from dateutil.parser import parse
import os
import xml.etree.ElementTree as ET

# TODO: crear diario "Ventas Controlador Fiscal"
# TODO: crear IVA 6%: 
# - Nombre: IVA 6%
# - Tipo de Impuestos: Ventas
# - Importe: 6,0000%
# - Distribucion de facturas: 100% Impuesto a cuenta IVA Debito Fiscal
# - Distribucion de notas de credito: 100% Impuesto a cuenta IVA Credito Fiscal
# - Etiquetas en facturas: IVA 6%
# - Grupo de Impuestos: IVA 6%
# - Incluir en el precio: Si 
# BUG: El informe de IVA no muestra el 6% y muestra de todas las compañias.
# TODO: crear impuestos IVA 21%, 6%, No Gravado, Exento para ventas/compras en empresas nuevas.
# TODO: incluir en el precio para las ventas 

#   - Fecha de Cierre: 2021-04-22T16:55:11
#   - Gravado:         6632.23
#   - No Gravado:      0.00
#   - Exento:          0.00
#   - Total:           8025.00
#   - 21.00%: 1392.77
class SaleImportPEMLine(models.TransientModel):
    _name = "l10n_ar.import.sale.pem.line"
    _description = "Linea de comprobante de Controlador Fiscal PEM"

    date = fields.Date(string="Fecha")
    
    # TODO: convertir a monetary
    number = fields.Integer(string="Comprobante Z")
    range_from = fields.Integer(string="Comprobante Desde")
    range_to = fields.Integer(string="Comprobante Hasta")
    taxed = fields.Float(string="Gravado")
    untaxed = fields.Float(string="No Gravado")
    exempt = fields.Float(string="Exento")
    total = fields.Float(string="Total")
    tax_21 = fields.Float(string="IVA 21%")
    tax_6 = fields.Float(string="IVA 6%")

    pem_id = fields.Many2one(comodel_name="l10n_ar.import.sale.pem", ondelete="cascade", invisible=True)

    range = fields.Char(string="Rango", compute="_compute_range")

    @api.depends('range_from', 'range_to')
    def _compute_range(self):
        for line in self:
            line.range = "{}-{}".format(line.range_from, line.range_to)

class SaleImportPEM(models.TransientModel):
    _name = "l10n_ar.import.sale.pem"
    _description = "Importar archivo de Controlador Fiscal PEM"

    # TODO
    # pem_type = fields.Select(string="Tipo", options=['f8010', 'f8011'])

    # Listado de comprobantes individuales
    # f8010_file = fields.Binary(string="Archivo F8010 (*.pem)")

    # Listado de comprobantes Z
    f8011_file = fields.Binary(string="Archivo F8011 (*.pem)")

    f8011_cuit = fields.Char(string="CUIT", readonly=True)
    f8011_pos = fields.Integer(string="Punto de Venta", readonly=True)
    f8011_start_date = fields.Date(string="Fecha Desde", readonly=True)
    f8011_end_date = fields.Date(string="Fecha Hasta", readonly=True)
    f8011_start_number = fields.Integer(string="Primer Comprobante", readonly=True)
    f8011_end_number = fields.Integer(string="Ultimo Comprobante", readonly=True)

    invoice_ids = fields.One2many(string="Comprobantes", comodel_name="l10n_ar.import.sale.pem.line", inverse_name="pem_id")
    
    tax_21 = fields.Many2one(comodel_name="account.tax", ondelete="cascade")
    tax_untaxed = fields.Many2one(comodel_name="account.tax", ondelete="cascade")
    tax_exempt = fields.Many2one(comodel_name="account.tax", ondelete="cascade")
    account_sale = fields.Many2one(comodel_name="account.account", ondelete="cascade")
    journal = fields.Many2one(comodel_name="account.journal", ondelete="cascade")

    def _find_relations(self):
        # Taxes
        self.tax_21 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA 21%'),
        ])
        self.tax_untaxed = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA No Gravado'),
        ])
        self.tax_exempt = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA Exento'),
        ])

        # Account
        self.account_sale = self.env['account.account'].search([
            ('code', '=', '4.1.1.01.010'),
            ('name', '=', 'Venta de mercadería'),
        ])

        # Journal
        self.journal = self.env['account.journal'].search([
            ('name', '=', 'Ventas Controlador Fiscal'),
        ])

    def _parse_pem(self, pem):
        attachment = self.env['ir.attachment'].create({
            # TODO: Get a meaningful name
            "name": "PEM",
            "datas": pem,
            "type": "binary",
        })
        print("PEM: ", attachment.id)

        # Convertir PEM a XML
        xmlfile = attachment.store_fname.replace("/", "")
        fullpath = os.path.join(attachment._filestore(), attachment.store_fname)
        os.system('openssl cms -verify -in {} -inform PEM -noverify -out /tmp/odoo/{}.xml'.format(fullpath, xmlfile))
        
        # Parsear archivo XML
        tree = ET.parse('/tmp/odoo/{}.xml'.format(xmlfile))
        return tree.getroot()

    def compute_f8010(self):

        # TODO: chequear CUIT con compañia
        # TODO: Obtener diario por PdV y tipo, o crearlo (no deberia haber duplicados)
        # TODO: Guardar un registro de los pems, pasar a readonly los archivos raw y attachear los XML

        [data] = self.read()

        if not data['f8010_file']:
            raise UserError("Debes cargar el archivo de ventas F8010")

        # Convertir PEM a XML
        root = self._parse_pem(data['f8010_file'])

        # root = ET.fromstring(file_content)
        # root = tree.getroot()

        tax_21 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA 21%'),
        ])
        # TODO: convertir esto a 21% y marcar como Exento el sobrante 
        tax_6 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA 6%'),
        ])
        tax_untaxed = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA No Gravado'),
        ])
        tax_exempt = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA Exento'),
        ])

        # TODO: Configure this in wizard
        account_sale = self.env['account.account'].search([
            ('code', '=', '4.1.1.01.010'),
            ('name', '=', 'Venta de mercadería'),
        ])
        journal = self.env['account.journal'].search([
            ('name', '=', 'Ventas Controlador Fiscal'),
        ])

        # TODO: Add preview

        grupoComprobantes = root.find('arrayGruposComprobantesFiscales').find('grupoComprobantes')
        for detalleComprobante in grupoComprobantes.find('arrayDetallesComprobantes').findall('detalleComprobante'):
            numeroComprobante = detalleComprobante.findtext('numeroComprobante')
            fechaHoraEmision = detalleComprobante.findtext('fechaHoraEmision')

            print('Comprobante', numeroComprobante)
            print('Fecha:', fechaHoraEmision)
            print()

            move = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': 7, # TODO: Consumidor Final
                'journal_id': journal.id,
                'date': parse(fechaHoraEmision), # Date
                'invoice_date': parse(fechaHoraEmision), # Date
                'l10n_latam_document_type_id': 11, # TODO: Factura C?
                'l10n_latam_document_number': '1-{}'.format(numeroComprobante),
            })

            # print('Descripcion              Gravado   IVA %    IVA     Total')

            # TODO: Forma de pago

            # Items
            for item in detalleComprobante.find('arrayItems').findall('item'):
                descripcion = item.findtext('descripcion')
                codigoCondicionIVA = item.findtext('codigoCondicionIVA')
                cantidad = item.findtext('cantidad')                      #   1.000000
                porcentajeIVA = item.findtext('porcentajeIVA') or '0.00'  #  21.00
                # importeIVA = item.findtext('importeIVA')                  #  43.39
                importeItem = item.findtext('importeItem')                # 250.00

                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': descripcion,
                    'account_id': account_sale.id,
                    'quantity': float(cantidad),
                    'price_unit': float(importeItem),
                    'price_subtotal': float(importeItem)
                })

                if porcentajeIVA == '21.00':
                    line.tax_ids += tax_21
                elif porcentajeIVA == '6.00': # codigo 7 (gravado)
                    line.tax_ids += tax_6
                elif porcentajeIVA == '0.00' and codigoCondicionIVA == '1': # No gravado
                    line.tax_ids += tax_untaxed
                elif porcentajeIVA == '0.00' and codigoCondicionIVA == '2': # Exento
                    line.tax_ids += tax_exempt
                else:
                    print('IVA Desconocido: ', numeroComprobante)

            # Recalculate totals
            move._recompute_dynamic_lines(recompute_all_taxes=True, recompute_tax_base_amount=True)
            move._recompute_payment_terms_lines()
            move._compute_amount()

    # @api.onchange('f8011_file')
    # TODO: seems to be a bug in Odoo 14.0 https://github.com/odoo/odoo/pull/59740
    def compute_f8011(self):
        [data] = self.read()

        if not data['f8011_file']:
            raise UserError("Debes cargar el archivo de ventas F8011")

        # TODO: error handling si el formato es incorrecto o es otro formulario

        # Convertir PEM a XML
        root = self._parse_pem(data['f8011_file'])

        text_date = root.findtext('fechaHoraEmisionAuditoria')

        emisor = root.find('emisor')
        text_cuit = emisor.findtext('cuitEmisor')
        text_pdv = emisor.findtext('numeroPuntoVenta')

        print('CUIT:   ', text_cuit)
        print('PdV:    ', text_pdv)
        print('Fecha:  ', text_date)
        print()
        self.f8011_cuit = text_cuit
        self.f8011_pos = int(text_pdv)

        for comprobanteAuditoria in root.find('arrayComprobantesAuditoria').findall('comprobanteAuditoria'):
            rango = comprobanteAuditoria.find('rangoEncontrado')

            text_number_from = rango.findtext('numeroZDesde')
            text_number_to = rango.findtext('numeroZHasta')
            text_date_from = rango.findtext('fechaZDesde') # YYYY-MM-DD
            text_date_to = rango.findtext('fechaZHasta') # YYYY-MM-DD 

            self.f8011_start_number = int(text_number_from)
            self.f8011_end_number = int(text_number_to)
            self.f8011_start_date = text_date_from
            self.f8011_end_date = text_date_to

            print('Numero:  {}-{}'.format(text_number_from, text_number_to))
            print('Desde:   {}'.format(text_date_from))
            print('Hasta:   {}'.format(text_date_to))
            print()

            for cierreZFecha in comprobanteAuditoria.find('arrayCierresZ').findall('cierreZFecha'):
                text_z_date = cierreZFecha.findtext('fechaHoraEmisionCierreZ')
                cierreZ = cierreZFecha.find('cierreZ')
                text_z_number = cierreZ.findtext('numeroZ')
                text_z_taxed = cierreZ.findtext('totalGravadoComprobantesFiscales')
                text_z_untaxed = cierreZ.findtext('totalNoGravadoComprobantesFiscales')
                text_z_exempt = cierreZ.findtext('totalExentoComprobantesFiscales')
                text_z_total = cierreZ.findtext('importeTotalComprobantesFiscales')
                
                # TODO: chequear que no haya mas de 1
                comp_fiscales = cierreZ.find('arrayConjuntosComprobantesFiscales').find('conjuntoComprobantesFiscales')
                # text_z_codigo_comprobante = comp_fiscales.findtext('codigoTipoComprobante') # 83
                text_z_range_from = comp_fiscales.findtext('primerNumeroComprobante')
                text_z_range_to = comp_fiscales.findtext('ultimoNumeroComprobante')
                
                print('Comprobante', text_z_number)
                print('  - Fecha de Cierre:', text_z_date)
                print('  - Gravado:        ', text_z_taxed)
                print('  - No Gravado:     ', text_z_untaxed)
                print('  - Exento:         ', text_z_exempt)
                print('  - Total:          ', text_z_total)

                invoice_data = {
                    'date': text_z_date[:10], # 2021-02-20T...
                    'number': text_z_number,
                    'range_from': int(text_z_range_from),
                    'range_to': int(text_z_range_to),
                    'taxed': float(text_z_taxed),
                    'untaxed': float(text_z_untaxed),
                    'exempt': float(text_z_exempt),
                    'total': float(text_z_total),
                    'pem_id': self.id,
                    'tax_21': 0,
                    'tax_6': 0
                }

                for subtotalIVA in cierreZ.find('arraySubtotalesIVA').findall('subtotalIVA'):
                    text_vat_percentage = subtotalIVA.findtext('porcentajeIVA')
                    text_vat_subtotal = subtotalIVA.findtext('importe')
                    
                    print('  - {}%: {}'.format(text_vat_percentage, text_vat_subtotal))

                    if text_vat_percentage == '21.00':
                        invoice_data['tax_21'] = float(text_vat_subtotal)
                    elif text_vat_percentage == '6.00':
                        invoice_data['tax_6'] = float(text_vat_subtotal)

                self.env["l10n_ar.import.sale.pem.line"].create(invoice_data)
                print()

        # Fill relations
        self._find_relations()

        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'l10n_ar.import.sale.pem',
            'res_id': self.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def generate_f8011(self):

        for invoice in self.invoice_ids:
            # Create Invoice
            move = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': 7, # TODO: Consumidor Final
                'journal_id': self.journal.id,
                'date': invoice.date,
                'invoice_date': invoice.date,
                'l10n_latam_document_type_id': 58, # TODO: Tique
                # TODO: Chequear (y validar) secuencia en PG 
                'l10n_latam_document_number': '{}-{}'.format(self.f8011_pos, invoice.number),
            })

            # range_from = fields.Integer(string="Comprobante Desde")
            # range_to = fields.Integer(string="Comprobante Hasta")
            # total = fields.Float(string="Total")

            # IVA 21%
            line = move.line_ids.create({
                'move_id': move.id,
                'name': 'Monto Gravado al 21%',
                'account_id': self.account_sale.id,
                'quantity': 1,
                # TODO: chequear que el impuesto este incluido en el precio
                'price_unit': invoice.taxed + invoice.tax_21,
            })
            line.tax_ids += self.tax_21

            # IVA No Gravado
            line = move.line_ids.create({
                'move_id': move.id,
                'name': 'Monto No Gravado',
                'account_id': self.account_sale.id,
                'quantity': 1,
                'price_unit': invoice.untaxed,
            })
            line.tax_ids += self.tax_untaxed

            # IVA Exento
            line = move.line_ids.create({
                'move_id': move.id,
                'name': 'Monto Exento',
                'account_id': self.account_sale.id,
                'quantity': 1,
                'price_unit': invoice.exempt,
            })
            line.tax_ids += self.tax_exempt

            # TODO: Handle IVA 6%

            # TODO: Add note with invoice range
            # display_type = line_note

            # Recalculate totals
            move._recompute_dynamic_lines(recompute_all_taxes=True, recompute_tax_base_amount=True)
            move._recompute_payment_terms_lines()
            move._compute_amount()

            move.action_post()

        # TODO: el codigo debe ser TI-Z y no TI-X

        # TODO: retornar vista de los tiques creados