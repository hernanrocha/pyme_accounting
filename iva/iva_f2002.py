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
import datetime

_logger = logging.getLogger(__name__)

# -- Todas las facturas emitidas, agrupadas por condicion fiscal del cliente
# -- TODO: Filtrar por fecha, company_id y posted (mostrar borrador??)
# SELECT mv.tax, mv.total, mv.l10n_ar_afip_responsibility_type_id,
# resp.name as name
# FROM (
# 	SELECT SUM(am.amount_tax_signed) as tax, SUM(am.amount_total_signed) as total,
# am.l10n_ar_afip_responsibility_type_id
# 	FROM account_move am
# 	WHERE move_type IN ('out_invoice', 'out_refund')
# 	GROUP BY l10n_ar_afip_responsibility_type_id
# ) mv
# -- l10n_ar_afip_responsibility_type_id: condicion fiscal del partner en las facturas
# LEFT JOIN l10n_ar_afip_responsibility_type resp
# ON mv.l10n_ar_afip_responsibility_type_id = resp.id

def format_amount(amount):
    return '{:0.2f}'.format(amount)

def format_iva(code):
    # (1) No Gravado
    # (2) Exento 
    # (3) 0%
    codes = {
        '4': '10.5%',
        '5': '21%',
        '6': '27%',
        '8': '5%',
        '9': '2.5%',
    }
    return codes[code]

def split_iva_new(lines, activity_code, label):
    # Filtrar solo las lineas que aplican al IVA
    # No tiene en cuenta percepciones
    t = list(filter(lambda x: x, lines.mapped('tax_ids.l10n_ar_vat_afip_code')))

    lines_2002 = []
    for afip_code in t:
        # Filtrar lineas que coinciden con el IVA
        current_lines = lines.filtered(lambda l: afip_code in l.mapped('tax_ids.l10n_ar_vat_afip_code'))
        # Obtener la referencia al IVA
        current_tax = current_lines.tax_ids.filtered(lambda t: t.l10n_ar_vat_afip_code == afip_code)
        # Calcular IVA sobre la suma de las lineas
        # En el caso de incluir el IVA en el precio, balance y price_total coinciden.
        # En el caso de no incluir el IVA en el precio, balance es menor que price_total
        # balance es negativo para ventas y positivo para compras. price_total es siempre positivo
        
        # Sumar todo primero y luego aplicar el IVA genera diferencias con los comprobantes
        # current = current_tax.compute_all(sum(current_lines.mapped('price_total')))
        
        # Para evitar problemas de redondeo, primero se calculan los IVAs individuales,
        # y luego se suman los montos para obtener los totales
        # current_total = sum(current_lines.mapped('price_total'))
        # current_subtotal = sum(current_lines.mapped('price_subtotal'))
        # current_total = list(map(current_tax.compute_all, current_lines.mapped('price_total')))
        # price_total incluye las percepciones de IIBB (y con 1 peso, las que estan mal)
        current_subtotal = list(map(current_tax.compute_all, current_lines.mapped('price_subtotal')))
        # current = current_total if current_tax.price_include else current_subtotal
        base = sum(map(lambda c: c['taxes'][0]['base'], current_subtotal))
        iva = sum(map(lambda c: c['taxes'][0]['amount'], current_subtotal))

        lines_2002.append([ 
            activity_code,
            label,
            format_iva(afip_code),
            format_amount(base),
            format_amount(iva),
            format_amount(base + iva)
        ])
    return lines_2002

def filter_by_activity(lines, activity_id):
    if activity_id:
        return lines.filtered(lambda l: l.product_id and l.product_id.afip_activity_id == activity_id)
    else:
        return lines.filtered(lambda l: not l.product_id or not l.product_id.afip_activity_id)

def filter_by_category(lines, category):
    if category:
        return lines.filtered(lambda l: l.product_id and l.product_id.afip_f2002_category == category)
    else:
        return lines.filtered(lambda l: not l.product_id or not l.product_id.afip_f2002_category)

