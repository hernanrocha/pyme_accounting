# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from dateutil.parser import parse
import os
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

_logger = logging.getLogger(__name__)

# PRECONDICIONES:
# - El CUIT debe ser el mismo de la compañia
# - Se debe haber instalado el plan contable resp. inscripto
# - Se deben configurar los IVAs para incluir en el precio de venta (price_include, include_base_amount)

class AccountMixin(models.AbstractModel):
    _name = 'mixin.l10n_ar.account'

    def get_pos(self, pos_number):
        print('Getting PuntoDeVenta', pos_number)

        # TODO: Sacar de account.chart.template
        account_sale = self.env['account.account'].search([
            # TODO: hacer dependiente de la compañia
            ('company_id', '=', self.env.company.id),
            ('code', '=', '4.1.1.01.010'),
            ('name', '=', 'Venta de mercadería'),
        ])

        journal = self.env['account.journal'].search([
            ('l10n_ar_afip_pos_number', '=', pos_number)
        ])

        if len(journal) > 1:
            raise UserError('No puede haber más de 1 punto de venta con el mismo número')

        if len(journal) == 0:
            # Create new journal for this POS
            journal = self.env['account.journal'].create({
                # TODO: make this generic
                'name': 'PDV {} - Controlador Fiscal'.format(pos_number),
                'type': 'sale',
                'l10n_latam_use_documents': True,
                'l10n_ar_afip_pos_number': pos_number,
                # TODO: definir si es factura en linea (RLI_RLM), webservice, CF
                'l10n_ar_afip_pos_system': 'RLI_RLM',
                'l10n_ar_afip_pos_partner_id': self.env.company.partner_id.id,
                'default_account_id': account_sale.id,
                'code': str(pos_number).zfill(5),
            })

        print("Journal encontrado/creado: ", journal)
        
        return journal

# BUG: El informe de IVA no muestra el 6% y muestra de todas las compañias.
# TODO: incluir en el precio para las ventas 


# Revisar codigo de secuencia que cambia nombre a "/"
# @api.onchange('journal_id')
# def _onchange_journal(self):
#     if self.journal_id and self.journal_id.currency_id:
#         new_currency = self.journal_id.currency_id
#         if new_currency != self.currency_id:
#             self.currency_id = new_currency
#             self._onchange_currency()
#     if self.state == 'draft' and self._get_last_sequence() and self.name and self.name != '/':
#         self.name = '/'

# sequence.mixin en account/models/sequence_mixin.py
# _get_last_sequence(self, relaxed=False) debe devolver [] cuando se trata legalmente

class SaleImportPemF8010Grouped(models.TransientModel):
    _name = "l10n_ar.import.sale.pem.f8010.grouped"
    _description = "Comprobantes Controlador Fiscal PEM F8010 agrupados por Z"

    z = fields.Integer(string="Comprobante Z")
    description = fields.Char(string="Descripción")
    total = fields.Float(string="Total")

    pem_id = fields.Many2one(comodel_name="l10n_ar.import.sale.pem", ondelete="cascade", invisible=True)


