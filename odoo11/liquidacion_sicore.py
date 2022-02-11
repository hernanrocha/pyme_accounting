from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

import logging
import base64
import traceback

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

class LiquidacionSicoreWizard(models.Model):
    _name = "l10n_ar.agente.sicore.wizard"
    _inherit = [ 'report.pyme_accounting.base' ]
    _description = 'Reporte de SICORE Agentes'

    tipo = fields.Selection(
        selection=[
            ('retenciones','Retenciones'),
            # ('percepciones','Percepciones')
        ], default='retenciones', string='Tipo de Liquidación')

    SICORE = fields.Text('SICORE', readonly=True)
    sicore_file = fields.Binary(string="SICORE Archivo", readonly=True)
    sicore_filename = fields.Char(string="SICORE Nombre de Archivo", readonly=True)
    sicore_csv_file = fields.Binary(string="SICORE Archivo", readonly=True)
    sicore_csv_filename = fields.Char(string="SICORE Nombre de Archivo", readonly=True)

    # invoice_ids = fields.Many2many('account.move', string="Facturas", compute="generate")
    payment_ids = fields.Many2many('account.move', string="Pagos", compute="generate")
    # perc_line_ids = fields.Many2many('account.move.line', string="Percepciones", compute="generate")
    ret_line_ids = fields.Many2many('account.move.line', string="Retenciones", compute="generate")

    def _format_numero_cbte(self, move):
        s = move.document_number.split("-")
        if len(s) != 2:
            # raise ValidationError('Numero de comprobante invalido: {}'.format(move.document_number))
            return '000000000000    '

        # TODO: definir si los 4 espacios se pueden reemplazar por 0s
        return '{}{}    '.format(s[0][-4:].zfill(4), s[1][-8:].zfill(8))

    def _format_codigo_regimen(self, payment):
        if not payment.communication:
            # return '000'
            raise ValidationError('Regimen no especificado en el campo comunicación del pago')

        return payment.communication.split('-')[0].strip().zfill(3)

    def generate(self):
        if not self.date_from or not self.date_to:
            return

        records, records_csv = self.generate_retenciones()

        # La ultima linea debe estar vacia
        records.append('')

        period = fields.Date.from_string(self.date_to).strftime('%Y-%m-%d')

        # Generar archivos
        self.SICORE = '\r\n'.join(records)
        self.sicore_filename = 'SICORE-{}.txt'.format(period)
        self.sicore_file = base64.encodestring(
            self.SICORE.encode('ISO-8859-1'))

        # Generar archivo excel
        SICORE_CSV = '\r\n'.join(records_csv)
        self.sicore_csv_filename = 'SICORE-{}.csv'.format(period)
        self.sicore_csv_file = base64.encodestring(
            SICORE_CSV.encode('ISO-8859-1'))


    def generate_retenciones(self):
        records = []
        records_csv = []

        # TODO: cambiar por referencia a retencion Ganancias aplicada
        iibb_account = self.env['account.account'].search([
            # ('code', '=', '231000'),
            ('code', '=', '2.1.03.01.006'),
        ])

        if not iibb_account:
            raise ValidationError('Cuenta de Retencion Ganancias aplicada no encontrada')

        self.ret_line_ids = self.env['account.move.line'].search([
            ('account_id', '=', iibb_account.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('move_id.state', '=', 'posted'),
            ('move_id.document_type_id', '!=', False),
            # TODO: order_by date asc, document_number asc
        ], order='date asc')
        self.payment_ids = self.ret_line_ids.mapped('move_id')

        for line in self.ret_line_ids:
            try:
                move = line.move_id
                payment = line.payment_id
                partner_id = move.partner_id

                record = [
                    # Campo 1 - Tipo de Comprobante (06 - Orden de Pago)
                    '06',
                    # Campo 2 - Fecha Comprobante (19/11/2021)
                    fields.Date.from_string(move.date).strftime('%d/%m/%Y'),
                    # Campo 3 - Pto. de Venta + Comprobante (000300066478)
                    # 4 punto de venta, 8 numero de comprobante, 4 vacios
                    self._format_numero_cbte(move),
                    # Campo 6 - Monto Retencion
                    format_amount(payment.withholding_base_amount, 16, 2, ','),
                    # TODO Campo 7 - Codigo de Impuesto (217 - Importe a las Ganancias)
                    '217', # payment.tax_withholding_id.???
                    # Campo 8 - Codigo de Regimen (078 - Enajenación de bienes muebles y bienes de cambio.)
                    # p.communication => "78 - Enajenación de bienes muebles y bienes de cambio."
                    self._format_codigo_regimen(payment),
                    # TODO Campo 9 - Codigo de Operacion (1 Retencion, 4 Imposibilidad de Retencion)
                    '1',
                    # Campo 10 - Base Imponible de la Retencion
                    format_amount(payment.withholding_base_amount, 14, 2, ','),
                    # Campo 11 - Fecha de la Retencion (19/11/2021)
                    fields.Date.from_string(move.date).strftime('%d/%m/%Y'),
                    # TODO Campo 12 - Codigo de Condicion (01 ??)
                    '01',
                    # TODO Campo 13 - Sujetos Suspendidos (0, 1, 2)
                    '0',
                    # Campo 14 - Importe Retenido
                    format_amount(abs(line.balance), 14, 2, ','),
                    # TODO Campo 15 - Porcentaje de Exclusion
                    format_amount(0, 6, 2, ','),
                    # Campo 16 - Fecha de Emision del Boletin (19/11/2021)
                    fields.Date.from_string(move.date).strftime('%d/%m/%Y'),
                    # Campo 17 - Tipo Documento
                    str(partner_id.main_id_category_id.afip_code).zfill(2),
                    # Campo 18 - Numero de Documento
                    partner_id.main_id_number.ljust(20, ' '),
                    # Campo 19 - Numero de Certificado Original
                    line.name[:14].rjust(14, ' '),
                    # TODO Relleno. Averiguar que significa este espacio
                    '                              0                      '
                ]

                records.append(''.join(record))
                records_csv.append(','.join(map(lambda r: '"{}"'.format(r), record)))
            except Exception as e:
                _logger.error("Error procesando percepcion. Asiento {}. {}".format(line.move_id.name, e))
                _logger.error(traceback.format_exc())

        return records, records_csv

# Cuentas:
# - 2.1.03.01.006 Retención ganancias aplicada (DONE)
# - 2.1.03.01.007 Percepción ganancias aplicada
# - 2.1.03.01.008 Retención IVA aplicada
# - 2.1.03.01.009 Percepción IVA aplicada

# TODO: separar en tipo (percepcion/retencion)
# Las presentaciones son mensual para percepciones y quincenal para retenciones