def split_iva(vat_taxes, label):
    # Filtrar solo las lineas que aplican al IVA
    # No tiene en cuenta percepciones
    t = list(filter(lambda x: x, vat_taxes.mapped('tax_group_id.l10n_ar_vat_afip_code')))
    
    _logger.info(" - Splitting: {} - {}".format(vat_taxes, t))
    lines = []
    for afip_code in t:
        taxes = vat_taxes.filtered(lambda x: x.tax_group_id.l10n_ar_vat_afip_code == afip_code)
        
        # Factura en pesos
        imp_neto = sum(taxes.mapped('tax_base_amount'))
        imp_liquidado = sum(taxes.mapped('price_subtotal'))
        lines.append([ 
            '000000',
            label,
            format_iva(afip_code),
            format_amount(imp_neto),
            format_amount(imp_liquidado),
            format_amount(imp_liquidado + imp_neto)
        ])
    return lines

# Las lineas "No gravadas", "Exentas" y "0%" no tienen una linea de impuestos asociada
# Las que tienen un monto IVA, en cambio, tienen una linea especifica.
# Se caracterizan por tener un tax_group_id diferente de NULL
# Las lineas que tienen un mismo IVA se agrupan en una sola

# TODO: No duplicar estas funciones

# TODO: Tambien se incluyen las compras a Monotributistas/Exentos?
def untaxed_exempt_line(line):
    codes = line.mapped('tax_ids').mapped('tax_group_id').mapped('l10n_ar_vat_afip_code')
    return '0' in codes or '1' in codes or '2' in codes

def taxed_0_line(line):
    codes = line.mapped('tax_ids').mapped('tax_group_id').mapped('l10n_ar_vat_afip_code')
    return '3' in codes

def taxed_line(line):
    # TODO: ignorar retenciones y percepciones
    return line.tax_group_id

def taxed_line_new(line):
    tax = list(filter(lambda x: x, line.mapped('tax_ids.l10n_ar_vat_afip_code')))
    
    if len(tax) != 1:
        raise ValidationError("Line {} - {} contiene 2 IVAs".format(line, line.move_id))

    return tax[0] in ['4', '5', '6', '8', '9']

# 1. Obtener actividades
# act = env['account.move'].search([]).mapped('invoice_line_ids.product_id.afip_activity_id')
#
# 2. Por cada actividad, obtener items
# m = env['account.move.line'].search([('product_id.afip_activity_id','=', 565)])
# m => account.move.line(2018,)
#
# 3. Filtrar Taxes que no sean de tipo IVA
#
# 4. Obtener Gravado, IVA y Total
# m.credit => 413.22
# m.tax_ids.compute_all(m.price_total)
# {
#   'taxes': [{
#       'id': 204, 
#       'name': 'IVA 21%', 
#       'amount': 86.78,  => IVA
#       'base': 413.22,   => GRAVADO
#       'sequence': 1, 
#       'account_id': 889, 
#       'analytic': False, 
#       'price_include': True, 
#       'tax_exigibility': 'on_invoice', 
#       'tax_repartition_line_id': 794, 
#       'group': None, 
#       'tag_ids': [], 
#       'tax_ids': []
#   }], 
#   'total_excluded': 413.22, 
#   'total_included': 500.0,      # TOTAL
#   'total_void': 413.22
# }

class ReportBase(models.Model):
    _name = 'report.pyme_accounting.base'

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        readonly=True,
        default=lambda self: self.env['res.company']._company_default_get('account.vat.ledger')
    )
    type = fields.Selection(
        [('sale', 'Venta'), ('purchase', 'Compra')],
        "Type",
        # required=True
    )

    name = fields.Char('Nombre') 
    date_from = fields.Date(string='Fecha Desde', required=True, readonly=True,
        default=lambda self: self._default_date_from(),
        states={'draft': [('readonly', False)]})
    date_to = fields.Date(string='Fecha Hasta', required=True, readonly=True,
        default=lambda self: self._default_date_to(),
        states={'draft': [('readonly', False)]})
    state = fields.Selection(
        [
            ('draft', 'Borrador'), 
            ('presented', 'Presentado'), 
            ('paid', 'Pagado'),
            ('cancel', 'Cancelado'),
        ],
        'Estado',
        required=True,
        default='draft'
    )
    note = fields.Html("Notas")

    def button_present(self):
        self.state = 'presented'

    def button_pay(self):
        self.state = 'paid'

    def button_cancel(self):
        self.state = 'cancel'

    def _default_date_from(self):
        today = datetime.date.today()
        first = today.replace(day=1)
        last_month_end = first - datetime.timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return last_month_start

    def _default_date_to(self):
        today = datetime.date.today()
        first = today.replace(day=1)
        last_month_end = first - datetime.timedelta(days=1)
        return last_month_end

