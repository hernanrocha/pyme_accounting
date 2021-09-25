# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import xml.etree.ElementTree as ET
import base64
import logging
import xlrd
from datetime import datetime

_logger = logging.getLogger(__name__)

class ImportSaleRg3685(models.TransientModel):
    _name = "l10n_ar.import.sale.rg3685"
    _description = "Importar Ventas RG3685"

    file_cbtes = fields.Binary(string="Archivo Ventas Cbtes (*.txt)")
    file_alicuotas = fields.Binary(string="Archivo Ventas Alicuotas (*.txt)")

    # invoice_ids = fields.One2many(string="Retenciones", comodel_name="l10n_ar.import.afip.retenciones.line", inverse_name="import_id")
    
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
                'name': 'PDV {} - Comprobantes Emitidos'.format(pos_number),
                'type': 'sale',
                'l10n_latam_use_documents': True,
                'l10n_ar_afip_pos_number': pos_number,
                # TODO: definir si es factura en linea (RLI_RLM), webservice o controlador fiscal
                'l10n_ar_afip_pos_system': 'RLI_RLM',
                'l10n_ar_afip_pos_partner_id': self.env.company.partner_id.id,
                'default_account_id': account_sale.id,
                'code': str(pos_number).zfill(5),
            })
        
        return journal.id


    def compute(self):
        [data] = self.read()

        if not data['file_cbtes'] or not data['file_alicuotas']:
            raise UserError("Debes cargar un archivo valido")
        
        # Borrar registros anteriores
        # self.write({ 'invoice_ids': [(5, 0, 0)] })

        # TODO: soportar ventas (tipo de documento 46, doc 11111111)

        # Leer archivo AFIP de compras
        file_cbtes_content = base64.decodebytes(data['file_cbtes']).splitlines()
        file_alicuotas_content = base64.decodebytes(data['file_alicuotas']).splitlines()

        lines_cbtes = []
        lines_alicuotas = []

        # Ventas Comprobantes
        for x in file_cbtes_content:
            venta = { 
                "fecha": x[:8].decode('ascii'), 
                "tipo_comprobante": int(x[8:11]), 
                "punto_de_venta": int(x[11:16]), 
                "numero_comprobante_desde": int(x[16:36]), 
                "numero_comprobante_hasta": int(x[36:56]), 
                "doc_codigo_comprador": int(x[56:58]), 
                "doc_numero_comprador": str(int(x[58:78])), 
                "nombre_comprador": x[78:108].strip().decode('ascii'), 
                "total": float(x[108:123])/100,
                "total_no_gravado": float(x[123:138])/100,
                "percepcion_no_categorizados": float(x[138:153])/100,
                "total_exento": float(x[153:168])/100,
                "total_perc_nacionales": float(x[168:183])/100,
                "total_perc_iibb": float(x[183:198])/100,
                "total_perc_municipales": float(x[198:213])/100,
                "total_imp_internos": float(x[213:228])/100,
                "codigo_moneda": x[228:231],
                "tipo_cambio": float(x[231:241])/1000000,
                "cant_alic_iva": int(x[241:242]),
                "codigo_operacion": x[242:243],
                "otros_tributos": float(x[243:258])/100,
                "fecha_vencimiento": x[258:266],
            }
                
            lines_cbtes.append(venta)

        # Ventas Alicuotas
        for x in file_alicuotas_content:
            a = { 
                "tipo_comprobante": int(x[:3]),
                "punto_de_venta": int(x[3:8]),
                "num_comprobante": int(x[8:28]),
                "importe_gravado": float(x[28:43])/100,
                "codigo_iva": int(x[43:47]),
                "valor_iva": float(x[47:62])/100,
            }

            lines_alicuotas.append(a)

        _logger.info(lines_cbtes)
        _logger.info(lines_alicuotas)

        # Consumidor Final
        consumidor_final = self.env['res.partner'].search([('name', '=', 'Consumidor Final Anónimo')])
        _logger.info("Consumidor Final: {}".format(consumidor_final))

        # Obtener tipo de identificacion CUIT
        cuit_type = self.env.ref('l10n_ar.it_cuit') 
        
        # Obtener condicion fiscal consumidor final, RI, Monotributo
        cf = self.env.ref('l10n_ar.res_CF')
        # ri = self.env.ref('l10n_ar.res_IVARI')
        # monotributo = self.env.ref('l10n_ar.res_RM')

        account_sale = self.env['account.account'].search([
            # TODO: hacer dependiente de la compañia
            ('company_id', '=', self.env.company.id),
            ('code', '=', '4.1.1.01.010'),
            ('name', '=', 'Venta de mercadería'),
        ])

        tax_untaxed = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA No Gravado'),
        ])
        
        tax_21 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA 21%'),
        ])

        tax_10 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA 10.5%'),
        ])

        tax_27 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA 27%'),
        ])

        tax_25 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', '=', 'IVA 2,5%'),
        ])

        tax_5 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA 5%'),
        ])

        tax_exempt = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('name', '=', 'IVA Exento'),
        ])

        for cbte in lines_cbtes:
            # Obtener/Crear diario segun el PdV automaticamente
            journal_id = self.get_pos(cbte["punto_de_venta"])

            tipo_doc = cbte["doc_codigo_comprador"]
            # Tipo de Documento CUIT
            if tipo_doc == 80:
                # Get or Create Customer Partner (res.partner)
                partner = self.env['res.partner'].search([('vat', '=', cbte["doc_numero_comprador"])])
                partner_data = {
                    'type': 'contact',
                    'name': cbte["nombre_comprador"],
                    'vat': cbte["doc_numero_comprador"],
                    'l10n_latam_identification_type_id': cuit_type.id,
                    # TODO: Si es Resp Inscripto, corroborar si es monotributo/RI
                    'l10n_ar_afip_responsibility_type_id': cf.id
                }
                print("PartnerData", partner_data)
                if len(partner) == 0:
                    partner = self.env['res.partner'].create(partner_data)
                else:
                    # Actualizar datos del cliente
                    partner = partner[0]
            else:
                partner = consumidor_final
            
            _logger.info("Partner: {}".format(partner))

            # Alicuotas de IVA
            alicuotas = filter(
                lambda x: x["num_comprobante"] == cbte["numero_comprobante_desde"],
                lines_alicuotas)

            # Create Invoice
            # TODO: mejorar esta query
            doc_type = self.env['l10n_latam.document.type'].search([('code', '=', cbte["tipo_comprobante"])])

            move_data = {
                'move_type': 'out_invoice',
                'partner_id': partner.id,
                'journal_id': journal_id,
                'date': datetime.strptime(cbte["fecha"], '%Y%m%d'),
                'invoice_date': datetime.strptime(cbte["fecha"], '%Y%m%d'),
                'l10n_latam_document_type_id': doc_type.id,
                # TODO: Chequear (y validar) secuencia en PG
                'l10n_latam_document_number': '{}-{}'.format(cbte["punto_de_venta"], cbte["numero_comprobante_desde"]),
            }
            
            # Para comprobantes Z, establecer valores desde/hasta
            if cbte["tipo_comprobante"] == 83:
                move_data['z_desde'] = cbte["numero_comprobante_desde"]
                move_data['z_hasta'] = cbte["numero_comprobante_hasta"]
            
            _logger.info("Invoice Data: {}".format(move_data))
            move = self.env['account.move'].create(move_data)
            _logger.info("Invoice: {}".format(move))

            # Cargar alicuotas de IVA
            for alic in alicuotas:
                cod = alic["codigo_iva"]
                
                if cod == 4:
                    line = move.line_ids.create({
                        'move_id': move.id,
                        'name': 'Monto Gravado 10.5%',
                        'account_id': account_sale.id,
                        'quantity': 1,
                        'price_unit': alic["importe_gravado"] + (alic["valor_iva"] if tax_10.price_include else 0),
                    })
                    line.tax_ids += tax_10
                elif cod == 5:
                    line = move.line_ids.create({
                        'move_id': move.id,
                        'name': 'Monto Gravado 21%',
                        'account_id': account_sale.id,
                        'quantity': 1,
                        'price_unit': alic["importe_gravado"] + (alic["valor_iva"] if tax_21.price_include else 0),
                    })
                    line.tax_ids += tax_21
                elif cod == 6:
                    line = move.line_ids.create({
                        'move_id': move.id,
                        'name': 'Monto Gravado 27%',
                        'account_id': account_sale.id,
                        'quantity': 1,
                        'price_unit': alic["importe_gravado"] + (alic["valor_iva"] if tax_27.price_include else 0),
                    })
                    line.tax_ids += tax_27
                elif cod == 8:
                    line = move.line_ids.create({
                        'move_id': move.id,
                        'name': 'Monto Gravado 5%',
                        'account_id': account_sale.id,
                        'quantity': 1,
                        'price_unit': alic["importe_gravado"] + (alic["valor_iva"] if tax_5.price_include else 0),
                    })
                    line.tax_ids += tax_5
                elif cod == 9:
                    line = move.line_ids.create({
                        'move_id': move.id,
                        'name': 'Monto Gravado 2.5%',
                        'account_id': account_sale.id,
                        'quantity': 1,
                        'price_unit': alic["importe_gravado"] + (alic["valor_iva"] if tax_25.price_include else 0),
                    })
                    line.tax_ids += tax_25

            # IVA No Gravado
            if cbte["total_no_gravado"] > 0:
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto No Gravado',
                    'account_id': account_sale.id,
                    'quantity': 1,
                    'price_unit': cbte["total_no_gravado"],
                })
                line.tax_ids += tax_untaxed

            # IVA Exento
            if cbte["total_exento"] > 0:
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto Exento',
                    'account_id': account_sale.id,
                    'quantity': 1,
                    'price_unit': cbte["total_exento"],
                })
                line.tax_ids += tax_exempt

            # Recalculate totals
            move._recompute_dynamic_lines(recompute_all_taxes=True, recompute_tax_base_amount=True)
            move._recompute_payment_terms_lines()
            move._compute_amount()

            # Post Entry
            # move.action_post()

        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'l10n_ar.import.sale.rg3685',
            'res_id': self.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def generate(self):
        pass