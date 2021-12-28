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

class IngresosBrutosArbaWizard(models.Model):
    _name = "l10n_ar.agente.arba.wizard"
    _inherit = [ 'report.pyme_accounting.base' ]
    _description = 'Reporte de Agente Ingresos Brutos ARBA'

    ARBA_PERC = fields.Text('ARBA Percepciones', readonly=True)
    arba_perc_file = fields.Binary(string="ARBA Percepciones Archivo", readonly=True)
    arba_perc_filename = fields.Char(string="ARBA Percepciones Nombre de Archivo", readonly=True)
    
    ARBA_RET = fields.Text('ARBA Retenciones', readonly=True)
    arba_ret_file = fields.Binary(string="ARBA Retenciones Archivo", readonly=True)
    arba_ret_filename = fields.Char(string="ARBA Retenciones Nombre de Archivo", readonly=True)
    
    invoice_ids = fields.Many2many('account.move', string="Facturas", compute="generate")
    payment_ids = fields.Many2many('account.move', string="Pagos", compute="generate")
    perc_line_ids = fields.Many2many('account.move.line', string="Percepciones", compute="generate")
    ret_line_ids = fields.Many2many('account.move.line', string="Retenciones", compute="generate")

    # TODO: exclude_journal_ids = fields.Many2many('account.journal', string="Excluir Diarios Contables")
    # TODO: include_journal_ids = fields.Many2many('account.journal', string="Incluir Diarios Contables")

    def _format_cuit(self, partner):
        cuit = partner.vat
        return '{}-{}-{}'.format(cuit[0:2], cuit[2:10], cuit[10])

    def _format_date(self, date):
        return fields.Date.from_string(date).strftime('%d/%m/%Y')

    def _format_tipo_cbte(self, move):
        doc_type = move.document_type_id.doc_code_prefix
        tipo_cbte_map = {
            'FA-A': 'F', 'FA-B': 'F', 'FA-C': 'F', # FA-E, FA-I, FA-M
            'NC-A': 'C', 'NC-B': 'C', 'NC-C': 'C', # NC-E, NC-I
            'ND-A': 'D', 'ND-B': 'D', 'ND-C': 'D', # ND-E. Revisar ND-M (dice NC-C)
            'RE-A': 'R', 'RE-B': 'R', 'RE-C': 'R', # RE-M
            'FCE-A': 'E', 'FCE-B': 'E', 'FCE-C': 'E',
            'NCE-A': 'H', 'NCE-B': 'H', 'NCE-C': 'H', # Revisar NCE-C (dice NCE-D)
            'NDE-A': 'I', 'NDE-B': 'I', 'NDE-C': 'I',
            # TODO: notas de venta al contado
        }
        if doc_type.strip() in tipo_cbte_map:
            return tipo_cbte_map[doc_type.strip()]
        
        raise ValidationError('Tipo de Cbte Invalido: {}'.format(doc_type))

    def _format_letra_cbte(self, move):
        letter_name = move.document_type_id.document_letter_id.name
        
        if letter_name in ['A', 'B', 'C']:
            # 'A', 'B', 'C'
            return letter_name

        # <blanco>
        return ' '

    def _format_pto_venta(self, move):
        s = move.document_number.split("-")
        if len(s) != 2:
            # raise ValidationError('Numero de comprobante invalido: {}'.format(move.document_number))
            return '0000'
        return s[0][-4:].zfill(4)

    def _format_numero_cbte(self, move):
        s = move.document_number.split("-")
        if len(s) != 2:
            # raise ValidationError('Numero de comprobante invalido: {}'.format(move.document_number))
            return '00000000'
        return s[1][-8:].zfill(8)

    def generate(self):
        self.generate_percepciones()
        self.generate_retenciones()

    def generate_percepciones(self):
        records_perc = []
        
        # TODO: permitir configurar estas cuentas
        # tax_account = self.env['account.account'].search([
        #     ('code', '=', '231000')
        # ])

        # TODO: cambiar por referencia a percepcion ARBA aplicada
        iibb_account = self.env['account.account'].search([
            # ('code', '=', '231000'),
            ('code', '=', '2.1.03.01.024')
        ])

        # if not tax_account:
        #     raise ValidationError('Cuenta de IVA no encontrada')

        if not iibb_account:
            raise ValidationError('Cuenta de percepcion ARBA aplicada no encontrada')

        self.perc_line_ids = self.env['account.move.line'].search([
            ('account_id', '=', iibb_account.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('move_id.state', '=', 'posted'),
            # TODO: order_by document_number
        ])
        self.invoice_ids = self.perc_line_ids.mapped('move_id')

        for line in self.perc_line_ids:
            move = line.move_id
            partner_id = move.partner_id
            # tax_line = move.line_ids.filtered(lambda l: l.account_id == tax_account)

            # Percepcion
            record = [
                # CUIT [13] (30-71125458-3)
                self._format_cuit(partner_id),
                # Fecha [10] (03/11/2021)
                self._format_date(line.date),
                # Tipo Comprobante [1] 
                #   F - Factura
                #   C - Nota de Credito
                #   R - Recibo
                #   D - Nota Debito
                #   V - Nota de Venta
                #   E - Factura de Crédito Electrónica
                #   H - Nota de Crédito Electrónica
                #   I - Nota de Débito Electrónica
                self._format_tipo_cbte(move),
                # Letra Comprobante [1] (A, B, C, <blanco>)
                self._format_letra_cbte(move), 
                # Punto de Venta [4] (0003)
                self._format_pto_venta(move),
                # Numero de Comprobante [8] (00000109)
                self._format_numero_cbte(move),
                # Monto Imponible [12] (000293674,28 o -00293674,28 para NC)
                format_amount(line.invoice_id.amount_untaxed_signed, 12, 2, ","),
                # Monto Percepcion [11] (00293674,28 o -0293674,28 para NC)
                format_amount(-line.balance, 11, 2, ","),
                # Tipo Operacion [1] (A alta - B baja - M modificacion)
                'A',
            ]

            _logger.info(record)
            records_perc.append(''.join(record))

        period = fields.Date.from_string(self.date_to).strftime('%Y-%m-%d')

        # Generar archivo Percepciones
        self.ARBA_PERC = '\r\n'.join(records_perc)
        self.arba_perc_filename = 'ARBA-{}-perc.txt'.format(period)
        self.arba_perc_file = base64.encodestring(
            self.ARBA_PERC.encode('ISO-8859-1'))

    def generate_retenciones(self):
        records_ret = []
        
        # TODO: permitir configurar estas cuentas
        # TODO: cambiar por referencia a retencion ARBA aplicada
        iibb_account = self.env['account.account'].search([
            # ('code', '=', '231000'),
            ('code', '=', '2.1.03.01.023'),
        ])
        if not iibb_account:
            raise ValidationError('Cuenta de retencion ARBA aplicada no encontrada')

        self.ret_line_ids = self.env['account.move.line'].search([
            ('account_id', '=', iibb_account.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('move_id.state', '=', 'posted'),
            # TODO: order_by document_number
        ])
        self.payment_ids = self.ret_line_ids.mapped('move_id')

        for line in self.ret_line_ids:
            move = line.move_id
            partner_id = move.partner_id

            # Retencion
            record = [
                # CUIT [13] (30-70862198-2)
                self._format_cuit(partner_id),
                # Fecha [10] (03/11/2021)
                self._format_date(line.date),
                # Numero Sucursal [4] (0001)
                self._format_pto_venta(move),
                # Numero Emision [8] (00001867)
                self._format_numero_cbte(move),
                # Monto Percepcion [11] (00293674,28 o -0293674,28 para NC) - tax_line_ids.amount_total
                format_amount(-line.balance, 11, 2, ","),
                # Tipo Operacion [1] (A alta - B baja - M modificacion)
                'A'
            ]

            _logger.info(record)
            records_ret.append(''.join(record))

        period = fields.Date.from_string(self.date_to).strftime('%Y-%m-%d')

        # Generar archivo Retenciones
        self.ARBA_RET = '\r\n'.join(records_ret)
        self.arba_ret_filename = 'ARBA-{}-ret.txt'.format(period)
        self.arba_ret_file = base64.encodestring(
            self.ARBA_RET.encode('ISO-8859-1'))

# Valores en invoice_id:
# amount_tax / amount_total / amount_untaxed / vat_amount 
# document_letter_name, document_number, invoice_number

# TODO: document_number provisto por ????

# 1.1.01.05.021 - Percepción IIBB p. Buenos Aires sufrida
# 1.1.01.05.022 - Retención IIBB p. ARBA sufrida
# 2.1.03.01.023 - Retención IIBB ARBA aplicada
# 2.1.03.01.024 - Percepción IIBB ARBA aplicada

# Las presentaciones de retenciones/percepciones es en diferentes epocas?