class ReportIvaF2002DebitoVentas(models.Model):
    _name = 'report.pyme_accounting.report_iva_f2002.debito_ventas'

    actividad = fields.Char(string="Actividad")
    operaciones_con = fields.Char(string="Operaciones con...")
    tasa_iva = fields.Char(string="Tasa IVA")
    neto = fields.Float(string="Monto Neto")
    iva = fields.Float(string="Monto IVA")
    total = fields.Float(string="Monto Total")

    report_id = fields.Many2one(comodel_name="report.pyme_accounting.report_iva_f2002", 
        ondelete="cascade", invisible=True)

class ReportIvaF2002DebitoNCRecibidas(models.Model):
    _name = 'report.pyme_accounting.report_iva_f2002.debito_nc_rec'

    categoria = fields.Char(string="Categoría")
    tasa_iva = fields.Char(string="Tasa IVA")
    neto = fields.Float(string="Monto Neto")
    iva = fields.Float(string="Monto IVA")
    total = fields.Float(string="Monto Total")

    report_id = fields.Many2one(comodel_name="report.pyme_accounting.report_iva_f2002", 
        ondelete="cascade", invisible=True)

class ReportIvaF2002CreditoCompras(models.Model):
    _name = 'report.pyme_accounting.report_iva_f2002.credito_compras'

    categoria = fields.Char(string="Categoría")
    tasa_iva = fields.Char(string="Tasa IVA")
    neto = fields.Float(string="Monto Neto")
    iva = fields.Float(string="Monto IVA")
    total = fields.Float(string="Monto Total")

    report_id = fields.Many2one(comodel_name="report.pyme_accounting.report_iva_f2002", 
        ondelete="cascade", invisible=True)

class ReportIvaF2002CreditoNCEmitidas(models.Model):
    _name = 'report.pyme_accounting.report_iva_f2002.credito_nc_emitidas'

    actividad = fields.Char(string="Actividad")
    operaciones_con = fields.Char(string="Operaciones con...")
    tasa_iva = fields.Char(string="Tasa IVA")
    neto = fields.Float(string="Monto Neto")
    iva = fields.Float(string="Monto IVA")
    total = fields.Float(string="Monto Total")

    report_id = fields.Many2one(comodel_name="report.pyme_accounting.report_iva_f2002", 
        ondelete="cascade", invisible=True)

