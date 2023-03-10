from odoo import fields, models, _
from odoo.exceptions import ValidationError

import requests
import json
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

    tipo = fields.Selection(
        selection=[
            ('retenciones','Retenciones'),
            ('percepciones','Percepciones')
        ], default='retenciones', string='Tipo de Liquidación')

    ARBA_PERC = fields.Text('ARBA Percepciones', readonly=True)
    arba_perc_file = fields.Binary(string="ARBA Percepciones Archivo", readonly=True)
    arba_perc_filename = fields.Char(string="ARBA Percepciones Nombre de Archivo", readonly=True)
    arba_perc_csv_file = fields.Binary(string="ARBA Percepciones CSV Archivo", readonly=True)
    arba_perc_csv_filename = fields.Char(string="ARBA Percepciones CSV Nombre de Archivo", readonly=True)

    ARBA_RET = fields.Text('ARBA Retenciones', readonly=True)
    arba_ret_file = fields.Binary(string="ARBA Retenciones Archivo", readonly=True)
    arba_ret_filename = fields.Char(string="ARBA Retenciones Nombre de Archivo", readonly=True)
    arba_ret_csv_file = fields.Binary(string="ARBA Retenciones CSV Archivo", readonly=True)
    arba_ret_csv_filename = fields.Char(string="ARBA Retenciones CSV Nombre de Archivo", readonly=True)

    invoice_ids = fields.Many2many('account.move', string="Facturas", compute="generate")
    payment_ids = fields.Many2many('account.move', string="Pagos", compute="generate")
    perc_line_ids = fields.Many2many('account.move.line', string="Percepciones", compute="generate")
    ret_line_ids = fields.Many2many('account.move.line', string="Retenciones", compute="generate")

    def _format_cuit(self, partner):
        cuit = partner.main_id_number
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
        if not self.date_from or not self.date_to:
            return

        # self.generate_percepciones()
        self.generate_retenciones()
        self.generate_payments_alicuotaonline()

    def _format_situacion_iva(self, partner_id):
        res_iva = partner_id.afip_responsability_type_id
        iva_code = res_iva.code
        
        # Resp. Inscripto / Resp. Inscripto Factura M
        if iva_code in ['1', '1FM']:
            return 'iva_responsable_inscripto'
        # Exento
        if iva_code == '4':
            return 'iva_sujeto_exento'
        # Monotributo
        if iva_code == '6':
            return 'responsable_monotributo'
        
        raise ValidationError('La responsabilidad frente a IVA "%s" no está soportada.' % res_iva.name)

    def _get_alicuota_agip(self, partner_id, date):
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

    def generate_percepciones(self):
        records_perc = []
        records_perc_csv = []
        
        # TODO: permitir configurar estas cuentas
        # tax_account = self.env['account.account'].search([
        #     ('code', '=', '231000')
        # ])

        # TODO: cambiar por referencia a percepcion ARBA aplicada,
        # usar grupo de impuestos o dejar que lo configure el usuario
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
            ('move_id.document_type_id', '!=', False),
            # TODO: order_by date asc, document_number asc
        ])
        self.invoice_ids = self.perc_line_ids.mapped('move_id')

        for line in self.perc_line_ids:
            try:
                move = line.move_id
                partner_id = move.partner_id

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

                records_perc.append(''.join(record))
                records_perc_csv.append(','.join(map(lambda r: '"{}"'.format(r), record)))
            except:
                _logger.error("Error procesando percepcion. Asiento {}".format(line.move_id.name))

        period = fields.Date.from_string(self.date_to).strftime('%Y-%m-%d')

        # Generar archivo Percepciones
        self.ARBA_PERC = '\r\n'.join(records_perc)
        self.arba_perc_filename = 'ARBA-{}-perc.txt'.format(period)
        self.arba_perc_file = base64.encodestring(
            self.ARBA_PERC.encode('ISO-8859-1'))

        # Generar archivo excel
        ARBA_PERC_CSV = '\r\n'.join(records_perc_csv)
        self.arba_perc_csv_filename = 'ARBA-{}-perc.csv'.format(period)
        self.arba_perc_csv_file = base64.encodestring(
            ARBA_PERC_CSV.encode('ISO-8859-1'))

    def generate_retenciones(self):
        records_ret = []
        records_ret_csv = []
        
        # TODO: permitir configurar estas cuentas
        # TODO: cambiar por referencia a retencion ARBA aplicada
        iibb_account = self.env['account.account'].search([
            # ('code', '=', '231000'),
            ('code', '=', '2.1.03.01.011'),
        ])
        if not iibb_account:
            raise ValidationError('Cuenta de retencion ARBA aplicada no encontrada')

        self.ret_line_ids = self.env['account.move.line'].search([
            ('account_id', '=', iibb_account.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('move_id.state', '=', 'posted'),
            ('move_id.document_type_id', '!=', False),
            # TODO: order_by date asc, document_number asc
        ])
        self.payment_ids = self.ret_line_ids.mapped('move_id')

        for line in self.ret_line_ids:
            try:
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

                records_ret.append(''.join(record))
                records_ret_csv.append(','.join(map(lambda r: '"{}"'.format(r), record)))
            except:
                _logger.error("Error procesando retencion. Asiento {}".format(line.move_id.name))

        period = fields.Date.from_string(self.date_to).strftime('%Y-%m-%d')

        # Generar archivo Retenciones
        self.ARBA_RET = '\r\n'.join(records_ret)
        self.arba_ret_filename = 'ARBA-{}-ret.txt'.format(period)
        self.arba_ret_file = base64.encodestring(
            self.ARBA_RET.encode('ISO-8859-1'))

        # Generar archivo excel
        ARBA_RET_CSV = '\r\n'.join(records_ret_csv)
        self.arba_ret_csv_filename = 'ARBA-{}-ret.csv'.format(period)
        self.arba_ret_csv_file = base64.encodestring(
            ARBA_RET_CSV.encode('ISO-8859-1'))

    def generate_retenciones_alicuotaonline(self):
        records_ret = []
        
        # TODO: permitir configurar estas cuentas
        # TODO: cambiar por referencia a retencion ARBA aplicada
        iibb_account = self.env['account.account'].search([
            ('code', '=', '2.1.03.01.011'),
        ])
        if not iibb_account:
            raise ValidationError('Cuenta de retencion ARBA aplicada no encontrada')

        ret_line_ids = self.env['account.move.line'].search([
            ('account_id', '=', iibb_account.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('move_id.state', '=', 'posted'),
            ('move_id.document_type_id', '!=', False),
            # TODO: order_by date asc, document_number asc
        ])
        # payment_ids = ret_line_ids.mapped('move_id')

        for line in ret_line_ids:
            move = line.move_id
            partner_id = move.partner_id

            monto_ret = abs(line.balance)
            monto_alicuota = self._get_alicuota_agip(partner_id, move.date).alicuota_retencion
            monto_base = round(monto_ret * 100.0 / monto_alicuota, 2)

            d = {            
                    "retenido_cuit": self._format_cuit(partner_id),            
                    "retenido_razon_social": partner_id.name,
                    "retenido_iibb_numero": self._format_cuit(partner_id),               # TODO
                    "retenido_iibb_tipo": "local",             # TODO
                    "retenido_condicion_fiscal": self._format_situacion_iva(partner_id),
                    "cbte_fecha": line.date,
                    "cbte_gravado": round(monto_base, 2),
                    "cbte_iva": 0,
                    "cbte_nogravado_exento": 0,
                    "cbte_otros": 0,
                    "cbte_total": round(monto_base, 2),
                    "pago_fecha": line.date,
                    "pago_total": round(monto_base - monto_ret, 2),
                    "sucursal": move.document_number.split("-")[0],
                    "numero_emision": move.document_number.split("-")[1],
                    "external_id": move.id,
                    "withholdings": [
                        {
                            "id_jurisdiccion": 901,
                            "monto_base": round(monto_base, 2),
                            "alicuota": round(monto_alicuota, 2),
                            "monto_retencion": -line.balance,                    
                            "certificado_numero": 1,                    
                            "tipo_operacion": "alta"                
                        }
                    ]
            }

            _logger.info(json.dumps(d))
            records_ret.append(d)

        _logger.info(len(records_ret))
        # period = fields.Date.from_string(self.date_to).strftime('%Y-%m-%d')
        r = requests.post('http://18.189.239.110:8000/user/payments/import/', json={"data": records_ret}, headers={"X-User-Id": "60346912-f22a-4ce1-b469-12f22a3ce1e3"})
        _logger.info(r.json())

    def generate_payments_alicuotaonline(self):
        records_ret = []
        
        # TODO: permitir configurar estas cuentas
        # TODO: cambiar por referencia a retencion ARBA aplicada
        iibb_account = self.env['account.account'].search([
            ('code', '=', '2.1.03.01.011'),
        ])
        tax_id_agip = 21184
        if not iibb_account:
            raise ValidationError('Cuenta de retencion ARBA aplicada no encontrada')

        move_ids = self.env['account.payment.group'].search([
            ('partner_type', '=', 'supplier'),
            ('payment_date', '>=', '2022-05-01'),
            ('payment_date','<=','2022-05-31'),
            ('state','=','posted')
        ])
        # document_type_id = id=86, display_name='ORDEN DE PAGO X' 
        # res = env['account.move.line'].search([('account_id','=',129),('date', '>=', '2022-05-01'),('date','<=','2022-05-31'),('move_id.state','=','posted'),('move_id.document_type_id','!=',False)])
        # res = env['account.move'].search([('date', '>=', '2022-05-01'),('date','<=','2022-05-31'),('state','=','posted'),('document_type_id','!=',False)])
        # res = self.env['account.payment.group'].search([('partner_type', '=', 'supplier'),('payment_date', '>=', '2022-05-01'),('payment_date','<=','2022-05-31'),('state','=','posted')])
        # payment_ids = ret_line_ids.mapped('move_id')

        for move in move_ids:
            partner_id = move.partner_id

            # monto_ret = abs(line.balance)
            # monto_alicuota = self._get_alicuota_agip(partner_id, move.date).alicuota_retencion
            # monto_base = round(monto_ret * 100.0 / monto_alicuota, 2)

            taxes = move.payment_ids.filtered(lambda p: p.tax_withholding_id.id != False)

            w = []

            for tax in taxes:
                if tax.tax_withholding_id.id == tax_id_agip:
                    monto_ret = tax.computed_withholding_amount
                    monto_alicuota = self._get_alicuota_agip(partner_id, move.payment_date).alicuota_retencion
                    monto_base = round(monto_ret * 100.0 / monto_alicuota, 2)

                    w.append({
                        "id_jurisdiccion": 901,
                        "monto_base": round(monto_base, 2),
                        "alicuota": round(monto_alicuota, 2),
                        "monto_retencion": monto_ret,                    
                        "certificado_numero": int(tax.withholding_number),                    
                        "tipo_operacion": "alta"
                    })

            d = {            
                    "retenido_cuit": self._format_cuit(partner_id),            
                    "retenido_razon_social": partner_id.name,
                    "retenido_iibb_numero": self._format_cuit(partner_id),
                    "retenido_iibb_tipo": "local",
                    "retenido_condicion_fiscal": self._format_situacion_iva(partner_id),
                    "cbte_fecha": move.payment_date,
                    "cbte_gravado": 10, # TODO: round(monto_base, 2),
                    "cbte_iva": 0,
                    "cbte_nogravado_exento": 0,
                    "cbte_otros": 0,
                    "cbte_total": 10, # TODO: round(monto_base, 2),
                    "pago_fecha": move.payment_date,
                    "pago_total": 10, # round(monto_base - monto_ret, 2),
                    "sucursal": move.document_number.split("-")[0],
                    "numero_emision": move.document_number.split("-")[1],
                    "external_id": move.id,
                    "withholdings": w,
            }

            _logger.info(json.dumps(d))
            records_ret.append(d)

        _logger.info(len(records_ret))
        # period = fields.Date.from_string(self.date_to).strftime('%Y-%m-%d')
        r = requests.post('http://18.189.239.110:8000/user/payments/import/', 
            json={"data": records_ret}, 
            headers={"X-User-Id": "60346912-f22a-4ce1-b469-12f22a3ce1e3"})
        _logger.info(r.json())

# Valores en invoice_id:
# amount_tax / amount_total / amount_untaxed / vat_amount 
# document_letter_name, document_number, invoice_number

# TODO: document_number provisto por ????

# 1.1.01.05.021 - Percepción IIBB p. Buenos Aires sufrida
# 1.1.01.05.022 - Retención IIBB p. ARBA sufrida
# 2.1.03.01.023 - Retención IIBB ARBA aplicada
# 2.1.03.01.024 - Percepción IIBB ARBA aplicada

# TODO: separar en tipo (percepcion/retencion)
# Las presentaciones son mensual para percepciones y quincenal para retenciones
# TODO: Agregar header en el archivo CSV
