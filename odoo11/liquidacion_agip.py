from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

import logging
import base64

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

class IngresosBrutosAgipWizard(models.Model):
    _name = "l10n_ar.agente.agip.wizard"
    _inherit = [ 'report.pyme_accounting.base' ]
    _description = 'Reporte de Agente Ingresos Brutos AGIP'

    AGIP_CBTES = fields.Text('AGIP Comprobantes', readonly=True)
    agip_cbtes_file = fields.Binary(string="AGIP Comprobantes Archivo", readonly=True)
    agip_cbtes_filename = fields.Char(string="AGIP Comprobantes Nombre de Archivo", readonly=True)
    invoice_ids = fields.Many2many('account.move', string="Facturas", compute="generate")

    def _format_tipo_cbte(self, internal_type):
        if internal_type == 'invoice':
            return '01'
        elif internal_type == 'debit_note':
            return '02'
        
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

    # depends('gross_income_type')
    def _format_situacion_iibb(self, partner_id):
        if not partner_id.gross_income_type:
            raise ValidationError(_(
                'Debe establecer el tipo de inscripción de IIBB del partner '
                '"%s" (id: %s)') % (partner_id.name, partner_id.id))

        # ahora se reportaria para cualquier inscripto el numero de cuit
        # gross_income_mapping = { 'multilateral': '2', 'exempt': '4', 'local': '5' }
        gross_income_mapping = { 'multilateral': '2', 'no_liquida': '4', 'local': '5' }
        return gross_income_mapping[partner_id.gross_income_type]

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
        self.env['account.account.tag'].search([
            ('name', '=', 'Jur: 901 - Capital Federal')
        ])
        partner_id.arba_alicuot_ids.filtered(
            lambda a: a.from_date, a.to_date, a.tag_id)

    def generate(self):
        records = []
        self.invoice_ids = self.env['account.move'].search([])

        for move in self.invoice_ids:
            # invoice, debit_note, ...
            internal_type = move.document_type_id.internal_type
            partner_id = move.partner_id
            
            payment = None
            percepcion = True

            monto_total = move.amount_total_signed             # 53074,79
            monto_base = move.amount_untaxed_signed            # 42122,85
            monto_iva = 0 # 8845.80  tax_line_ids.filtered(name = 'IVA Ventas 21%').amount_total
            monto_perc = 0 # 1053,07
            monto_otros = monto_total - monto_base - monto_iva # 2106.14

            record = [
                # Campo 1 - Percepcion (1) / Retencion (2)
                '1' if percepcion else '2',
                # Campo 2 - Codigo de Norma. 
                # Regimen General es el unico soportado al momento
                '029',
                # Campo 3- Fecha Retencion/Percepcion
                fields.Date.from_string(move.date).strftime('%d/%m/%Y'),
                # Campo 4- Tipo de Comprobante
                self._format_tipo_cbte(internal_type),
                # Campo 5 - Letra del Comprobante
                # TODO: Campo 6 - Pto. de Venta + Comprobante (0003-000000066478)
                move.document_type_id.document_letter_id.name if True else ' ',
                # 4 punto de venta, 12 numero de comprobante
                '0003000000066478',
                # Campo 7 - Fecha Comprobante
                fields.Date.from_string(move.date).strftime('%d/%m/%Y'),
                # TODO Campo 8 - Monto Total (amount_total) (53074.79 => 0000000053074,79)
                format_amount(monto_total, 16, 2, ','),
                # Campo 9 - Numero de certificado. No aplica
                ('' if percepcion else payment.withholding_number).rjust(16, ' '),
                # Campo 10 - Tipo de documento cliente (partner_id.afip_type)
                # 1 CDI, 2 CUIL, 3 CUIT
                self._format_tipo_documento(partner_id),
                # Campo 11 - Numero de Documento (partner_id.vat)
                partner_id.vat,
                # Campo 12 - Situacion IIBB
                # 1: Local 2: Convenio Multilateral
                # 4: No inscripto 5: Reg.Simplificado
                self._format_situacion_iibb(partner_id),
                # Campo 13 - Numero de inscripcion IIBB
                '00000000000' if partner_id.gross_income_type == 'no_liquida' else partner_id.gross_income_number,
                # Campo 14 - Situacion frente al IVA
                self._format_situacion_iva(partner_id),
                # Campo 15 - Razon Social
                '{:30.30}'.format(partner_id.name),
                # Campo 16 - Importe Otros Conceptos
                format_amount(monto_otros, 16, 2, ','),
                # Campo 17 - Importe IVA
                format_amount(monto_iva, 16, 2, ','),
                # Campo 18 - Base Imponible (Total - IVA - Otros)  
                format_amount(monto_base, 16, 2, ','),
                # Campo 19 - Alicuota (sacado de padron AGIP, por CUIT+fecha)
                '99,99',
                # Campo 20 - Impuesto aplicado (Base * Alicuota / 100)  
                format_amount(monto_perc, 16, 2, ','),
                # Campo 21 - Impuesto aplicado  
                format_amount(monto_perc, 16, 2, ','),
            ]

            _logger.info(record)
            records.append(''.join(record))

        # TODO
        period = '2021-11-0'

        # Generar archivo
        self.AGIP_CBTES = '\r\n'.join(records)
        self.agip_cbtes_filename = 'AGIP-{}-cbtes.txt'.format(period)
        self.agip_cbtes_file = base64.encodestring(
            self.AGIP_CBTES.encode('ISO-8859-1'))

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