class ReportIvaF2002(models.Model):
    _name = 'report.pyme_accounting.report_iva_f2002'
    _inherit = [ 'report.pyme_accounting.base' ]

    @api.depends('date_from', 'date_to')
    def _compute_name(self):
        for r in self:
            if r.date_from and r.date_to:
                r.name = 'Liquidación IVA {} al {}'.format(
                    r.date_from.strftime('%d/%m/%Y'), 
                    r.date_to.strftime('%d/%m/%Y'))
            else:
                r.name = 'Liquidación IVA'

    name = fields.Char(compute=_compute_name)

    afip_activity_ids = fields.Many2many('l10n_ar.afip.actividad', related="company_id.afip_activity_ids")

    debito_ventas = fields.One2many(string="Ventas", 
        comodel_name="report.pyme_accounting.report_iva_f2002.debito_ventas", 
        inverse_name="report_id")
    # TODO: debito_ventas_bienes
    debito_nc_recibidas = fields.One2many(string="Notas de Crédito Recibidas", 
        comodel_name="report.pyme_accounting.report_iva_f2002.debito_nc_rec", 
        inverse_name="report_id")
    credito_compras = fields.One2many(string="Compras", 
        comodel_name="report.pyme_accounting.report_iva_f2002.credito_compras", 
        inverse_name="report_id")
    credito_nc_emitidas = fields.One2many(string="Notas de Crédito Emitidas", 
        comodel_name="report.pyme_accounting.report_iva_f2002.credito_nc_emitidas", 
        inverse_name="report_id")

    total_debito = fields.Float(string="Total Débito Fiscal")
    total_credito = fields.Float(string="Total Crédito Fiscal")
    saldo_anterior = fields.Float(string="Saldo Técnico Período Anterior")
    saldo_libre_afip = fields.Float(string="Saldo Libre disponibilidad a favor de AFIP")
    saldo_libre_responsable = fields.Float(string="Saldo Libre disponibilidad a favor del Responsable")

    ingresos_retenciones = fields.Float(string="Retenciones Sufridas")
    ingresos_percepciones = fields.Float(string="Percepciones Sufridas")
    # TODO: 'ingresos_acuenta': [],
    saldo_total_afip = fields.Float(string="Saldo Total a favor de AFIP")
    saldo_total_responsable = fields.Float(string="Saldo Total a favor del Responsable")

    def button_compute(self):
        self.debito_ventas = [(5,0,0)]
        self.credito_nc_emitidas = [(5,0,0)]

        self.credito_compras = [(5,0,0)]  
        self.debito_nc_recibidas = [(5,0,0)]

        debito_ventas = self.get_ventas(self.get_digital_invoices('out_invoice'))
        for i in debito_ventas['lines']:
            self.env['report.pyme_accounting.report_iva_f2002.debito_ventas'].create({
                'actividad': i[0],
                'operaciones_con': i[1],
                'tasa_iva': i[2],
                'neto': i[3],
                'iva': i[4],
                'total': i[5],
                'report_id': self.id
            })

        credito_nc_emitidas = self.get_ventas(self.get_digital_invoices('out_refund'))
        for i in credito_nc_emitidas['lines']:
            self.env['report.pyme_accounting.report_iva_f2002.credito_nc_emitidas'].create({
                'actividad': i[0],
                'operaciones_con': i[1],
                'tasa_iva': i[2],
                'neto': i[3],
                'iva': i[4],
                'total': i[5],
                'report_id': self.id
            })
        
        credito_compras = self.get_compras(self.get_digital_invoices('in_invoice'))        
        for i in credito_compras['lines']:
            self.env['report.pyme_accounting.report_iva_f2002.credito_compras'].create({
                'categoria': i[1],
                'tasa_iva': i[2],
                'neto': i[3],
                'iva': i[4],
                'total': i[5],
                'report_id': self.id
            })
        
        debito_nc_recibidas = self.get_compras(self.get_digital_invoices('in_refund'))
        for i in debito_nc_recibidas['lines']:
            self.env['report.pyme_accounting.report_iva_f2002.debito_nc_rec'].create({
                'categoria': i[1],
                'tasa_iva': i[2],
                'neto': i[3],
                'iva': i[4],
                'total': i[5],
                'report_id': self.id
            })
        
        self.total_debito = float(debito_ventas['total'][1]) + float(debito_nc_recibidas['total'][1])
        self.total_credito =  float(credito_compras['total'][1]) + float(credito_nc_emitidas['total'][1])

        self.saldo_anterior = 0 # TODO
        self.saldo_libre_afip = self.total_debito - self.total_credito
        self.saldo_libre_responsable = -self.saldo_libre_responsable

        self.ingresos_retenciones = 0 # TODO
        self.ingresos_percepciones = 0 # TODO
        self.saldo_total_afip = self.total_debito - self.total_credito - self.ingresos_retenciones - self.ingresos_percepciones
        self.saldo_total_responsable = -self.saldo_total_afip

    def _get_report_values(self, docids, data=None):

        debito_ventas = self.get_ventas(self.get_digital_invoices('out_invoice'))
        credito_nc_emitidas = self.get_ventas(self.get_digital_invoices('out_refund'))

        credito_compras = self.get_compras(self.get_digital_invoices('in_invoice'))        
        debito_nc_recibidas = self.get_compras(self.get_digital_invoices('in_refund'))
        
        # Percepciones/Retenciones IVA
        perc = sum(self.env['l10n_ar.impuestos.deduccion'].search([
            ('company_id', '=', self.env.company.id),
            ('type', '=', 'iva_percepcion'),
            ('state', '=', 'available'),
            ('date', '>=', '2021-09-01'),
            ('date', '<=', '2021-09-30')
        ]).mapped('amount'))

        ret = sum(self.env['l10n_ar.impuestos.deduccion'].search([
            ('company_id', '=', self.env.company.id),
            ('type', '=', 'iva_retencion'),
            ('state', '=', 'available'),
            ('date', '>=', '2021-09-01'),
            ('date', '<=', '2021-09-30')
        ]).mapped('amount'))

        # TODO: agregar contribuciones patronales (Total vs Computable)
        # TODO: agregar impuesto al combustible
        # TODO: Cuales son las que no generan credito fiscal???
        # TODO: revisar condiciones fiscales de los CUITs cargados

        total_debito = float(debito_ventas['total'][1]) + float(debito_nc_recibidas['total'][1])
        total_credito =  float(credito_compras['total'][1]) + float(credito_nc_emitidas['total'][1])

        company_id = self.env['res.company']._company_default_get('report.pyme_accounting.report_iva_f2002')

        return {
            'name': 'IVA Por Actividad - F. 2002',
            'actividades_afip': company_id.afip_activity_ids,
            # Primer Parrafo
            'debito_ventas': debito_ventas,
            # TODO
            # 'debito_ventas_bienes': [],
            'debito_nc_recibidas': debito_nc_recibidas,
            'credito_compras': credito_compras,
            'credito_nc_emitidas': credito_nc_emitidas,
            'operaciones_no_gravadas': [],
            # TODO
            # 'credito_acuenta': [],
            # Segundo Parrafo
            'total_debito': format_amount(total_debito),
            'total_credito': format_amount(total_credito),
            'saldo_anterior': format_amount(0.0),
            'saldo_libre_afip': total_debito > total_credito,
            'saldo_libre_disp': format_amount(abs(total_credito - total_debito)),
            'ingresos_retenciones': format_amount(ret),
            'ingresos_percepciones': format_amount(perc),
            'ingresos_acuenta': [],
            'saldo_total_afip': format_amount(total_credito - total_debito - ret - perc)
        }

    def get_digital_invoices(self, move_type):
        _logger.info('{} - {} - {}'.format(self.env, self.env.company.id, self.env.user.company_id))

        # TODO: filtrado por fechas, confirmado
        return self.env['account.move'].search(
            [
                ('company_id', '=', self.env.company.id),
                ('state', '=', 'posted'),
                ('move_type', '=', move_type),
                ('date', '>=', self.date_from),
                ('date', '<=', self.date_to)
            ], 
            order='invoice_date asc')

    def get_ventas(self, invoices):
        lines = []
        activity_ids = invoices.mapped('invoice_line_ids.product_id.afip_activity_id')

        # Obtener las que no tienen actividad y luego separado por actividad
        # TODO: revisar que no se repita cuando el producto exista pero no tenga categoria
        lines.extend(self._get_ventas(invoices, False))
        for activity_id in activity_ids:
            lines.extend(self._get_ventas(invoices, activity_id))
        
        _logger.info("lines: {}".format(lines))

        # Calcular Totales

        total = [ 0.00, 0.00, 0.00 ]
        for line in lines:
            total[0] += float(line[3])
            total[1] += float(line[4])
            total[2] += float(line[5])
        
        total[0] = format_amount(total[0])
        total[1] = format_amount(total[1])
        total[2] = format_amount(total[2])

        return { 'lines': lines, 'total': total }

    def get_compras(self, invoices):
        lines = []

        categories = invoices.mapped('invoice_line_ids.product_id.afip_f2002_category')

        # TODO: borrar esto
        # Obtener las que no tienen categoria y luego separado por categoria
        # lines_all = invoices.mapped('line_ids').filtered(taxed_line)
        # lines.extend(split_iva(lines_all, "Compra de Bienes (excepto Bs de Uso)"))

        lines.extend(self._get_compras(invoices, False))
        for category in categories:
            lines.extend(self._get_compras(invoices, category))
        
        # Operaciones Gravadas al 0%
        lines_taxed_0 = invoices.mapped('invoice_line_ids').filtered(taxed_0_line)
        _logger.info("lines_taxed_0: {}".format(lines_taxed_0))
        if len(lines_taxed_0):
            amount = sum(lines_taxed_0.mapped('price_total'))
            lines.append([ 
                '',
                "Operaciones Gravadas al 0%",
                "0%",
                format_amount(amount),
                format_amount(0),
                format_amount(amount),
            ])

        # Operaciones Exentas / No Gravadas
        lines_untaxed_exempt = invoices.mapped('invoice_line_ids').filtered(untaxed_exempt_line)
        _logger.info("lines_untaxed_exempt: {}".format(lines_untaxed_exempt))
        if len(lines_untaxed_exempt):
            amount = sum(lines_untaxed_exempt.mapped('price_total'))
            lines.append([ 
                '',
                "Operaciones No Gravadas y Exentas",
                "-",
                format_amount(amount),
                format_amount(0),
                format_amount(amount),
            ])
        
        _logger.info("lines: {}".format(lines))

        # Calcular Totales
        total = [ 0.00, 0.00, 0.00 ]
        for line in lines:
            total[0] += float(line[3])
            total[1] += float(line[4])
            total[2] += float(line[5])
        
        total[0] = format_amount(total[0])
        total[1] = format_amount(total[1])
        total[2] = format_amount(total[2])

        return { 'lines': lines, 'total': total }    

    def _get_ventas(self, invoices, activity_id):
        activity_code = activity_id.code if activity_id else '-'

        _logger.info("GET VENTAS: {}".format(invoices, activity_id))

        # Para NC de Compras, es lo mismo que facturas de compra:
        # - Bienes en mercado local
        # -
        # Para NC de Ventas, es lo mismo que facturas de venta:
        # - RI
        # - CF, Exentos y No Alcanzados
        # - Monotributistas
        # - Op. Gravadas al 0%
        # - Op. No Gravadas y Exentas
        #
        # Para Venta de Bienes de Uso:
        # - Responsables Inscriptos
        # - CF, Monotributistas, Exentos, No Alcanzados

        # TODO: separar por actividad

        # Condicion Fiscal
        # 1 - IVA Responsable Inscripto
        # 4 - Exento
        # 5 - Consumidor Final
        # 6 - Monotributo
        # 99 - No Alcanzado

        lines = []

        # Responsables inscriptos
        inv_ri = invoices.filtered(
            lambda i: i.l10n_ar_afip_responsibility_type_id.code == '1')

        lines_ri_new = inv_ri.mapped('invoice_line_ids').filtered(taxed_line_new)
        lines_ri_new = filter_by_activity(lines_ri_new, activity_id)
        lines.extend(split_iva_new(lines_ri_new, activity_code, "Responsables Inscriptos"))

        # Consumidores Finales, Exentos y No Alcanzados
        inv_cf_ex_na = invoices.filtered(
            lambda i: i.l10n_ar_afip_responsibility_type_id.code in [ '4', '5', '99' ])

        lines_cf_ex_na_new = inv_cf_ex_na.mapped('invoice_line_ids').filtered(taxed_line_new)
        lines_cf_ex_na_new = filter_by_activity(lines_cf_ex_na_new, activity_id)
        lines.extend(split_iva_new(lines_cf_ex_na_new, activity_code, "Cons. Finales, Exentos y No Alcanzados"))

        # Monotributistas
        inv_mt = invoices.filtered(
            lambda i: i.l10n_ar_afip_responsibility_type_id.code == '6')
        lines_mt_new = inv_mt.mapped('invoice_line_ids').filtered(taxed_line_new)
        lines_mt_new = filter_by_activity(lines_mt_new, activity_id)
        lines.extend(split_iva_new(lines_mt_new, activity_code, "Monotributistas"))

        # Operaciones Gravadas al 0%
        lines_taxed_0 = invoices.mapped('invoice_line_ids').filtered(taxed_0_line)
        lines_taxed_0 = filter_by_activity(lines_taxed_0, activity_id)
        if len(lines_taxed_0):
            amount = sum(lines_taxed_0.mapped('price_total'))
            lines.append([ 
                activity_code,
                "Operaciones Gravadas al 0%",
                "0%",
                format_amount(amount),
                format_amount(0),
                format_amount(amount),
            ])

        # Operaciones Exentas / No Gravadas
        lines_untaxed_exempt = invoices.mapped('invoice_line_ids').filtered(untaxed_exempt_line)
        lines_untaxed_exempt = filter_by_activity(lines_untaxed_exempt, activity_id)
        if len(lines_untaxed_exempt):
            amount = sum(lines_untaxed_exempt.mapped('price_total'))
            lines.append([ 
                activity_code,
                "Operaciones No Gravadas y Exentas",
                "-",
                format_amount(amount),
                format_amount(0),
                format_amount(amount),
            ])

        return lines

    def _get_compras(self, invoices, category):
        lines = []

        # Responsables inscriptos
        lines_all_new = invoices.mapped('invoice_line_ids').filtered(taxed_line_new)
        lines_all_new = filter_by_category(lines_all_new, category)
        lines.extend(split_iva_new(lines_all_new, category, category or '-'))

        return lines

