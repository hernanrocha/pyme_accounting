# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import xml.etree.ElementTree as ET
import base64
import logging
import xlrd
from datetime import datetime

_logger = logging.getLogger(__name__)

def es_comprobante_c(invoice_code):
    # Factura C, Nota de Debito C, Nota de Credito C, Recibo C
    return invoice_code in [11, 12, 13, 15]

# TODO: credito_fiscal invalido
# TODO: cargar los otros tipos de IVA que no sean 21%

# TODO: revisar comprobantes con 0$
# TODO: falta cargar IIBB
# TODO: unificar comprobantes + notas de credito

class ImportPurchaseRg3685(models.TransientModel):
    _name = "l10n_ar.import.purchase.rg3685"
    _description = "Importar Compras RG3685"

    file_cbtes = fields.Binary(string="Archivo Compras Cbtes (*.txt)")
    file_alicuotas = fields.Binary(string="Archivo Compras Alicuotas (*.txt)")

    period_start = fields.Date(string="Periodo Desde")
    period_end = fields.Date(string="Periodo Hasta")
    # invoice_ids = fields.One2many(string="Retenciones", comodel_name="l10n_ar.import.afip.retenciones.line", inverse_name="import_id")
    
    def compute(self):
        [data] = self.read()

        if not data['file_cbtes'] or not data['file_alicuotas']:
            raise UserError("Debes cargar un archivo valido")
        
        # Borrar registros anteriores
        # self.write({ 'invoice_ids': [(5, 0, 0)] })

        # Leer archivo AFIP de compras
        file_cbtes_content = base64.decodebytes(data['file_cbtes']).splitlines()
        file_alicuotas_content = base64.decodebytes(data['file_alicuotas']).splitlines()

        lines_cbtes = []
        lines_alicuotas = []

        # Compras Comprobantes
        for x in file_cbtes_content:
            _logger.info(x)
            compra = { 
                "fecha": x[:8].decode('ascii'), 
                "tipo_comprobante": int(x[8:11]), 
                "punto_de_venta": int(x[11:16]), 
                "numero_comprobante_desde": int(x[16:36]), 
                "depacho_importacion": x[36:52].strip(), 
                "doc_codigo_comprador": int(x[52:54]), 
                "doc_numero_comprador": str(int(x[54:74])), 
                "nombre_comprador": x[74:104].strip().decode('ascii'), 
                "total": float(x[104:119])/100,
                "total_no_gravado": float(x[119:134])/100,
                "total_exento": float(x[134:149])/100,
                "total_perc_iva": float(x[149:164])/100,
                "total_perc_nacionales": float(x[164:179])/100,
                "total_perc_iibb": float(x[179:194])/100,
                "total_perc_municipales": float(x[194:209])/100,
                "total_imp_internos": float(x[209:224])/100,
                "codigo_moneda": x[224:227],
                "tipo_cambio": float(x[227:237])/1000000,
                "cant_alic_iva": int(x[237:238]),
                "codigo_operacion": x[238:239],
                "credito_fiscal": float(x[239:254])/100,
                "otros_tributos": float(x[254:269])/100,
            }

            lines_cbtes.append(compra)

        # Compras Alicuotas
        for x in file_alicuotas_content:
            a = { 
                "tipo_comprobante": int(x[:3]),
                "punto_de_venta": int(x[3:8]),
                "num_comprobante": int(x[8:28]),
                "tipo_documento": int(x[28:30]),
                "numero_documento": x[30:50],
                "importe_gravado": float(x[50:65])/100,
                "codigo_iva": int(x[65:69]),
                "valor_iva": float(x[69:84])/100,
            }
            
            lines_alicuotas.append(a)

        _logger.info(lines_cbtes)
        _logger.info(lines_alicuotas)

        # TODO: USAR MIXIN
        tax_untaxed = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', '=', 'IVA No Gravado'),
        ])

        tax_21 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', '=', 'IVA 21%'),
        ])

        tax_10 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', '=', 'IVA 10.5%'),
        ])

        tax_27 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', '=', 'IVA 27%'),
        ])

        tax_25 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', '=', 'IVA 2,5%'),
        ])

        tax_5 = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', '=', 'IVA 5%'),
        ])

        tax_exempt = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', '=', 'IVA Exento'),
        ])

        tax_no_corresponde = self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('name', '=', 'IVA No Corresponde'),
        ])

        # Obtener diario de proveedores
        journal = self.env['account.move'].with_context(default_move_type='in_invoice')._get_default_journal()

        # Obtener condicion fiscal RI y Monotributo       
        ri = self.env.ref('l10n_ar.res_IVARI')
        monotributo = self.env.ref('l10n_ar.res_RM')
    
        # Obtener tipo de identificacion CUIT
        # TODO: tener en cuenta DNIs para compras de consumidores finales
        cuit_type = self.env.ref('l10n_ar.it_cuit')

        account_purchase = self.env['account.account'].search([
            # TODO: hacer dependiente de la compañia 
            ('company_id', '=', self.env.company.id),
            ('code', '=', '5.1.1.01.030'),
            ('name', '=', 'Compra de mercadería'),
        ])

        for cbte in lines_cbtes:
            alicuotas = filter(
                lambda x: x["num_comprobante"] == cbte["numero_comprobante_desde"],
                lines_alicuotas)

            _logger.info("Alicuotas en {}: {}".format(cbte["numero_comprobante_desde"], alicuotas))

            partner = self.env['res.partner'].search([('vat', '=', cbte["doc_numero_comprador"])])        
            partner_data = { 
                'type': 'contact',
                'name': cbte["nombre_comprador"],
                'vat': cbte["doc_numero_comprador"],
                'l10n_latam_identification_type_id': cuit_type.id,
                # TODO: Si es factura C, cargar como monotributo/exento
                # Para esto se debe poder consultar la API de CUITs
                'l10n_ar_afip_responsibility_type_id': monotributo.id if es_comprobante_c(cbte["tipo_comprobante"]) else ri.id 
            }
            if len(partner) == 0:
                # Crear nuevo proveedor
                _logger.info("Creating partner: {}".format(partner_data))
                partner = self.env['res.partner'].create(partner_data)
            else:
                # Actualizar datos del proveedor
                partner = partner[0]

            # Create Invoice
            doc_type = self.env['l10n_latam.document.type'].get_by_prefix(cbte["tipo_comprobante"])

            # Cuando es comprobante C, generado por monotributo/exento,
            # se debe colocar "IVA No Corresponde"
            no_iva = doc_type.purchase_aliquots == 'zero'

            invoice_date = datetime.strptime(cbte["fecha"], '%Y%m%d').date()
            account_date = invoice_date if self.period_start and invoice_date > self.period_start else \
                self.period_start

            move_data = {
                'move_type': 'in_refund' if doc_type.internal_type == 'credit_note' else 'in_invoice',
                'partner_id': partner.id,
                'journal_id': journal.id,
                'date': account_date,
                'invoice_date': invoice_date,
                'l10n_latam_document_type_id': doc_type.id,
                'l10n_latam_document_number': '{}-{}'.format(cbte["punto_de_venta"], cbte["numero_comprobante_desde"]),
            }
            _logger.info("Invoice Data: {}".format(move_data))

            move = self.env['account.move'].create(move_data)

            # Cargar alicuotas de IVA
            for alic in alicuotas:
                cod = alic["codigo_iva"]
                
                if cod == 4:
                    line = move.line_ids.create({
                        'move_id': move.id,
                        'name': 'Monto Gravado 10.5%',
                        'account_id': account_purchase.id,
                        'quantity': 1,
                        'price_unit': alic["importe_gravado"] + (alic["valor_iva"] if tax_10.price_include else 0),
                    })
                    line.tax_ids += tax_no_corresponde if no_iva else tax_10
                elif cod == 5:
                    line = move.line_ids.create({
                        'move_id': move.id,
                        'name': 'Monto Gravado 21%',
                        'account_id': account_purchase.id,
                        'quantity': 1,
                        'price_unit': alic["importe_gravado"] + (alic["valor_iva"] if tax_21.price_include else 0),
                    })
                    line.tax_ids += tax_no_corresponde if no_iva else tax_21
                elif cod == 6:
                    line = move.line_ids.create({
                        'move_id': move.id,
                        'name': 'Monto Gravado 27%',
                        'account_id': account_purchase.id,
                        'quantity': 1,
                        'price_unit': alic["importe_gravado"] + (alic["valor_iva"] if tax_27.price_include else 0),
                    })
                    line.tax_ids += tax_no_corresponde if no_iva else tax_27
                elif cod == 8:
                    line = move.line_ids.create({
                        'move_id': move.id,
                        'name': 'Monto Gravado 5%',
                        'account_id': account_purchase.id,
                        'quantity': 1,
                        'price_unit': alic["importe_gravado"] + (alic["valor_iva"] if tax_5.price_include else 0),
                    })
                    line.tax_ids += tax_no_corresponde if no_iva else tax_5
                elif cod == 9:
                    line = move.line_ids.create({
                        'move_id': move.id,
                        'name': 'Monto Gravado 2.5%',
                        'account_id': account_purchase.id,
                        'quantity': 1,
                        'price_unit': alic["importe_gravado"] + (alic["valor_iva"] if tax_25.price_include else 0),
                    })
                    line.tax_ids += tax_no_corresponde if no_iva else tax_25

            # IVA No Gravado
            if cbte["total_no_gravado"] > 0:
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto No Gravado',
                    'account_id': account_purchase.id,
                    'quantity': 1,
                    'price_unit': cbte["total_no_gravado"],
                })
                line.tax_ids += tax_no_corresponde if no_iva else tax_untaxed

            # IVA Exento
            if cbte["total_exento"] > 0:
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto Exento',
                    'account_id': account_purchase.id,
                    'quantity': 1,
                    'price_unit': cbte["total_exento"],
                })
                line.tax_ids += tax_no_corresponde if no_iva else tax_exempt

            # IVA No Corresponde (solo para Comprobantes C)
            if cbte["total"] > move.amount_total and es_comprobante_c(cbte["tipo_comprobante"]):
                line = move.line_ids.create({
                    'move_id': move.id,
                    'name': 'Monto No Gravado',
                    'account_id': account_purchase.id,
                    'quantity': 1,
                    'price_unit': cbte["total"] - move.amount_total,
                })
                line.tax_ids += tax_no_corresponde

            # TODO: Importar percepciones IIBB y otras

            # Recalculate totals
            move._recompute_dynamic_lines(recompute_all_taxes=True, recompute_tax_base_amount=True)
            move._recompute_payment_terms_lines()
            move._compute_amount()

        # TODO: mostrar mensaje success

    # TODO: Permitir editar antes de importar
    def generate(self):
        pass
