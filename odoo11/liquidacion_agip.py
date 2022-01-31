from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

import logging
import base64
import unicodedata
from datetime import datetime

_logger = logging.getLogger(__name__)

def format_amount(amount, padding=15, decimals=2, sep=""):
    if amount < 0:
        template = "-{:0>%dd}" % (padding - 1 - len(sep))
    else:
        template = "{:0>%dd}" % (padding - len(sep))
    res = template.format(
        int(round(abs(amount) * 10**decimals, decimals)))
    if sep:
        res = "{0}{1}{2}".format(res[:-decimals], sep, res[-decimals:])
    return res

# Liquidacion Mensual de AGIP
class IngresosBrutosAgipWizard(models.Model):
    _name = "l10n_ar.agente.agip.wizard"
    _inherit = [ 'report.pyme_accounting.base' ]
    _description = 'Reporte de Agente Ingresos Brutos AGIP'

    AGIP_CBTES = fields.Text('AGIP Comprobantes', readonly=True)
    agip_cbtes_file = fields.Binary(string="AGIP Comprobantes Archivo", readonly=True)
    agip_cbtes_filename = fields.Char(string="AGIP Comprobantes Nombre de Archivo", readonly=True)
    agip_cbtes_csv_file = fields.Binary(string="AGIP Comprobantes CSV Archivo", readonly=True)
    agip_cbtes_csv_filename = fields.Char(string="AGIP Comprobantes CSV Nombre de Archivo", readonly=True)

    AGIP_NC = fields.Text('AGIP Notas de Credito', readonly=True)
    agip_nc_file = fields.Binary(string="AGIP Notas de Credito Archivo", readonly=True)
    agip_nc_filename = fields.Char(string="AGIP Notas de Credito Nombre de Archivo", readonly=True)
    agip_nc_csv_file = fields.Binary(string="AGIP Notas de Credito Archivo", readonly=True)
    agip_nc_csv_filename = fields.Char(string="AGIP Notas de Credito Nombre de Archivo", readonly=True)

    invoice_ids = fields.Many2many('account.move', string="Facturas", compute="generate")
    payment_ids = fields.Many2many('account.move', string="Pagos", compute="generate")
    perc_line_ids = fields.Many2many('account.move.line', string="Percepciones", compute="generate")
    ret_line_ids = fields.Many2many('account.move.line', string="Retenciones", compute="generate")

    def _format_tipo_cbte(self, internal_type):
        # TODO: confirmar esto

        # invoice, debit_note, credit_note, ticket, 
        # receipt_invoice, customer_payment, supplier_payment, in_document
        if internal_type == 'invoice':
            return '01'
        elif internal_type == 'debit_note':
            return '02'
        
        # TODO: descomentar esto
        # elif internal_type == 'supplier_payment':
        #     return '03'

        # raise ValidationError('Tipo de documento interno invalido: {}'.format(internal_type))
            
        # Orden de pago
        return '03'

    # depends('l10n_latam_identification_type_id')
    def _format_tipo_documento(self, partner_id):
        doc_type_mapping = {'CDI': '1', 'CUIL': '2', 'CUIT': '3' }
        doc_type_name = partner_id.main_id_category_id.code
        if doc_type_name not in ['CUIT', 'CUIL', 'CDI']:
                raise ValidationError(_(
                    'EL el partner "%s" (id %s), el tipo de identificación '
                    'debe ser una de siguientes: CUIT, CUIL, CDI.' % (partner_id.id, partner_id.name)))
        return doc_type_mapping[doc_type_name]

    def _format_letra_cbte(self, move):
        return move.document_type_id.document_letter_id.name

    def _format_numero_cbte(self, move):
        s = move.document_number.split("-")
        if len(s) != 2:
            # raise ValidationError('Numero de comprobante invalido: {}'.format(move.document_number))
            return '0000000000000000'

        return '{}{}'.format(s[0][-4:].zfill(4), s[1][-12:].zfill(12))

    # depends('gross_income_type')
    def _format_situacion_iibb(self, partner_id):
        # if not partner_id.gross_income_type:
        #     raise ValidationError(_(
        #         'Debe establecer el tipo de inscripción de IIBB del partner '
        #         '"%s" (id: %s)') % (partner_id.name, partner_id.id))

        # # ahora se reportaria para cualquier inscripto el numero de cuit
        # # gross_income_mapping = { 'multilateral': '2', 'exempt': '4', 'local': '5' }
        # gross_income_mapping = { 'multilateral': '2', 'no_liquida': '4', 'local': '5' }
        # return gross_income_mapping[partner_id.gross_income_type]
        
        # Para evitar saber la situacion de cada cliente,
        # se puede simplemente declarar local y poner el numero de CUIT
        return '5'

    # depends('gross_income_type', 'gross_income_number')
    def _format_numero_iibb(self, partner_id):
        # if partner_id.gross_income_type == 'no_liquida':
        #     return '00000000000' 
    
        # return partner_id.gross_income_number
        return partner_id.main_id_number

    # depends('afip_responsability_type_id.code')
    def _format_situacion_iva(self, partner_id):
        res_iva = partner_id.afip_responsability_type_id
        iva_code = res_iva.code
        
        # Resp. Inscripto / Resp. Inscripto Factura M
        if iva_code in ['1', '1FM']:
            return '1'
        # Exento
        if iva_code == '4':
            return '3'
        # Monotributo
        if iva_code == '6':
            return '4'
        
        raise ValidationError(_(
            'La responsabilidad frente a IVA "%s" no está soportada '
            'para ret/perc AGIP') % res_iva.name)

    def _get_alicuota(self, partner_id, date):
        tag_id = self.env['account.account.tag'].search([
            ('name', '=', 'Jur: 901 - Capital Federal')
        ])
        # Primero chequear que esten seteados from_date y to_date. 
        # Luego validar que el rango y la jurisdiccion coincidan 
        alicuota = partner_id.arba_alicuot_ids.filtered(
            lambda a: a.from_date and a.to_date and a.from_date <= date and a.to_date >= date and a.tag_id == tag_id)
        if len(alicuota) != 1:
            err = 'Alicuota AGIP no encontrada para partner {} - fecha {}'.format(partner_id, date)
            _logger.error(err)
            raise ValidationError(err)

        return alicuota

    def _format_nc_numero_cbte(self, move):
        s = move.document_number.split("-")
        if len(s) != 2:
            # raise ValidationError('Numero de comprobante invalido: {}'.format(move.document_number))
            return '000000000000'

        return '{}{}'.format(s[0][-4:].zfill(4), s[1][-8:].zfill(8))

    def generate(self):
        if not self.date_from or not self.date_to:
            return

        records = []
        records_nc = []
        records_csv = []
        records_nc_csv = []
        
        # Percepciones
        f, nc, f_csv, nc_csv = self.generate_percepciones()
        records.extend(f)
        records_nc.extend(nc)
        records_csv.extend(f_csv)
        records_nc_csv.extend(nc_csv)

        # Retenciones
        f, f_csv = self.generate_retenciones()
        records.extend(f)
        records_csv.extend(f_csv)

        # Ordenar por fecha de comprobante, tipo, numero
        records.sort(key=lambda l: '{}-{}-{}'.format(
            datetime.strptime(l[4:14], '%d/%m/%Y').strftime('%Y-%m-%d'), 
            l[0],
            l[17:33]))
        records_nc.sort(key=lambda l: '{}-{}-{}'.format(
            datetime.strptime(l[13:23], '%d/%m/%Y').strftime('%Y-%m-%d'), 
            l[0],
            l[1:13]))

        period = fields.Date.from_string(self.date_to).strftime('%Y-%m-%d')

        # Generar archivos CSV
        AGIP_CBTES_CSV = '\r\n'.join(records_csv)
        self.agip_cbtes_csv_filename = 'AGIP-{}-cbtes.csv'.format(period)
        self.agip_cbtes_csv_file = base64.encodestring(
            # Primero se debe normalizar para evitar caracteres especiales
            # que alteran la longitud de la linea
            unicodedata.normalize('NFD', AGIP_CBTES_CSV).encode('ISO-8859-1', 'ignore'))

        AGIP_NC_CSV = '\r\n'.join(records_nc_csv)
        self.agip_nc_csv_filename = 'AGIP-{}-nc.csv'.format(period)
        self.agip_nc_csv_file = base64.encodestring(
            # Primero se debe normalizar para evitar caracteres especiales
            # que alteran la longitud de la linea
            unicodedata.normalize('NFD', AGIP_NC_CSV).encode('ISO-8859-1', 'ignore'))

        # La ultima linea debe estar vacia
        records.append('')
        records_nc.append('')

        # Generar archivos
        self.AGIP_CBTES = '\r\n'.join(records)
        self.agip_cbtes_filename = 'AGIP-{}-cbtes.txt'.format(period)
        self.agip_cbtes_file = base64.encodestring(
            # Primero se debe normalizar para evitar caracteres especiales
            # que alteran la longitud de la linea
            unicodedata.normalize('NFD', self.AGIP_CBTES).encode('ISO-8859-1', 'ignore'))

        self.AGIP_NC = '\r\n'.join(records_nc)
        self.agip_nc_filename = 'AGIP-{}-nc.txt'.format(period)
        self.agip_nc_file = base64.encodestring(
            # Primero se debe normalizar para evitar caracteres especiales
            # que alteran la longitud de la linea
            unicodedata.normalize('NFD', self.AGIP_NC).encode('ISO-8859-1', 'ignore'))

    # Dependencies:
    # - invoice_id.amount_total_company_signed
    # - invoice_id.amount_untaxed_signed
    def generate_percepciones(self):
        records = []
        records_nc = []
        records_csv = []
        records_nc_csv = []

        # TODO: cambiar por referencia a percepcion AGIP aplicada
        iibb_account = self.env['account.account'].search([
            # ('code', '=', '231000'),
            ('code', '=', '2.1.03.01.012')
        ])

        if not iibb_account:
            raise ValidationError('Cuenta de percepcion AGIP aplicada no encontrada')
        
        # IVA Debito Fiscal
        # TODO: sacar de una referencia o permitir cargar por el usuario
        tax_account = self.env['account.account'].search([
            # ('code', '=', '231000')
            ('code', '=', '2.1.03.01.001')
        ])

        if not tax_account:
            raise ValidationError('Cuenta de IVA Debito no encontrada')

        self.perc_line_ids = self.env['account.move.line'].search([
            ('account_id', '=', iibb_account.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('move_id.state', '=', 'posted'),
            ('move_id.document_type_id', '!=', False),
            # TODO: order_by date asc, document_number asc
        ], order='date asc')
        self.invoice_ids = self.perc_line_ids.mapped('move_id')

        for line in self.perc_line_ids:
            try:
                move = line.move_id
                internal_type = move.document_type_id.internal_type
                partner_id = move.partner_id

                # Revisar bien cuando las facturas sean en USD, que los campos sean en Pesos
                monto_total = abs(line.invoice_id.amount_total_company_signed) # 53074,79
                tax_lines = move.line_ids.filtered(lambda l: l.account_id == tax_account)
                monto_iva = abs(sum(tax_lines.mapped('balance')))
                monto_perc = abs(line.balance) # 1053,07

                if internal_type == 'credit_note':
                    origin_move = self.env['account.move'].search([
                        ('document_number', '=', line.invoice_id.origin)
                    ])
                    if len(origin_move) != 1:
                        raise ValidationError('El numero de documento para {} debe ser unico'.format(move.origin))
                    
                    monto_alicuota = self._get_alicuota(partner_id, origin_move.date).alicuota_percepcion
                    # Se calcula asi el monto base, porque en AGIP debe coincidir exactamente
                    # el calculo de alicuota, con precision de decimales
                    monto_base = round(monto_perc * 100.0 / monto_alicuota, 2)
                    # Al calcular el monto base con una alicuota muy chica, 
                    # el monto de otros puede quedar negativo
                    monto_otros = max(monto_total - monto_base - monto_iva, monto_alicuota) # 2106.14
                    monto_total = monto_base + monto_iva + monto_otros

                    record = [
                        # Campo 1 - Tipo de Operacion [1]. Percepcion (2)
                        '2',
                        # Campo 2 - Nro Nota de Credito [12]
                        # 4 punto de venta - 8 numero comprobante
                        self._format_nc_numero_cbte(move),
                        # Campo 3 - Fecha de Nota de Credito [10]
                        fields.Date.from_string(move.date).strftime('%d/%m/%Y'),
                        # Campo 4 - Monto Base de Nota de Credito [16]
                        format_amount(monto_base, 16, 2, ','),
                        # Campo 5 - Numero de certificado [16]
                        ''.rjust(16, ' '),
                        # Campo 6 - Tipo de Comprobante Origen [2]
                        self._format_tipo_cbte(origin_move.document_type_id.internal_type),
                        # Campo 7 - Letra del Comprobante Origen [1]
                        self._format_letra_cbte(origin_move),
                        # Campo 8 - Numero de Comprobante Origen [16]
                        self._format_numero_cbte(origin_move),
                        # Campo 9 - Numero de Documento del Retenido [11]
                        partner_id.main_id_number,
                        # Campo 10 - Codigo de Norma [3]
                        '029',
                        # Campo 11 - Fecha de Retencion/Percepcion original [10]
                        fields.Date.from_string(origin_move.date).strftime('%d/%m/%Y'),
                        # Campo 12 - Monto a deducir [16]
                        format_amount(monto_perc, 16, 2, ','),
                        # Campo 13 - Alicuota [5]
                        format_amount(monto_alicuota, 5, 2, ","),
                    ]

                    records_nc.append(''.join(record))
                    records_nc_csv.append(','.join(map(lambda r: '"{}"'.format(r), record)))
                else:
                    monto_alicuota = self._get_alicuota(partner_id, move.date).alicuota_percepcion
                    # Se calcula asi el monto base, porque en AGIP debe coincidir exactamente
                    # el calculo de alicuota, con precision de decimales
                    monto_base = round(monto_perc * 100.0 / monto_alicuota, 2)
                    # Al calcular el monto base con una alicuota muy chica, 
                    # el monto de otros puede quedar negativo
                    monto_otros = max(monto_total - monto_base - monto_iva, monto_alicuota) # 2106.14
                    monto_total = monto_base + monto_iva + monto_otros

                    record = [
                        # Campo 1 - Percepcion (2)
                        '2',
                        # Campo 2 - Codigo de Norma. 
                        # Regimen General es el unico soportado al momento
                        '029',
                        # Campo 3- Fecha Retencion/Percepcion
                        fields.Date.from_string(move.date).strftime('%d/%m/%Y'),
                        # Campo 4- Tipo de Comprobante
                        self._format_tipo_cbte(internal_type),
                        # Campo 5 - Letra del Comprobante
                        self._format_letra_cbte(move),
                        # Campo 6 - Pto. de Venta + Comprobante (0003000000066478)
                        # 4 punto de venta, 12 numero de comprobante
                        self._format_numero_cbte(move),
                        # Campo 7 - Fecha Comprobante
                        fields.Date.from_string(move.date).strftime('%d/%m/%Y'),
                        # Campo 8 - Monto Total (amount_total) (53074.79 => 0000000053074,79)
                        format_amount(monto_total, 16, 2, ','),
                        # Campo 9 - Numero de certificado. No aplica para percepcion
                        ''.rjust(16, ' '),
                        # Campo 10 - Tipo de documento cliente (partner_id.afip_type)
                        # 1 CDI, 2 CUIL, 3 CUIT
                        self._format_tipo_documento(partner_id),
                        # Campo 11 - Numero de Documento (partner_id.main_id_number)
                        partner_id.main_id_number,
                        # Campo 12 - Situacion IIBB
                        # 1: Local 2: Convenio Multilateral
                        # 4: No inscripto 5: Reg.Simplificado
                        self._format_situacion_iibb(partner_id),
                        # Campo 13 - Numero de inscripcion IIBB
                        self._format_numero_iibb(partner_id),
                        # Campo 14 - Situacion frente al IVA
                        # 1 Resp. Inscripto - 3 Exento - 4 Monotributo
                        self._format_situacion_iva(partner_id),
                        # Campo 15 - Razon Social
                        # TODO: tal vez reemplazar guiones bajo
                        '{:30.30}'.format(partner_id.name),
                        # Campo 16 - Importe Otros Conceptos
                        format_amount(monto_otros, 16, 2, ','),
                        # Campo 17 - Importe IVA
                        format_amount(monto_iva, 16, 2, ','),
                        # Campo 18 - Base Imponible (Total - IVA - Otros)  
                        format_amount(monto_base, 16, 2, ','),
                        # Campo 19 - Alicuota (sacado de padron AGIP, por CUIT+fecha)
                        format_amount(monto_alicuota, 5, 2, ","),
                        # Campo 20 - Impuesto aplicado (Base * Alicuota / 100)  
                        format_amount(monto_perc, 16, 2, ','),
                        # Campo 21 - Impuesto aplicado  
                        format_amount(monto_perc, 16, 2, ','),
                    ]

                    records.append(''.join(record))
                    records_csv.append(','.join(map(lambda r: '"{}"'.format(r), record)))
            except:
                _logger.error("Error procesando percepcion. Asiento {}".format(line.move_id.name))

        return records, records_nc, records_csv, records_nc_csv

    def generate_retenciones(self):
        records = []
        records_csv = []

        # TODO: cambiar por referencia a retencion AGIP aplicada
        # usar grupo de impuestos o dejar que lo configure el usuario
        iibb_account = self.env['account.account'].search([
            # ('code', '=', '231000'),
            ('code', '=', '2.1.03.01.011')
        ])

        if not iibb_account:
            raise ValidationError('Cuenta de retencion AGIP aplicada no encontrada')

        self.ret_line_ids = self.env['account.move.line'].search([
            ('account_id', '=', iibb_account.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('move_id.state', '=', 'posted'),
            ('move_id.document_type_id', '!=', False),
            # TODO: order_by date, document_number
        ])
        self.payment_ids = self.ret_line_ids.mapped('move_id')

        for line in self.ret_line_ids:
            try:
                move = line.move_id
                internal_type = move.document_type_id.internal_type
                partner_id = move.partner_id

                # Base Imponible (restando el minimo no imponible)
                # monto_base = line.payment_id.withholding_base_amount
                monto_ret = abs(line.balance)
                monto_alicuota = self._get_alicuota(partner_id, move.date).alicuota_retencion
                monto_base = round(monto_ret * 100.0 / monto_alicuota, 2)

                # TODO: chequear que no aparezca una devolucion de pago

                record = [
                    # Campo 1 - Retencion (1)
                    '1',
                    # Campo 2 - Codigo de Norma. 
                    # Regimen General es el unico soportado al momento
                    '029',
                    # Campo 3- Fecha Retencion/Percepcion
                    fields.Date.from_string(move.date).strftime('%d/%m/%Y'),
                    # Campo 4- Tipo de Comprobante
                    self._format_tipo_cbte(internal_type),
                    # Campo 5 - Letra del Comprobante
                    ' ',
                    # Campo 6 - Pto. de Venta + Comprobante (0003-000000066478)
                    # 4 punto de venta, 12 numero de comprobante
                    self._format_numero_cbte(move),
                    # Campo 7 - Fecha Comprobante
                    fields.Date.from_string(move.date).strftime('%d/%m/%Y'),
                    # Campo 8 - Monto Base (53074.79 => 0000000053074,79)
                    format_amount(monto_base, 16, 2, ','),
                    # Campo 9 - Numero de certificado.
                    line.name.rjust(16, ' '),
                    # line.payment_id.withholding_number.rjust(16, ' '),
                    # Campo 10 - Tipo de documento cliente (partner_id.afip_type)
                    # 1 CDI, 2 CUIL, 3 CUIT
                    self._format_tipo_documento(partner_id),
                    # Campo 11 - Numero de Documento (partner_id.main_id_number)
                    partner_id.main_id_number,
                    # Campo 12 - Situacion IIBB
                    # 1: Local 2: Convenio Multilateral
                    # 4: No inscripto 5: Reg.Simplificado
                    self._format_situacion_iibb(partner_id),
                    # Campo 13 - Numero de inscripcion IIBB
                    self._format_numero_iibb(partner_id),
                    # Campo 14 - Situacion frente al IVA
                    self._format_situacion_iva(partner_id),
                    # Campo 15 - Razon Social
                    # TODO: tal vez reemplazar guiones bajo
                    '{:30.30}'.format(partner_id.name),
                    # Campo 16 - Importe Otros Conceptos
                    format_amount(0, 16, 2, ','),
                    # Campo 17 - Importe IVA
                    format_amount(0, 16, 2, ','),
                    # Campo 18 - Base Imponible (Total - IVA - Otros)  
                    format_amount(monto_base, 16, 2, ','),
                    # Campo 19 - Alicuota (sacado de padron AGIP, por CUIT+fecha)
                    format_amount(monto_alicuota, 5, 2, ","),
                    # Campo 20 - Impuesto aplicado (Base * Alicuota / 100)  
                    format_amount(monto_ret, 16, 2, ','),
                    # Campo 21 - Impuesto aplicado  
                    format_amount(monto_ret, 16, 2, ','),
                ]

                records.append(''.join(record))
                records_csv.append(','.join(map(lambda r: '"{}"'.format(r), record)))
            except:
                _logger.error("Error procesando retencion. Asiento {}".format(line.move_id.name))

        return records, records_csv

# Siempre es simplificado? De donde sacan los valores esos?
# Siendo multilateral, se presenta SIFERE + DDDJJ en cada provincia?
# account.move vs account.invoice ???
# Revisar que no afecte la moneda extranjera. Como se calcula perc/ret?
# NOTA: las notas de credito se cargan luego de los comprobantes. Los montos
#    deben coincidir exactamente con los originales del comprobante

# Campos:
# - account.move:
#   - l10n_ar_document_type_id.internal_type
#     [OK] document_type_id.internal_type
#   - l10n_latam_document_type_id.l10n_ar_letter
#     [OK] document_type_id (account.document.type) => document_letter_id (account.document.letter) => name
#     modulo account_document (ADHOC)
#   - [OK] partner_id: base
# - payment:
#   - withholding_number
# - res.partner:
#   - [OK] vat: CUIT
#   - l10n_ar_gross_income_type: Tipo IIBB
#     [OK] gross_income_type (modulo l10n_ar_account)
#   - [OK] gross_income_number: Numero IIBB (modulo l10n_ar_account)
#   - l10n_latam_identification_type_id: Tipo Documento
#     main_id_category_id (res.partner.id_category) => code (modulo l10n_ar_partner)
#   - l10n_ar_afip_responsibility_type_id: Tipo Responsabilidad AFIP
#     [OK] afip_responsability_type_id (afip.responsability.type) => code (modulo l10n_ar_account)

# Modulos:
# - l10n_ar_base (11.0.1.0.0)
# - l10n_ar_partner - https://github.com/ingadhoc/odoo-argentina/tree/11.0/l10n_ar_partner
# - l10n_ar_account
# - account_payment_group
# - account_withholding
# - account_document - https://apps.odoo.com/apps/modules/11.0/account_document/

# Otros:
# - account_credit_control (11.0.1.0.1)
# - account_financial_report (11.0.2.3.1)
# - account_check (11.0.1.11.0)
# - account_accountant_cbc (11.0.1.0)
# - account_invoicing (11.0.1.0)
# - mis_builder (11.0.3.6.3)
# - account_fiscal_year 


# README
# - En account_document.py _get_localizations retorna ['argentina']
# - En account.document.type se borra columna validator_numero_factura y localization

# 1.1.01.05.018 - Percepción IIBB CABA sufrida
# 1.1.01.05.019 - Retención IIBB CABA sufrida
# 2.1.03.01.011 - Retención IIBB CABA aplicada
# 2.1.03.01.012 - Percepción IIBB CABA aplicada

# TODO
# En percepciones:
# - Las NC que no sean por el monto completo o de un periodo anterior, no agregarlos al TXT

# - Separar NC en la vista