# Todas las lineas de factura indicando el impuesto asociado
# TODO: Filtrar solo las de IVA
# SELECT lines.tax_id, lines.tax_name,
# sum(lines.amount_taxed) amount_taxed, 
# sum(lines.amount_tax) amount_tax, 
# sum(lines.amount_total) amount_total
# FROM
# (SELECT
# 	am.id move_id, am.name as name, 
# 	line.id line_id,
# 	tax.id as tax_id, 
# 	tax.tax_group_id tax_group_id,
# 	tax.name as tax_name,
# 	line.price_subtotal amount_taxed, 
# 	(line.price_total - line.price_subtotal) amount_tax,
# 	line.price_total amount_total
# 	-- line.exclude_from_invoice_tab,
# 	--am.amount_tax_signed as tax, am.amount_total_signed as total, am.l10n_ar_afip_responsibility_type_id
# 	FROM account_move am
# 	JOIN account_move_line line
# 	ON line.move_id = am.id
# 	-- Tabla NxN entre line y tax
# 	JOIN account_move_line_account_tax_rel mtl
# 	ON line.id = mtl.account_move_line_id
# 	-- Tabla de taxes
# 	JOIN account_tax tax
# 	ON tax.id = mtl.account_tax_id
# 	WHERE am.move_type IN ('out_invoice')
# 	AND am.company_id = 4
# 	AND line.exclude_from_invoice_tab IS NOT TRUE
# 	ORDER BY am.date -- TODO: definir este valor
# ) lines
# GROUP BY lines.tax_id, lines.tax_name

