##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from ast import literal_eval
import base64
import logging
import re

_logger = logging.getLogger(__name__)

# https://discuss.tryton.org/t/account-ar-argentine-localization/3261/4

# TODO: Mover esto a computed en account.move
def untaxed_exempt_line(line):
    codes = line.mapped('tax_ids').mapped('tax_group_id').mapped('l10n_ar_vat_afip_code')
    return '1' in codes or '2' in codes

def untaxed_line(line):
    codes = line.mapped('tax_ids').mapped('tax_group_id').mapped('l10n_ar_vat_afip_code')
    return '1' in codes
    
def exempt_line(line):
    codes = line.mapped('tax_ids').mapped('tax_group_id').mapped('l10n_ar_vat_afip_code')
    return '2' in codes

def taxed_0_line(line):
    codes = line.mapped('tax_ids').mapped('tax_group_id').mapped('l10n_ar_vat_afip_code')
    return '3' in codes

class AccountVatLedger(models.Model):
    _inherit = "account.vat.ledger"

    # TODO ?????
    digital_skip_invoice_tests = fields.Boolean(
        string='Saltear tests a facturas?',
        help='If you skip invoice tests probably you will have errors when '
        'loading the files in digital.'
    )
    digital_skip_lines = fields.Char(
        string="Lista de lineas a saltear con los archivos del digital",
        help="Enter a list of lines, for eg '1, 2, 3'. If you skip some lines "
        "you would need to enter them manually"
    )
    REGDIGITAL_CV_ALICUOTAS = fields.Text(
        'REGDIGITAL_CV_ALICUOTAS',
        readonly=True,
    )
    REGDIGITAL_CV_COMPRAS_IMPORTACIONES = fields.Text(
        'REGDIGITAL_CV_COMPRAS_IMPORTACIONES',
        readonly=True,
    )
    REGDIGITAL_CV_CBTE = fields.Text(
        'REGDIGITAL_CV_CBTE',
        readonly=True,
    )
    digital_vouchers_file = fields.Binary(
        string="Archivo Comprobantes",
        compute='_compute_digital_files',
        readonly=True
    )
    digital_vouchers_filename = fields.Char(
        compute='_compute_digital_files',
    )
    digital_aliquots_file = fields.Binary(
        string="Archivo Alícuotas",
        compute='_compute_digital_files',
        readonly=True
    )
    digital_aliquots_filename = fields.Char(
        readonly=True,
        compute='_compute_digital_files',
    )
    digital_import_aliquots_file = fields.Binary(
        compute='_compute_digital_files',
        readonly=True
    )
    digital_import_aliquots_filename = fields.Char(
        readonly=True,
        compute='_compute_digital_files',
    )
    prorate_tax_credit = fields.Boolean(
    )
    #prorate_type = fields.Selection(
    #    [('global', 'Global'), ('by_voucher', 'By Voucher')],
    #)
    #tax_credit_computable_amount = fields.Float(
    #    'Credit Computable Amount',
    #)
    #sequence = fields.Integer(
    #    default=0,
    #    required=True,
    #    help='Se deberá indicar si la presentación es Original (00) o '
    #    'Rectificativa y su orden'
    #)

    def format_amount(self, amount, padding=15, decimals=2, invoice=False):
        # get amounts on correct sign despite conifiguration on taxes and tax
        # codes
        # TODO
        # remove this and perhups invoice argument (we always send invoice)
        # for invoice refund we dont change sign (we do this before)
        # if invoice:
        #     amount = abs(amount)
        #     if invoice.type in ['in_refund', 'out_refund']:
        #         amount = -1.0 * amount
        # Al final volvimos a agregar esto, lo necesitabamos por ej si se pasa
        # base negativa de no gravado
        # si se usa alguno de estos tipos de doc para rectificativa hay que pasarlos restando
        # seguramente para algunos otros tambien pero realmente no se usan y el digital tiende a depreciarse
        # y el uso de internal_type a cambiar
        if invoice and invoice.l10n_latam_document_type_id.code in ['39', '40', '41', '66', '99'] \
           and invoice.type in ['in_refund', 'out_refund']:
            amount = -amount

        if amount < 0:
            template = "-{:0>%dd}" % (padding - 1)
        else:
            template = "{:0>%dd}" % (padding)
        return template.format(
            int(round(abs(amount) * 10**decimals, decimals)))

    def _compute_digital_files(self):
        self.ensure_one()
        # segun vimos aca la afip espera "ISO-8859-1" en vez de utf-8
        # http://www.planillasutiles.com.ar/2015/08/
        # como-descargar-los-archivos-de.html

        # Restablecer todos los datos
        self.digital_vouchers_file = False
        self.digital_vouchers_filename = False
        self.digital_aliquots_file = False
        self.digital_aliquots_filename = False
        self.digital_import_aliquots_file = False
        self.digital_import_aliquots_filename = False

        # Comprobantes
        if self.REGDIGITAL_CV_CBTE:
            # self.period_id.name
            # self.env.company_id.partner_id.vat
            if self.type == 'purchase':
                self.digital_vouchers_filename = 'Compras_Cbtes_{}.txt'.format(self.date_to)
            else:
                self.digital_vouchers_filename = 'Ventas_Cbtes_{}.txt'.format(self.date_to)

            self.digital_vouchers_file = base64.encodestring(
                self.REGDIGITAL_CV_CBTE.encode('ISO-8859-1'))

        # Alicuotas
        if self.REGDIGITAL_CV_ALICUOTAS:
            # self.period_id.name
            # self.env.company_id.partner_id.vat
            if self.type == 'purchase':
                self.digital_aliquots_filename = 'Compras_Alicuotas_{}.txt'.format(self.date_to)
            else:
                self.digital_aliquots_filename = 'Ventas_Alicuotas_{}.txt'.format(self.date_to)

            self.digital_aliquots_file = base64.encodestring(
                self.REGDIGITAL_CV_ALICUOTAS.encode('ISO-8859-1'))
        
        # Importaciones
        if self.REGDIGITAL_CV_COMPRAS_IMPORTACIONES:
            # self.period_id.name
            # self.env.company_id.partner_id.vat
            self.digital_import_aliquots_filename = 'Compras_Importaciones_{}.txt'.format(self.date_to)
            self.digital_import_aliquots_file = base64.encodestring(
                self.REGDIGITAL_CV_COMPRAS_IMPORTACIONES.encode('ISO-8859-1'))

    def compute_digital_data(self):
        if self.type == 'sale':
            alicuotas = self.get_REGDIGITAL_CV_ALICUOTAS_VENTAS()

            # sacamos todas las lineas y las juntamos
            lines = []
            for k, v in alicuotas.items():
                lines += v
            self.REGDIGITAL_CV_ALICUOTAS = '\r\n'.join(lines)
            _logger.info(self.REGDIGITAL_CV_ALICUOTAS)

            self.get_REGDIGITAL_CV_CBTE_VENTAS(alicuotas)
        else:
            alicuotas = self.get_REGDIGITAL_CV_ALICUOTAS_COMPRAS()

            # sacamos todas las lineas y las juntamos
            lines = []
            for k, v in alicuotas.items():
                lines += v
            self.REGDIGITAL_CV_ALICUOTAS = '\r\n'.join(lines)
            _logger.info(self.REGDIGITAL_CV_ALICUOTAS)

            impo_alicuotas = {}
            if self.type == 'purchase':
                impo_alicuotas = self.get_REGDIGITAL_CV_ALICUOTAS_COMPRAS(impo=True)
                # sacamos todas las lineas y las juntamos
                lines = []
                for k, v in impo_alicuotas.items():
                    lines += v
                self.REGDIGITAL_CV_COMPRAS_IMPORTACIONES = '\r\n'.join(lines)
            alicuotas.update(impo_alicuotas)
            self.get_REGDIGITAL_CV_CBTE_COMPRAS(alicuotas)

    def get_partner_document_code(self, partner):
        # se exige cuit para todo menos consumidor final.
        # TODO si es mayor a 1000 habria que validar reportar
        # DNI, LE, LC, CI o pasaporte
        if partner.l10n_ar_afip_responsibility_type_id.code == '5':
            #return "{:0>2d}".format(partner.l10n_latam_identification_type_id.l10n_ar_afip_code)
            res = str(partner.l10n_latam_identification_type_id.l10n_ar_afip_code).zfill(2)
            return res
        return '80'

    @api.model
    def get_partner_document_number(self, partner):
        # se exige cuit para todo menos consumidor final.
        # TODO si es mayor a 1000 habria que validar reportar
        # DNI, LE, LC, CI o pasaporte
        #if partner.l10n_ar_afip_responsibility_type_id.l10n_ar_afip_code == '5':
        if partner.l10n_ar_afip_responsibility_type_id.code == '5':
            number = partner.vat or ''
            # por las dudas limpiamos letras
            number = re.sub("[^0-9]", "", number)
        else:
            #number = partner.cuit_required()
            number = partner.vat
        return number.rjust(20, '0')

    @api.model
    def get_point_of_sale(self, invoice):
        if self.type == 'sale':
            return "{:0>5d}".format(invoice.journal_id.l10n_ar_afip_pos_number)
        else:
            return invoice.l10n_latam_document_number[:5]

    def action_see_skiped_invoices(self):
        invoices = self.get_digital_invoices(return_skiped=True)
        raise ValidationError(_('Facturas salteadas:\n%s') % ', '.join(invoices.mapped('display_name')))

    @api.constrains('digital_skip_lines')
    def _check_digital_skip_lines(self):
        for rec in self.filtered('digital_skip_lines'):
            try:
                res = literal_eval(rec.digital_skip_lines)
                if not isinstance(res, int):
                    assert isinstance(res, tuple)
            except Exception as e:
                raise ValidationError(_(
                    'Bad format for Skip Lines. You need to enter a list of '
                    'numbers like "1, 2, 3". This is the error we get: %s') % (
                        repr(e)))
    
    def get_digital_invoices(self, return_skiped=False):
        self.ensure_one()
        invoices = self.env['account.move'].search([
            # ('l10n_latam_document_type_id.export_to_digital', '=', True),
            ('id', 'in', self.invoice_ids.ids)], order='commercial_partner_name asc,sequence_number asc')

        return invoices

    # TODO: Calcular alicuotas dentro del mismo metodo
    def get_REGDIGITAL_CV_CBTE_VENTAS(self, alicuotas):
        res = []

        # Obtener lista de comprobantes.
        # TODO: revisar parametro skip_test_invoice
        invoices = self.env['account.move'].search([
            ('id', 'in', self.invoice_ids.ids)],
            # TODO: ordenar por punto de venta 
            order='sequence_number asc')

        for inv in invoices:
            # TODO: Revisar aca la lista de alicuotas
            cant_alicuotas = 0
            vat_taxes = alicuotas[inv]
            vat_exempt_base_amount = 0
            cant_alicuotas = len(vat_taxes)

            currency_rate = inv.l10n_ar_currency_rate
            currency_code = inv.currency_id.l10n_ar_afip_code
            doc_number = int(inv.name.split('-')[2])

            untaxed_amount = sum(inv.invoice_line_ids.filtered(untaxed_line).mapped('price_total'))
            exempt_amount = sum(inv.invoice_line_ids.filtered(exempt_line).mapped('price_total'))
            _logger.info("No Gravado / Exento: {} {}".format(untaxed_amount, exempt_amount))

            row = [
                # VENTAS Campo 1: Fecha de comprobante
                fields.Date.from_string(inv.invoice_date).strftime('%Y%m%d'),

                # VENTAS Campo 2: Tipo de Comprobante.
                "{:0>3d}".format(int(inv.l10n_latam_document_type_id.code)),

                # VENTAS Campo 3: Punto de Venta
                self.get_point_of_sale(inv),

                # VENTAS Campo 4: Número de Comprobante
                # TODO agregar estos casos de uso
                # Si se trata de un comprobante de varias hojas, se deberá
                # informar el número de documento de la primera hoja, teniendo
                # en cuenta lo normado en el  artículo 23, inciso a), punto
                # 6., de la Resolución General N° 1.415, sus modificatorias y
                # complementarias.
                # En el supuesto de registrar de manera agrupada por totales
                # diarios, se deberá consignar el primer número de comprobante
                # del rango a considerar.
                "{:0>20d}".format(inv.z_desde if inv.z_desde else doc_number),

                # VENTAS Campo 5: Número de Comprobante Hasta.
                # En el resto de los casos se consignará el
                # dato registrado en el campo 4
                "{:0>20d}".format(inv.z_hasta if inv.z_hasta else doc_number),

                # VENTAS Campo 6: Código de documento del comprador.
                self.get_partner_document_code(inv.commercial_partner_id),

                # VENTAS Campo 7: Número de Identificación del comprador
                self.get_partner_document_number(inv.commercial_partner_id),

                # VENTAS Campo 8: Apellido y Nombre del comprador.
                inv.commercial_partner_id.name.ljust(30, ' ')[:30],
                # inv.commercial_partner_id.name.encode(
                #     'ascii', 'replace').ljust(30, ' ')[:30],

                # VENTAS Campo 9: Importe Total de la Operación.
                #self.format_amount(inv.cc_amount_total, invoice=inv),
                self.format_amount(inv.amount_total, invoice=inv),

                # VENTAS Campo 10: Importe No Gravado
                self.format_amount(untaxed_amount, invoice=inv),
                    
                # VENTAS Campo 11: Percepción a no categorizados
                self.format_amount(
                    sum(inv.move_tax_ids.filtered(lambda r: (
                        r.tax_id.tax_group_id.tax_type == 'withholding' and
                        r.tax_id.tax_group_id.l10n_ar_tribute_afip_code == '01')
                    ).mapped('tax_amount')), invoice=inv),

                # VENTAS Campo 12: Importe exento
                self.format_amount(exempt_amount, invoice=inv),

                # VENTAS Campo 13: Importe de percepciones o pagos a cuenta de
                # impuestos nacionales
                self.format_amount(
                    sum(inv.move_tax_ids.filtered(lambda r: (
                        r.tax_id.tax_group_id.tax_type == 'withholding' and
                        r.tax_id.tax_group_id.l10n_ar_tribute_afip_code == '01')
                    ).mapped('tax_amount')), invoice=inv),

                # VENTAS Campo 14: Importe de percepciones de ingresos brutos
                self.format_amount(
                    sum(inv.move_tax_ids.filtered(lambda r: (
                        r.tax_id.tax_group_id.tax_type == 'withholding' and
                        r.tax_id.tax_group_id.l10n_ar_tribute_afip_code == '02')
                    ).mapped('tax_amount')), invoice=inv),

                # VENTAS Campo 15: Importe de percepciones de impuestos municipales
                self.format_amount(
                    sum(inv.move_tax_ids.filtered(lambda r: (
                        r.tax_id.tax_group_id.tax_type == 'withholding' and
                        r.tax_id.tax_group_id.l10n_ar_tribute_afip_code == '03')
                    ).mapped('tax_amount')), invoice=inv),

                # VENTAS Campo 16: Importe de impuestos internos
                self.format_amount(
                    sum(inv.move_tax_ids.filtered(
                        lambda r: r.tax_id.tax_group_id.l10n_ar_tribute_afip_code == '04'
                    ).mapped('tax_amount')), invoice=inv),

                # VENTAS Campo 17: Código de Moneda
                str(currency_code),

                # VENTAS Campo 18: Tipo de Cambio
                # nueva modalidad de currency_rate
                self.format_amount(currency_rate, padding=10, decimals=6),

                # VENTAS Campo 19: Cantidad de alícuotas de IVA
                str(cant_alicuotas),

                # VENTAS Campo 20: Código de operación.
                # WARNING. segun la plantilla es 0 si no es ninguna
                # TODO ver que no se informe un codigo si no correpsonde,
                # tal vez da error
                # TODO ADIVINAR E IMPLEMENTAR, VA A DAR ERROR
                #inv.fiscal_position_id.afip_code or '0',
                ' ',

                # VENTAS Campo 21: Otros Tributos
                self.format_amount(self._get_venta_otros_tributos(inv), invoice=inv),

                # VENTAS Campo 22: vencimiento comprobante
                # Segun aplicativo, solo es obligatorio para algunos casos especiales
                # Por el momento, se completa con ceros.
                '00000000'
                # (inv.l10n_latam_document_type_id.code in [
                #     '19', '20', '21', '16', '55', '81', '82', '83',
                #     '110', '111', '112', '113', '114', '115', '116',
                #     '117', '118', '119', '120', '201', '202', '203',
                #     '206', '207', '208', '211', '212', '213'] and
                #     '00000000' or
                #     fields.Date.from_string(
                #         inv.invoice_date_due or inv.invoice_date).strftime(
                #         '%Y%m%d')),
            ]
            res.append(''.join(row))
        self.REGDIGITAL_CV_CBTE = '\r\n'.join(res)

    def get_REGDIGITAL_CV_CBTE_COMPRAS(self, alicuotas):
        self.ensure_one()
        res = []

        # Obtener lista de comprobantes.
        # TODO: revisar parametro skip_test_invoice
        invoices = self.env['account.move'].search([
            ('id', 'in', self.invoice_ids.ids)],
            # TODO: ordenar por punto de venta
            order='commercial_partner_name asc,sequence_number asc')

        # Validacion de CUIT para compras
        partners = invoices.mapped('commercial_partner_id').filtered(
            lambda r: r.l10n_latam_identification_type_id.l10n_ar_afip_code in (
                False, 99) or not r.vat)
        if partners:
            raise ValidationError(_(
                "On purchase digital, partner document type is mandatory "
                "and it must be different from 99. "
                "Partners: \r\n\r\n"
                "%s") % '\r\n'.join(
                    ['[%i] %s' % (p.id, p.display_name)
                        for p in partners]))

        for inv in invoices:
            # si no existe la factura en alicuotas es porque no tienen ninguna
            #cant_alicuotas = len(alicuotas.get(inv.))
            # TODO: Revisar aca la lista de alicuotas
            cant_alicuotas = 0
            vat_taxes = alicuotas[inv]
            vat_exempt_base_amount = 0
            for invl in inv.invoice_line_ids:
                for tax in invl.tax_ids:
                    # if tax.tax_group_id.tax_type == 'vat':
                    #     if tax.id not in vat_taxes and tax.amount != 0 :
                    #         vat_taxes.append(tax.id)
                    if self.type == 'purchase':
                        if tax.amount == 0:
                            vat_exempt_base_amount += invl.price_subtotal

            cant_alicuotas = len(vat_taxes)

            currency_rate = inv.l10n_ar_currency_rate
            currency_code = inv.currency_id.l10n_ar_afip_code
            doc_number = int(inv.name.split('-')[2])

            untaxed_amount = sum(inv.invoice_line_ids.filtered(untaxed_line).mapped('price_total'))
            exempt_amount = sum(inv.invoice_line_ids.filtered(exempt_line).mapped('price_total'))
            _logger.info("No Gravado / Exento: {} {}".format(untaxed_amount, exempt_amount))

            row = [
                # COMPRAS Campo 1: Fecha de comprobante
                fields.Date.from_string(inv.invoice_date).strftime('%Y%m%d'),

                # COMPRAS Campo 2: Tipo de Comprobante.
                "{:0>3d}".format(int(inv.l10n_latam_document_type_id.code)),

                # COMPRAS Campo 3: Punto de Venta
                self.get_point_of_sale(inv),

                # COMPRAS Campo 4: Número de Comprobante
                # TODO agregar estos casos de uso
                # Si se trata de un comprobante de varias hojas, se deberá
                # informar el número de documento de la primera hoja, teniendo
                # en cuenta lo normado en el  artículo 23, inciso a), punto
                # 6., de la Resolución General N° 1.415, sus modificatorias y
                # complementarias.
                # En el supuesto de registrar de manera agrupada por totales
                # diarios, se deberá consignar el primer número de comprobante
                # del rango a considerar.
                "{:0>20d}".format(doc_number),

                # COMPRAS Campo 5: Despacho de importación
                # TODO
                # if inv.l10n_latam_document_type_id.code == '66':
                #     row.append(
                #         (inv.l10n_latam_document_number or inv.number or '').rjust(
                #             16, '0'))
                # else:
                #     row.append(''.rjust(16, ' '))
                ''.rjust(16, ' '),

                # COMPRAS Campo 6: Código de documento del comprador.
                self.get_partner_document_code(inv.commercial_partner_id),

                # COMPRAS Campo 7: Número de Identificación del comprador
                self.get_partner_document_number(inv.commercial_partner_id),

                # COMPRAS Campo 8: Apellido y Nombre del comprador.
                inv.commercial_partner_id.name.ljust(30, ' ')[:30],
                # inv.commercial_partner_id.name.encode(
                #     'ascii', 'replace').ljust(30, ' ')[:30],

                # COMPRAS Campo 9: Importe Total de la Operación.
                self.format_amount(inv.amount_total, invoice=inv),

                #if inv.id == 200:
                #    raise ValidationError('estamos aca %s'%(inv.l10n_latam_tax_ids[1].tax_ids))a
                # TODO
                # amount_percepciones_iva = 0
                # amount_percepciones_iibb = 0

                # COMPRAS Campo 10: Importe No Gravado
                self.format_amount(untaxed_amount, invoice=inv),
                
                # COMPRAS Campo 11: Importe Exento
                self.format_amount(exempt_amount, invoice=inv),

                # COMPRAS Campo 12: Importe de percepciones/pagos a cuenta de IVA
                self.format_amount(self._get_compra_iva(inv), invoice=inv),
                
                # COMPRAS Campo 13: Importe de percepciones/pagos a cuenta de
                # impuestos nacionales
                self.format_amount(
                    sum(inv.move_tax_ids.filtered(lambda r: (
                        r.tax_id.tax_group_id.tax_type == 'withholding' and
                        r.tax_id.tax_group_id.l10n_ar_tribute_afip_code == '01')
                    ).mapped('tax_amount')), invoice=inv),

                # COMPRAS Campo 14: Importe de percepciones de ingresos brutos
                self.format_amount(self._get_compra_iibb(inv), invoice=inv),

                # COMPRAS Campo 15: Importe de percepciones de impuestos municipales
                # TODO:
                # self.format_amount(
                #     sum(inv.move_tax_ids.filtered(lambda r: (
                #         r.tax_id.tax_group_id.tax_type == 'withholding' and
                #         r.tax_id.tax_group_id.l10n_ar_tribute_afip_code == '03')
                #     ).mapped('tax_amount')), invoice=inv),
                self.format_amount(0, invoice=inv),

                # COMPRAS Campo 16: Importe de impuestos internos
                self.format_amount(
                    sum(inv.move_tax_ids.filtered(
                        lambda r: r.tax_id.tax_group_id.l10n_ar_tribute_afip_code == '04'
                    ).mapped('tax_amount')), invoice=inv),

                # COMPRAS Campo 17: Código de Moneda
                str(currency_code),

                # COMPRAS Campo 18: Tipo de Cambio
                # nueva modalidad de currency_rate
                self.format_amount(currency_rate, padding=10, decimals=6),

                # COMPRAS Campo 19: Cantidad de alícuotas de IVA
                str(cant_alicuotas),

                # COMPRAS Campo 20: Código de operación.
                # - E: operaciones exentas
                # - N: operaciones no gravadas
                # - <blanco>: operaciones que tienen al menos una parte gravada
                self._get_compra_codigo_operacion(
                    self.format_amount(inv.amount_total, invoice=inv),
                    self.format_amount(untaxed_amount, invoice=inv),
                    self.format_amount(exempt_amount, invoice=inv)),

                # COMPRAS Campo 21: Crédito Fiscal Computable
                # if self.prorate_tax_credit:
                #     if self.prorate_type == 'global':
                #         row.append(self.format_amount(0, invoice=inv))
                #     else:
                #         # row.append(self.format_amount(0))
                #         # por ahora no implementado pero seria lo mismo que
                #         # sacar si prorrateo y que el cliente entre en el digital
                #         # en cada comprobante y complete cuando es en
                #         # credito fiscal computable
                #         raise ValidationError(_(
                #             'Para utilizar el prorrateo por comprobante:\n'
                #             '1) Exporte los archivos sin la opción "Proratear '
                #             'Crédito de Impuestos"\n2) Importe los mismos '
                #             'en el aplicativo\n3) En el aplicativo de afip, '
                #             'comprobante por comprobante, indique el valor '
                #             'correspondiente en el campo "Crédito Fiscal '
                #             'Computable"'))
                # else:
                #     vat_taxes = self.env['account.move.line']
                #     imp_neto = 0
                #     imp_liquidado = 0
                #     for mvl_tax in inv.l10n_latam_tax_ids:
                #         #raise ValidationError('estamos aca %s %s %s'%(inv,mvl_tax.tax_group_id.l10n_ar_vat_afip_code + 'X',mvl_tax.tax_group_id.tax_type))
                #         #if not mvl_tax.l10n_latam_tax_ids:
                #         #    continue
                #         tax_group_id = mvl_tax.tax_group_id
                #         #if tax_group_id.tax_type == 'vat' and (tax_group_id.l10n_ar_vat_afip_code == 3 or (tax_group_id.l10n_ar_vat_afip_code in [4, 5, 6, 8, 9])):
                #         if tax_group_id.tax_type == 'vat':
                #             imp_neto += mvl_tax.tax_base_amount
                #             imp_liquidado += mvl_tax.price_subtotal
                #     #if inv.id == 904:
                #     #    raise ValidationError('%s %s %s %s %s'%(inv.amount_total,inv.amount_untaxed,imp_neto,imp_liquidado,inv.id))
                #     row.append(self.format_amount(round(imp_liquidado,2), invoice=inv))
                #     # row.append(self.format_amount(
                #         #    inv.vat_amount, invoice=inv))
                self.format_amount(self._get_invoice_credito_fiscal(inv), invoice=inv),

                # COMPRAS Campo 22: Otros Tributos
                #self.format_amount(
                #    sum(inv.l10n_latam_tax_ids.filtered(lambda r: (
                #        r.l10n_latam_tax_ids[0].tax_group_id.tax_type \
                #        == 'others')).mapped(
                #        'cc_amount')), invoice=inv),
                self.format_amount(0),
                    #sum(inv.l10n_latam_tax_ids.filtered(lambda r: (
                    #    r.l10n_latam_tax_ids[0].tax_group_id.tax_type \
                    #    == 'others')).mapped(
                    #    'cc_amount')), invoice=inv),

                # TODO implementar estos 3
                # COMPRAS Campo 23: CUIT Emisor / Corredor
                # Se informará sólo si en el campo "Tipo de Comprobante" se
                # consigna '033', '058', '059', '060' ó '063'. Si para
                # éstos comprobantes no interviene un tercero en la
                # operación, se consignará la C.U.I.T. del informante. Para
                # el resto de los comprobantes se completará con ceros
                self.format_amount(0, padding=11, invoice=inv),

                # COMPRAS Campo 24: Denominación Emisor / Corredor
                ''.ljust(30, ' ')[:30],

                # COMPRAS Campo 25: IVA Comisión
                # Si el campo 23 es distinto de cero se consignará el
                # importe del I.V.A. de la comisión
                self.format_amount(0, invoice=inv)
            ]

            res.append(''.join(row))
        self.REGDIGITAL_CV_CBTE = '\r\n'.join(res)

    def _get_compra_codigo_operacion(self, total, untaxed, exempt):
        if total == 0:
            return ' '
        if total == untaxed:
            return 'N'
        if total == exempt:
            return 'E'
        return ' '

    def _get_compra_iva(self, inv):
        iibb = inv.line_ids.filtered(lambda r: (
            r.tax_group_id and r.tax_group_id.l10n_ar_tribute_afip_code == '06'))
        
        return sum(iibb.mapped('price_total'))

    def _get_venta_otros_tributos(self, inv):
        otros = inv.line_ids.filtered(lambda r: (
            r.tax_group_id and r.tax_group_id.l10n_ar_tribute_afip_code == '99'))
        
        return sum(otros.mapped('price_total'))

    def _get_compra_iibb(self, inv):
        # TODO Percepciones en moneda extranjera
        # if inv.currency_id.id == inv.company_id.currency_id.id:
        #     row += [
        #         self.format_amount(
        #             sum(inv.l10n_latam_tax_ids.filtered(lambda r: (
        #                 r.tax_line_id.tax_group_id.tax_type == 'withholdings' and
        #                 r.tax_line_id.tax_group_id.l10n_ar_tribute_afip_code \
        #                 == '07')
        #             ).mapped('debit')), invoice=inv)]
        _logger.info("MOVE_TAX_IDS: {} {}".format(inv, inv.line_ids))
        iibb = inv.line_ids.filtered(lambda r: (
            r.tax_group_id and r.tax_group_id.l10n_ar_tribute_afip_code == '07'))
        _logger.info("Filtered: {}".format(iibb))
        
        return sum(iibb.mapped('price_total'))

    # Genera una linea de Alicuota en IVA para compra, venta o importacion
    def get_tax_row(self, invoice, base, code, tax_amount, impo=False):
        self.ensure_one()
        inv = invoice
        if self.type == 'sale':
            doc_number = int(inv.name.split('-')[2])
            row = [
                # ALICUOTA VENTA Campo 1: Tipo de Comprobante
                "{:0>3d}".format(int(inv.l10n_latam_document_type_id.code)),

                # ALICUOTA VENTA Campo 2: Punto de Venta
                self.get_point_of_sale(inv),

                # ALICUOTA VENTA Campo 3: Número de Comprobante
                # Para los comprobantes Z, indicar el numero desde
                "{:0>20d}".format(inv.z_desde if inv.z_desde else doc_number),

                # ALICUOTA VENTA Campo 4: Importe Neto Gravado
                self.format_amount(base, invoice=inv),

                # ALICUOTA VENTA Campo 5: Alícuota de IVA.
                str(code).rjust(4, '0'),

                # ALICUOTA VENTA Campo 6: Impuesto Liquidado.
                self.format_amount(tax_amount, invoice=inv),
            ]
        elif impo:
            row = [
                # Campo 1: Despacho de importación.
                (inv.document_number or inv.number or '').rjust(16, '0'),

                # Campo 2: Importe Neto Gravado
                self.format_amount(base, invoice=inv),

                # Campo 3: Alícuota de IVA
                str(code).rjust(4, '0'),

                # Campo 4: Impuesto Liquidado.
                self.format_amount(tax_amount, invoice=inv),
            ]
        else:
            doc_number = int(inv.name.split('-')[2])
            #raise ValidationError('estamos aca %s'%(doc_number))
            row = [
                # Campo 1: Tipo de Comprobante
                #"{:0>3d}".format(int(inv.document_type_id.code)),
                str(inv.l10n_latam_document_type_id.code).zfill(3),

                # Campo 2: Punto de Venta
                #self.get_point_of_sale(inv),
                "{:0>5d}".format(int(inv.l10n_latam_document_number[:inv.l10n_latam_document_number.find('-')])),

                # Campo 3: Número de Comprobante
                #"{:0>19d}".format(int(inv.l10n_latam_document_number[inv.l10n_latam_document_number.find('-')+1:])),
                "{:0>20d}".format(doc_number),

                ## Campo 4: Código de documento del vendedor
                self.get_partner_document_code(
                    inv.commercial_partner_id),

                ## Campo 5: Número de identificación del vendedor
                self.get_partner_document_number(
                    inv.commercial_partner_id),

                # Campo 4: Importe Neto Gravado
                self.format_amount(base, invoice=inv),

                # Campo 5: Alícuota de IVA.
                str(code).rjust(4, '0'),

                # Campo 6: Impuesto Liquidado.
                self.format_amount(tax_amount, invoice=inv),
            ]
        return row

    def _get_invoice_credito_fiscal(self, inv):
        vat_taxes = inv.line_ids.filtered(
            # (0) No Corresponde (Monotributista, CF, Exento)
            # (1) No Gravado
            # (2) Exento 
            # (3) 0%
            # (4) 10.5%
            # (5) 21%
            # (6) 27%
            # (8) 5%
            # (9) 2.5%
            lambda l: l.tax_group_id and
            l.tax_group_id.l10n_ar_vat_afip_code in ['4', '5', '6', '8', '9']
        )

        return sum(vat_taxes.mapped('price_subtotal'))

    # A partir de un invoice, se determinan tipos de alicuota y se devuelve un array
    def get_invoice_alicuotas(self, inv, impo):
        lines = []

        # Retornar 1 alicuota en 0 para comprobantes con total 0
        if inv.amount_total == 0:
            lines.append(''.join(self.get_tax_row(inv, 0.0, 3, 0.0, impo=impo)))
            return lines

        # reportamos como linea de iva si:
        # * el impuesto es iva cero
        # * el impuesto es iva 21, 27 etc pero tiene impuesto liquidado,
        # si no tiene impuesto liquidado (is_zero), entonces se inventa
        # una linea

        # Obtener todas las lineas de IVA
        # - Filtrar las lineas de impuestos de tipo 'IVA' con codigo conocido
        vat_taxes = inv.line_ids.filtered(
            # (1) No Gravado
            # (2) Exento 
            # (3) 0%
            # (4) 10.5%
            # (5) 21%
            # (6) 27%
            # (8) 5%
            # (9) 2.5%
            lambda l: l.tax_group_id and 
            l.tax_group_id.l10n_ar_vat_afip_code in ['2','3', '4', '5', '6', '8', '9']
        )

        _logger.info("Cantidad de alicuotas gravadas: {}".format(len(vat_taxes)))
        _logger.info(vat_taxes)

        taxed_0 = inv.invoice_line_ids.filtered(taxed_0_line)
        if len(taxed_0):
            _logger.info("Alicuota al 0%: {} {} {}".format(inv, vat_taxes, inv.amount_total))
            lines.append(''.join(self.get_tax_row(inv, sum(taxed_0.mapped('price_total')), 3, 0.0, impo=impo)))            

        untaxed_exempt = inv.invoice_line_ids.filtered(untaxed_exempt_line)
        if len(untaxed_exempt):
            _logger.info("Alicuota No Gravada/Exenta: {} {}".format(inv, vat_taxes))
            lines.append(''.join(self.get_tax_row(inv, 0.0, 3, 0.0, impo=impo)))
        
        # Agrupar montos por tipo de alicuota
        for afip_code in vat_taxes.mapped('tax_group_id.l10n_ar_vat_afip_code'):
            taxes = vat_taxes.filtered(lambda x: x.tax_group_id.l10n_ar_vat_afip_code == afip_code)
            if inv.currency_id.id == inv.company_id.currency_id.id:
                # Factura en pesos
                imp_neto = sum(taxes.mapped('tax_base_amount'))
            else:
                # Factura en otra moneda
                imp_neto = 0
                other_lines = self.env['account.move.line'].search([('debit','>',0),('move_id','=',inv.id),('tax_ids','!=',False)])
                for other_line in other_lines:
                    imp_neto = imp_neto + other_line.amount_currency
            
            imp_liquidado = sum(taxes.mapped('price_subtotal'))
            lines.append(''.join(self.get_tax_row(
                inv, imp_neto, afip_code, imp_liquidado, impo=impo,
            )))
        
        return lines
    
    # impo indica es si es para (66) - Despacho de Importacion (True) o no (False)
    def get_REGDIGITAL_CV_ALICUOTAS_COMPRAS(self, impo=False):
        """
        Devolvemos un dict para calcular la cantidad de alicuotas cuando
        hacemos los comprobantes
        """
        self.ensure_one()
        res = {}
        # only vat taxes with codes 3, 4, 5, 6, 8, 9
        # segun: http://contadoresenred.com/regimen-de-informacion-de-
        # compras-y-ventas-rg-3685-como-cargar-la-informacion/
        # empezamos a contar los codigos 1 (no gravado) y 2 (exento)
        # si no hay alicuotas, sumamos una de esta con 0, 0, 0 en detalle
        # usamos mapped por si hay afip codes duplicados (ej. manual y
        # auto)
        if impo:
            # Si es importacion, obtener los comprobantes tipo 66 (Despacho de Importacion)
            invoices = self.get_digital_invoices().filtered(
                lambda r: r.l10n_latam_document_type_id.code == '66')
        else:
            # Si no es importacion, filtrar los comprobantes tipo 66 (Despacho de Importacion)
            invoices = self.get_digital_invoices().filtered(
                lambda r: r.l10n_latam_document_type_id.code != '66')

        _logger.info("INVOICES PARA ALICUOTAS {}".format(len(invoices)))
        for inv in invoices:
            # Por cada factura, obtener la lista de alicuotas
            res[inv] = self.get_invoice_alicuotas(inv, impo=impo)
        return res

    def get_REGDIGITAL_CV_ALICUOTAS_VENTAS(self):
        """
        Devolvemos un dict para calcular la cantidad de alicuotas cuando
        hacemos los comprobantes
        """
        self.ensure_one()
        res = {}
        
        # No es necesario filtrar despachos de importación (66) para ventas
        invoices = self.env['account.move'].search([
            ('id', 'in', self.invoice_ids.ids)
        ], order='sequence_number asc')

        for inv in invoices:
            # Por cada factura, obtener la lista de alicuotas
            res[inv] = self.get_invoice_alicuotas(inv, impo=False)
        return res