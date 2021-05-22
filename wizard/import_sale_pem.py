# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import io
import base64
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

class SaleImportPEM(models.Model):
    _name = "l10n_ar.import.sale.pem"
    _description = 'Importar archivo de Controlador Fiscal PEM'

    # TODO
    # pem_type = fields.Select(string="Tipo", options=['f8010', 'f8011'])

    # Listado de comprobantes individuales
    f8010_file = fields.Binary(string="Archivo F8010 (*.pem)")

    # Listado de comprobantes Z
    f8011_file = fields.Binary(string="Archivo F8011 (*.pem)")

    # TODO
    # start_date = fields.Date(string="Fecha Desde")
    # end_date = fields.Date(string="Fecha Hasta")
    # start_number = field.Number
    # end_number = field.Number

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
        tax_excempt = self.env['account.tax'].search([
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
                    line.tax_ids += tax_excempt
                else:
                    print('IVA Desconocido: ', numeroComprobante)

            # Recalculate totals
            move._recompute_dynamic_lines(recompute_all_taxes=True, recompute_tax_base_amount=True)
            move._recompute_payment_terms_lines()
            move._compute_amount()

    # TODO: Compute F80811
    def compute_f8011(self):
        [data] = self.read()

        if not data['f8011_file']:
            raise UserError("Debes cargar el archivo de ventas F8011")

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

        for comprobanteAuditoria in root.find('arrayComprobantesAuditoria').findall('comprobanteAuditoria'):
            rango = comprobanteAuditoria.find('rangoEncontrado')

            text_number_from = rango.findtext('numeroZDesde')
            text_number_to = rango.findtext('numeroZHasta')
            text_date_from = rango.findtext('fechaZDesde')
            text_date_to = rango.findtext('fechaZHasta')
            
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
                text_z_excempt = cierreZ.findtext('totalExentoComprobantesFiscales')
                text_z_total = cierreZ.findtext('importeTotalComprobantesFiscales')

                # TODO: primer/ultimo comprobante
                
                print('Comprobante', text_z_number)
                print('  - Fecha de Cierre:', text_z_date)
                print('  - Gravado:        ', text_z_taxed)
                print('  - No Gravado:     ', text_z_untaxed)
                print('  - Exento:         ', text_z_excempt)
                print('  - Total:          ', text_z_total)

                for subtotalIVA in cierreZ.find('arraySubtotalesIVA').findall('subtotalIVA'):
                    text_vat_percentage = subtotalIVA.findtext('porcentajeIVA')
                    text_vat_subtotal = subtotalIVA.findtext('importe')
                    
                    print('  - {}%: {}'.format(text_vat_percentage, text_vat_subtotal))

                print()