# Ver lineas de impuestos. Puede haber mas de una por linea de factura
# Por ejemplo una para IVA, otra para percepcion, etc.
# Las facturas con IVA No Gravado/Exento no tienen linea de impuesto
# SELECT tl.id, tl.move_id move_id, tl.tax_line_id tax_id, tl.tax_group_id, 
# tl.tax_base_amount, tl.price_unit, tl.tax_exigible 
# FROM account_move_line tl
# WHERE tax_line_id IS NOT NULL
#
# company_id => Empresa
# move_id => ID de Factura Padre
# currency_id => Moneda (Peso)
# partner_id => Cliente/Proveedor
# parent_state => Estado de la factura (Posted/Draft)
# tax_line_id => ID del impuesto (IVA 21%/IVA 10.5%)
# tax_group_id => Gravado/No Gravado/Municipales/Provinciales
# tax_base_amount => 4524.89 (Monto Gravado)
# price_unit => 475.11 (IVA)
# tax_exigible => true (se puede tomar???)
# l10n_latam_document_type_id => Tipo de factura (A,B,C)

# Lineas de factura con montos de IVA
# SELECT
# am.id move_id, am.name as name, 
# line.id line_id, 
# tax.id as tax_id, tax.name as tax_name,
# line.price_subtotal amount_taxed, 
# (line.price_total - line.price_subtotal) amount_tax, 
# line.price_total amount_total
# -- line.exclude_from_invoice_tab,
# --am.amount_tax_signed as tax, am.amount_total_signed as total, am.l10n_ar_afip_responsibility_type_id
# FROM account_move am
# JOIN account_move_line line
# ON line.move_id = am.id
# JOIN account_move_line_account_tax_rel mtl
# ON line.id = mtl.account_move_line_id
# JOIN account_tax tax
# ON tax.id = mtl.account_tax_id
# WHERE am.move_type IN ('out_invoice')
# AND am.company_id = 4
# AND line.exclude_from_invoice_tab IS NOT TRUE
# ORDER BY am.date -- TODO: definir este valor

# TODO: Por que se usa commercial_partner_id y no partner_id
# TODO: name vs display_name en res_partner



# PARRAFO 1

# DEBITO FISCAL (VENTAS)
#  
# JOIN 1: Codigo Actividad => Cada actividad AFIP de la empresa (definida por producto)
# 
# JOIN 2: Operacion con    => [
#   "Responsables Inscriptos", 
#   "Cons. Finales, Exentos y No Alcanzados",
#   "Monotributistas"
# ]
# Filtrar operaciones de tipo "Otros conceptos", "Operaciones no gravadas y exentas"
# En SOS Contador, [ 
# "2. Cons. Final, Exento y No Alcanzados", 
# "4. Op. Gravadas al 0%", 
# "5. Operaciones No Gravadas y Exentas excepto exportaciones" ]
#
# JOIN 3: Tasa IVA (para las basicas)
#
# Mostrar: Neto, IVA, Total

# DEBITO FISCAL (VENTAS BIENES DE USO)
# Es igual, solo que aplica a productos marcados como bienes de uso

# NOTAS DE CREDITO RECIBIDAS (COMPRAS)