class SaleImportPemF8010Line(models.TransientModel):
    _name = "l10n_ar.import.sale.pem.f8010.line"
    _description = "Linea de comprobante de Controlador Fiscal PEM F8010"

    date = fields.Date(string="Fecha")
    
    # TODO: convertir a monetary
    number = fields.Integer(string="Comprobante")
    description = fields.Char(string="Descripción")
    # TODO: generar un mixin con estos campos
    taxed_21 = fields.Float(string="Gravado")
    tax_21 = fields.Float(string="IVA 21%")
    # TODO: borrar este campo
    taxed_6 = fields.Float(string="Gravado 6%")
    tax_6 = fields.Float(string="IVA 6%")
    untaxed = fields.Float(string="No Gravado")
    exempt = fields.Float(string="Exento")
    total = fields.Float(string="Total")

    pem_id = fields.Many2one(comodel_name="l10n_ar.import.sale.pem", ondelete="cascade", invisible=True)

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
    number = fields.Integer(string="Z")
    range_from = fields.Integer(string="Comprobante Desde")
    range_to = fields.Integer(string="Comprobante Hasta")
    # TODO: generar un mixin con estos campos
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
    _inherit = [ 'mixin.l10n_ar.account' ]

    # TODO: Permitir guardarse y acceder los XML
    f8010_xml_file = fields.Binary(string="F8010 archivo XML", readonly=True)
    f8011_xml_file = fields.Binary(string="F8011 archivo XML", readonly=True)

    # TODO: soportar comprobante f8010
    # pem_type = fields.Select(string="Tipo", options=['f8010', 'f8011'])

    # Listado de comprobantes individuales
    f8010_file = fields.Binary(string="Archivo F8010 (*.pem)")

    f8010_cuit = fields.Char(string="CUIT", readonly=True)
    f8010_pos = fields.Integer(string="Punto de Venta", readonly=True)
    f8010_start_date = fields.Date(string="Fecha Desde", readonly=True)
    f8010_end_date = fields.Date(string="Fecha Hasta", readonly=True)
    f8010_invoice_ids = fields.One2many(string="Comprobantes", comodel_name="l10n_ar.import.sale.pem.f8010.line", inverse_name="pem_id")

    f8010_grouped_ids = fields.One2many(string="Ventas por Z", comodel_name="l10n_ar.import.sale.pem.f8010.grouped", inverse_name="pem_id")

    # Listado de comprobantes Z
    f8011_file = fields.Binary(string="Archivo F8011 (*.pem)")

    f8011_cuit = fields.Char(string="CUIT", readonly=True)
    f8011_pos = fields.Integer(string="Punto de Venta", readonly=True)
    f8011_start_date = fields.Date(string="Fecha Desde", readonly=True)
    f8011_end_date = fields.Date(string="Fecha Hasta", readonly=True)
    f8011_start_number = fields.Integer(string="Primer Comprobante", readonly=True)
    f8011_end_number = fields.Integer(string="Ultimo Comprobante", readonly=True)
    invoice_ids = fields.One2many(string="Comprobantes", comodel_name="l10n_ar.import.sale.pem.line", inverse_name="pem_id")
    
    f8011_total_tax_6 = fields.Boolean(string="Total IVA 6%", compute="_compute_f8011_total_tax_6")

    @api.depends('invoice_ids', 'invoice_ids.tax_6')
    def _compute_f8011_total_tax_6(self):
        for pem in self:
            pem.f8011_total_tax_6 = sum(pem.invoice_ids.mapped('tax_6')) > 0

    # Referencias
    tax_21 = fields.Many2one(comodel_name="account.tax", ondelete="cascade")
    tax_untaxed = fields.Many2one(comodel_name="account.tax", ondelete="cascade")
    tax_exempt = fields.Many2one(comodel_name="account.tax", ondelete="cascade")
    account_sale = fields.Many2one(comodel_name="account.account", ondelete="cascade")
    journal = fields.Many2one(comodel_name="account.journal", ondelete="cascade")

    def _find_relations(self):
        # Taxes
        # TODO: sacar de computed
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
        # TODO: Sacar de account.chart.template
        self.account_sale = self.env['account.account'].search([
            # TODO: hacer dependiente de la compañia
            ('company_id', '=', self.env.company.id),
            ('code', '=', '4.1.1.01.010'),
            ('name', '=', 'Venta de mercadería'),
        ])

    def _parse_pem(self, pem):
        attachment = self.env['ir.attachment'].create({
            # TODO: Get a meaningful name
            "name": "PEM",
            "datas": pem,
            "type": "binary",
        })
        _logger.info("PEM: {}".format(attachment.id))

        xmlfile = attachment.store_fname.replace("/", "")
        fullpath = os.path.join(attachment._filestore(), attachment.store_fname)
        _logger.info("XML File {} {}".format(xmlfile, fullpath))
        
        # Make sure /tmp/odoo exists
        Path("/tmp/odoo").mkdir(parents=True, exist_ok=True) 

        # Convertir PEM a XML
        ret = os.system('openssl cms -verify -in {} -inform PEM -noverify -out /tmp/odoo/{}.xml'.format(fullpath, xmlfile))
        if ret != 0:
            raise UserError("Hubo un error analizando el archivo .PEM")
        _logger.info("Return OpenSSL {}".format(ret))
        
        # Parsear archivo XML
        tree = ET.parse('/tmp/odoo/{}.xml'.format(xmlfile))

        # TODO: Borrar archivos temporales despues de usarlos o attachearlo a Odoo

        return tree.getroot()

    @api.depends('f8010_file', 'f8011_file')
    def compute(self):
        self.compute_f8010()
        return self.compute_f8011()

    @api.depends('f8010_file')
    def compute_f8010(self):

        # TODO: chequear CUIT con compañia
        # TODO: Guardar un registro de los pems, pasar a readonly los archivos raw y attachear los XML
        # TODO: poner "nombre" de la controladora fiscal???
        # TODO: listar productos encontrados, permitir configurar entre No Gravado / Exento

        # Borrar comprobantes cargados anteriormente
        # TODO: Borrar esto una vez que este funcionando. Puede ser util cargar varios PEM
        self.write({ 'f8010_invoice_ids': [(5, 0, 0)] })

        [data] = self.read()

        if not data['f8010_file']:
            return

        # Convertir PEM a XML
        root = self._parse_pem(data['f8010_file'])
              
        text_cuit = root.findtext('cuitEmisor')
        text_pdv = root.findtext('numeroPuntoVenta')
        text_fecha_desde = root.findtext('fechaDesde')
        text_fecha_hasta = root.findtext('fechaHasta')

        self.f8010_cuit = text_cuit
        self.f8010_pos = int(text_pdv)
        self.f8010_start_date = text_fecha_desde[:10]
        self.f8010_end_date = text_fecha_hasta[:10]
        
        # Fill relations (Taxes, Accounts)
        self._find_relations()

        # Find Point of Sale (Sale Journal)
        self.journal = self.get_pos(self.f8010_pos)
        
        comprobantes = {}

        grupoComprobantes = root.find('arrayGruposComprobantesFiscales').find('grupoComprobantes')
        
        # Recorrer listado de comprobantes
        for detalleComprobante in grupoComprobantes.find('arrayDetallesComprobantes').findall('detalleComprobante'):
            numeroComprobante = int(detalleComprobante.findtext('numeroComprobante'))
            fechaHoraEmision = detalleComprobante.findtext('fechaHoraEmision')
            fecha = fechaHoraEmision[:10] # 2021-02-01T10:16:01 => 2021-02-01

            # TODO: generar rango de comprobantes

            # Recorrer items y agrupar por producto
            # TODO: agrupar por numero de comprobante y no por fecha (Puede haber 2 Zs diarios)
            # TODO: para eso, se deben procesar los 2 archivos juntos

            # Recorrer listado de items
            for item in detalleComprobante.find('arrayItems').findall('item'):
                descripcion = item.findtext('descripcion')
                codigoCondicionIVA = item.findtext('codigoCondicionIVA')
                # precioUnitario = item.findtext('precioUnitario')        # 250.000000
                # cantidad = item.findtext('cantidad')                    #   1.000000
                porcentajeIVA = item.findtext('porcentajeIVA') or '0.00'  #  21.00
                importeIVA = float(item.findtext('importeIVA'))           #  43.39
                importeItem = float(item.findtext('importeItem'))         # 250.00

                c_fecha = comprobantes.get(fecha, {})
                c_fecha_item = c_fecha.get(descripcion, {
                    'comprobante_desde': numeroComprobante,
                    'comprobante_hasta': numeroComprobante,
                    'codigoCondicionIVA': codigoCondicionIVA, 
                    'porcentajeIVA': porcentajeIVA, 
                    'importeItem': 0, 
                    'importeIVA': 0,
                    'importeGravado': 0,
                })
                c_fecha_item['importeItem'] += importeItem
                c_fecha_item['importeIVA'] += importeIVA
                c_fecha_item['importeGravado'] += importeItem - importeIVA
                c_fecha_item['comprobante_desde'] = min(c_fecha_item['comprobante_desde'], numeroComprobante)
                c_fecha_item['comprobante_hasta'] = max(c_fecha_item['comprobante_hasta'], numeroComprobante)

                c_fecha[descripcion] = c_fecha_item
                comprobantes[fecha] = c_fecha

                self.f8010_invoice_ids.create({
                    'number': numeroComprobante,
                    'description': descripcion,
                    'date': fecha,
                    'taxed_21': importeItem - importeIVA,   # Gravado
                    'tax_21': importeIVA, # IVA
                    'taxed_6': porcentajeIVA, # Porcentaje IVA
                    'total': importeItem,
                    'pem_id': self.id
                })

        # Obtener tique
        tique = self.env.ref('l10n_ar.dc_t')

        print('Fecha      Descripcion           Gravado      IVA %        IVA      Total')
        for fecha, items in comprobantes.items():
            # # Create Invoice
            # move = self.env['account.move'].create({
            #     'move_type': 'out_invoice',
            #     'partner_id': 7, # TODO: Consumidor Final
            #     'journal_id': self.journal.id,
            #     'date': fecha,
            #     'invoice_date': fecha,
            #     'l10n_latam_document_type_id': tique.id,
            #     # TODO: Chequear (y validar) secuencia en PG
            #     # TODO: Revisar este valor del Z???
            #     # 'l10n_latam_document_number': '{}-{}'.format(self.f8010_pos, invoice.number),
            # })

            # range_from = fields.Integer(string="Comprobante Desde")
            # range_to = fields.Integer(string="Comprobante Hasta")
            # total = fields.Float(string="Total")

            for desc, item in items.items():
                print('{} {:<20} {:>8.2f} {:>10} {:>10.2f} {:>10.2f} {}'.format(
                    fecha, 
                    desc, 
                    item['importeGravado'],
                    item['porcentajeIVA'], 
                    item['importeIVA'], 
                    item['importeItem'],
                    item['codigoCondicionIVA']))

                invoice_data = {
                    'date': fecha,
                    # 'range_from': int(text_z_range_from),
                    # 'range_to': int(text_z_range_to),
                    'description': desc,
                    'total': float(item['importeItem']),
                    'pem_id': self.id,
                    'taxed_21': 0,
                    'tax_21': 0,
                    'taxed_6': 0,
                    'tax_6': 0,
                    'untaxed': 0,
                    'exempt': 0
                }

                # TODO: borrar lo innecesario
                # self.f8010_invoice_ids.create({
                #     'number': item['comprobante_desde'],
                #     'description': desc,
                #     'date': fecha,
                #     'taxed_21': item['importeGravado'],   # Gravado
                #     'tax_21': item['importeIVA'], # IVA
                #     'taxed_6': item['porcentajeIVA'], # Porcentaje IVA
                #     'total': item['importeGravado'] + item['importeIVA'],
                #     'pem_id': self.id
                # })

                # if item['porcentajeIVA'] == '21.00':
                #     # IVA 21%
                #     invoice_data['taxed_21'] = float(item['importeGravado'])
                #     invoice_data['tax_21'] = float(item['importeIVA'])

                #     line = move.line_ids.create({
                #         'move_id': move.id,
                #         'name': desc,
                #         'account_id': self.account_sale.id,
                #         'quantity': 1,
                #         # TODO: chequear que el impuesto este incluido en el precio
                #         'price_unit': invoice_data['taxed_21'] + invoice_data['tax_21'],
                #     })
                #     line.tax_ids += self.tax_21
                # elif item['porcentajeIVA'] == '6.00':
                #     invoice_data['taxed_6'] = float(item['importeGravado'])
                #     invoice_data['tax_6'] = float(item['importeIVA'])

                #     taxed_21 = invoice_data['tax_6']/ 0.21
                #     tax_21 = invoice_data['tax_6']
                #     untaxed = invoice_data['taxed_6'] - taxed_21

                #     # Crear linea de Monto Gravado al 21%
                #     line = move.line_ids.create({
                #         'move_id': move.id,
                #         'name': '{} (Monto Gravado 21%)'.format(desc),
                #         'account_id': self.account_sale.id,
                #         'quantity': 1,
                #         'price_unit': taxed_21 + tax_21,
                #     })
                #     line.tax_ids += self.tax_21

                #     # Crear linea de Monto Exento
                #     line = move.line_ids.create({
                #         'move_id': move.id,
                #         'name': '{} (Monto Exento)'.format(desc),
                #         'account_id': self.account_sale.id,
                #         'quantity': 1,
                #         'price_unit': untaxed,
                #     })
                #     line.tax_ids += self.tax_exempt
                # elif item['porcentajeIVA'] == '0.00' and item['codigoCondicionIVA'] == '1':
                #     # No gravado
                #     invoice_data['untaxed'] = float(item['importeItem'])
                    
                #     line = move.line_ids.create({
                #         'move_id': move.id,
                #         'name': desc,
                #         'account_id': self.account_sale.id,
                #         'quantity': 1,
                #         'price_unit': invoice_data['untaxed'],
                #     })
                #     line.tax_ids += self.tax_untaxed
                # elif item['porcentajeIVA'] == '0.00' and item['codigoCondicionIVA'] == '2':
                #     # Exento
                #     invoice_data['exempt'] = float(item['importeItem'])
                    
                #     line = move.line_ids.create({
                #         'move_id': move.id,
                #         'name': desc,
                #         'account_id': self.account_sale.id,
                #         'quantity': 1,
                #         'price_unit': invoice_data['exempt'],
                #     })
                #     line.tax_ids += self.tax_exempt
                # else:
                #     raise UserError("IVA desconocido {} {}".format(item['porcentajeIVA'], item['codigoCondicionIVA']))

                # TODO: mostrar previsualizacion correcta en la UI
                # self.env["l10n_ar.import.sale.pem.f8010.line"].create(invoice_data)
            
            # TODO: Add note with invoice range
            # display_type = line_note

            # Recalculate totals
            # move._recompute_dynamic_lines(recompute_all_taxes=True, recompute_tax_base_amount=True)
            # move._recompute_payment_terms_lines()
            # move._compute_amount()
                
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

        # TODO: retornar vista de los tiques creados. Asi retorna una lista generica
        return {
            # 'context': self.env.context,
            'name': 'Comprobantes Emitidos',
            'view_mode': 'tree,form',
            # 'view_type': 'form',
            'res_model': 'account.move',
            # 'res_ids': [ 1, 2 ],
            # 'view_id': self.env.ref('pyme_accounting.action_move_out_invoice_type').id,
            'type': 'ir.actions.act_window',
            'target': 'primary',
            'domain': [('move_type', '=', 'out_invoice')],
            'default_move_type': 'out_invoice',
        }

    # TODO: seems to be a bug in Odoo 14.0 https://github.com/odoo/odoo/pull/59740
    @api.depends('f8011_file')
    def compute_f8011(self):
        [data] = self.read()

        if not data['f8011_file']:
            raise UserError("Debes cargar el archivo de ventas F8011")

        # TODO: error handling si el formato es incorrecto o es otro formulario
        # TODO: borrar los registros cargados anteriormente
        # TODO: Chequear CUIT con el de la empresa o tirar error
        # TODO: Chequear siguiente comprobante con el metodo _get_last_sequence()

        # Convertir PEM a XML
        root = self._parse_pem(data['f8011_file'])

        # text_date = root.findtext('fechaHoraEmisionAuditoria')
        emisor = root.find('emisor')
        text_cuit = emisor.findtext('cuitEmisor')
        text_pdv = emisor.findtext('numeroPuntoVenta')

        self.f8011_cuit = text_cuit
        self.f8011_pos = int(text_pdv)

        # Borrar comprobantes cargados anteriormente
        # TODO: Borrar esto una vez que este funcionando. Puede ser util cargar varios PEM
        self.write({ 'invoice_ids': [(5, 0, 0)] })

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

            for cierreZFecha in comprobanteAuditoria.find('arrayCierresZ').findall('cierreZFecha'):
                text_z_date = cierreZFecha.findtext('fechaHoraEmisionCierreZ')
                cierreZ = cierreZFecha.find('cierreZ')
                text_z_number = cierreZ.findtext('numeroZ')
                text_z_taxed = cierreZ.findtext('totalGravadoComprobantesFiscales')
                text_z_untaxed = cierreZ.findtext('totalNoGravadoComprobantesFiscales')
                text_z_exempt = cierreZ.findtext('totalExentoComprobantesFiscales')
                text_z_total = cierreZ.findtext('importeTotalComprobantesFiscales')
                
                comp_fiscales = cierreZ.find('arrayConjuntosComprobantesFiscales').find('conjuntoComprobantesFiscales')

                _logger.info('Comprobante {}'.format(text_z_number))
                _logger.info('  - Fecha de Cierre: {}'.format(text_z_date))
                _logger.info('  - Gravado:        {}'.format(text_z_taxed))
                _logger.info('  - No Gravado:     {}'.format(text_z_untaxed))
                _logger.info('  - Exento:         {}'.format(text_z_exempt))
                _logger.info('  - Total:          {}'.format(text_z_total))

                invoice_data = {
                    'date': text_z_date[:10], # 2021-02-20T...
                    'number': text_z_number,
                    'taxed': float(text_z_taxed),
                    'untaxed': float(text_z_untaxed),
                    'exempt': float(text_z_exempt),
                    'total': float(text_z_total),
                    'pem_id': self.id,
                    'tax_21': 0,
                    'tax_6': 0
                }

                # A veces la lista de comprobantes esta vacia
                # TODO: Controlar que esto genere correctamente las ventas
                # En el IVA digital, se debe agregar una linea con el numero del comprobante Z, con todo en 0, 
                # con operacion E (Exento) y con 1 alicuota en 0 (codigo 3)
                if comp_fiscales:
                    # text_z_codigo_comprobante = comp_fiscales.findtext('codigoTipoComprobante') # 83
                    text_z_range_from = comp_fiscales.findtext('primerNumeroComprobante')
                    text_z_range_to = comp_fiscales.findtext('ultimoNumeroComprobante')
                
                    invoice_data['range_from'] = int(text_z_range_from)
                    invoice_data['range_to'] = int(text_z_range_to)

                for subtotalIVA in cierreZ.find('arraySubtotalesIVA').findall('subtotalIVA'):
                    text_vat_percentage = subtotalIVA.findtext('porcentajeIVA')
                    text_vat_subtotal = subtotalIVA.findtext('importe')
                    
                    # TODO: tener en cuenta otros tipos de IVA
                    if text_vat_percentage == '21.00':
                        invoice_data['tax_21'] = float(text_vat_subtotal)
                    elif text_vat_percentage == '6.00':
                        invoice_data['tax_6'] = float(text_vat_subtotal)
                    else:
                        raise UserError("IVA desconocido {}".format(text_vat_percentage))

                self.env["l10n_ar.import.sale.pem.line"].create(invoice_data)

        # Fill relations
        self._find_relations()
        self.journal = self.get_pos(int(text_pdv))

        # TODO: chequear starting sequence aca

        # Si ya esta cargado el F8010, agrupar los productos por Z
        if self.f8010_invoice_ids:
            # TODO: descomentar esta linea
            # self.write({ 'f8010_grouped_ids', [(5, 0, 0)] })

            for z in self.invoice_ids:
                cbtes = self.f8010_invoice_ids.filtered(lambda i: i.number >= z.range_from and i.number <= z.range_to)
                _logger.info("Comprobante Z {}: {} individuales".format(z.number, len(cbtes)))
                products = list(dict.fromkeys(cbtes.mapped('description')))
                _logger.info("Productos: {}".format(products))
                for p in products:
                    product_items = cbtes.filtered(lambda i: i.description == p)
                    tot = sum(product_items.mapped('total'))

                    self.f8010_grouped_ids.create({
                        'z': z.number,
                        'description': p,
                        'total': tot,
                        'pem_id': self.id
                    })

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

    def show_pivot(self):
        return {
            'name': "Detalle Items",
            'context': self.env.context,
            'view_type': 'pivot',
            'view_mode': 'pivot',
            'res_model': 'l10n_ar.import.sale.pem.f8010.grouped',
            # 'res_id': self.f8010_grouped_ids.id,
            'domain': [ ('pem_id', '=', self.id) ],
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'current',
        }

    def generate_f8011(self):
        # Obtener tique
        tique = self.env.ref('l10n_ar.dc_t')

        for invoice in self.invoice_ids:
            # Create Invoice
            move = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': 7, # TODO: Consumidor Final
                'journal_id': self.journal.id,
                'date': invoice.date,
                'invoice_date': invoice.date,
                'l10n_latam_document_type_id': tique.id,
                # TODO: Chequear (y validar) secuencia en PG
                'l10n_latam_document_number': '{}-{}'.format(self.f8011_pos, invoice.number),
                'z_desde': invoice.range_from,
                'z_hasta': invoice.range_to,
            })

            # Valor "Gravado" que no se utilizo (solo ocurre con el cigarrillo)
            taxed_not_used = invoice.taxed

            # IVA 21%
            if (invoice.tax_21 > 0):
                # El monto gravado puede estar mezclado con otros, por lo que se
                # determina el valor especifico para este IVA,
                # y se descuenta del valor original
                t = invoice.tax_21 / 0.21
                taxed_not_used -= t

                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto Gravado al 21%',
                    'account_id': self.account_sale.id,
                    'quantity': 1,
                    'price_unit': t + (invoice.tax_21 if self.tax_21.price_include else 0),
                })
                line.tax_ids += self.tax_21

            # IVA No Gravado
            if invoice.untaxed > 0:
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto No Gravado',
                    'account_id': self.account_sale.id,
                    'quantity': 1,
                    'price_unit': invoice.untaxed,
                })
                line.tax_ids += self.tax_untaxed

            # IVA Exento (o comprobante en 0)
            if invoice.exempt > 0 or invoice.total == 0:
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto Exento',
                    'account_id': self.account_sale.id,
                    'quantity': 1,
                    'price_unit': invoice.exempt,
                })
                line.tax_ids += self.tax_exempt

            # IVA 6% (convertido a 21% y Exento)
            if invoice.tax_6 > 0:
                taxed_21 = invoice.tax_6 / 0.21
                tax_21 = invoice.tax_6
                taxed_not_used -= taxed_21

                # Crear linea de Monto Gravado al 21%
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': '[IVA 6%] Monto Gravado al 21%',
                    'account_id': self.account_sale.id,
                    'quantity': 1,
                    'price_unit': taxed_21 + tax_21,
                })
                line.tax_ids += self.tax_21

                # Crear linea de Monto No Gravado
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': '[IVA 6%] Monto No Gravado',
                    'account_id': self.account_sale.id,
                    'quantity': 1,
                    'price_unit': taxed_not_used,
                })
                line.tax_ids += self.tax_untaxed

            # Recalculate totals
            move._recompute_dynamic_lines(recompute_all_taxes=True, recompute_tax_base_amount=True)
            move._recompute_payment_terms_lines()
            move._compute_amount()

        # TODO: retornar vista de los tiques creados. Asi retorna una lista generica
        return {
            # 'context': self.env.context,
            'name': 'Comprobantes Emitidos',
            'view_mode': 'tree,form',
            # 'view_type': 'form',
            'res_model': 'account.move',
            # 'res_ids': [ 1, 2 ],
            # 'view_id': self.env.ref('pyme_accounting.action_move_out_invoice_type').id,
            'type': 'ir.actions.act_window',
            'target': 'main',
            'domain': [('move_type', '=', 'out_invoice')],
            'default_move_type': 'out_invoice',
        }
