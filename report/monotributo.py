# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
import locale

# Define locale es_AR
def _temp_localeconv(lc=locale.localeconv()):
    lc.update({'int_curr_symbol': 'ARS', 'currency_symbol': '$', 'mon_decimal_point': ',', 'mon_thousands_sep': '.', 'mon_grouping': [3, 0], 'positive_sign': '', 'negative_sign': '-', 'int_frac_digits': 2, 'frac_digits': 2, 'p_cs_precedes': 1, 'p_sep_by_space': 1, 'n_cs_precedes': 1, 'n_sep_by_space': 1, 'p_sign_posn': 3, 'n_sign_posn': 3, 'decimal_point': ',', 'thousands_sep': '.', 'grouping': [3, 0]})
    return lc

# Do the override
locale.localeconv = _temp_localeconv

# TODO: mover esto a su propio modelo
# https://www.afip.gob.ar/monotributo/categorias.asp
# Vigente desde 07/2021 a la fecha
categories = [
    {
        'char': 'A',
        'max_invoice': 370000.00,
        'service_payment': 2646.22,
        'goods_payment': 2646.22
    },
    {
        'char': 'B',
        'max_invoice': 550000.00,
        'service_payment': 2958.95,
        'goods_payment': 2958.95
    },
    {
        'char': 'C',
        'max_invoice': 770000.00,
        'service_payment': 3382.62,
        'goods_payment': 3325.44
    },
    {
        'char': 'D',
        'max_invoice': 1060000.00,
        'service_payment': 3988.85,
        'goods_payment': 3894.71
    },
    {
        'char': 'E',
        'max_invoice': 1400000.00,
        'service_payment': 5239.44,
        'goods_payment': 4711.54
    },
    {
        'char': 'F',
        'max_invoice': 1750000.00,
        'service_payment': 6271.46,
        'goods_payment': 5417.38
    },
    {
        'char': 'G',
        'max_invoice': 2100000.00,
        'service_payment': 7314.87,
        'goods_payment': 6168.24
    },
    {
        'char': 'H',
        'max_invoice': 2600000.00,
        'service_payment': 12789.38,
        'goods_payment': 10671.08
    },
    {
        'char': 'I',
        'max_invoice': 2910000.00,
        'service_payment': 0,
        'goods_payment': 15339.68
    },
    {
        'char': 'J',
        'max_invoice': 3335000.00,
        'service_payment': 0,
        'goods_payment': 17617.10
    },
    {
        'char': 'K',
        'max_invoice': 3700000.00,
        'service_payment': 0,
        'goods_payment': 19912.74
    },
]

# #------------------------------------------------------
# # Report controllers
# #------------------------------------------------------
# @http.route([
#     '/report/<converter>/<reportname>',
#     '/report/<converter>/<reportname>/<docids>',
# ], type='http', auth='user', website=True)
# def report_routes(self, reportname, docids=None, converter=None, **data):

# web/views/webclient_templates.xml
# web/views/report_templates.xml
# web/static/src/xml/report.xml
# - report.client_action.ControlButtons
# - report.client_action

# Archivos importantes:
# - base/models/ir_actions_report.py
# - base/report/report_base_report_irmodulereference.py

# El nombre debe ser 'report.<module>.<template_id>'
# 
# http://localhost:8069/report/html/pyme_accounting.report_payslip
# _get_report_values(None, { 'report_type': 'html' })
#
# http://localhost:8069/report/html/pyme_accounting.report_payslip/1
# _get_report_values([1], { 'report_type': 'html' })
# 
# http://localhost:8069/report/html/pyme_accounting.report_payslip/1,2
# _get_report_values([1, 2], { 'report_type': 'html' })

# WARN: para facturas, usar inoice_date en lugar de date
# WARN: para facturas, filtrar state=posted (o draft)
# WARN: para facturas, usar amount_total_signed para no mezclar facturas y notas de credito (o separarlas)

# Valores move_type en account.move:
#   entry        - Asiento contable
#   out_invoice  - Factura de cliente
#   out_refund   - Factura rectificativa de cliente
#   in_invoice   - Factura de proveedor
#   in_refund    - Factura rectificativa de proveedor
#   out_receipt  - Recibo de ventas
#   in_receipt   - Recibo de compra
class ReportMonotributoMensual(models.AbstractModel):
    _name = 'report.pyme_accounting.report_payslip'

    def _get_report_values(self, docids, data=None):
        print("REPORTE", docids, data)

        moves = self.env['account.move'].browse(docids)

        # https://www.odoo.com/documentation/14.0/es/developer/reference/orm.html#odoo.models.Model.read_group
        # Devuelve: {
        #   'invoice_date_count': 511, 
        #   'amount_total': 749800.69, 
        #   'invoice_date:month': 'febrero 2021', 
        #   '__domain': ['&', '&', 
        #       ('invoice_date', '>=', '2021-02-01'), 
        #       ('invoice_date', '<', '2021-03-01'), 
        #       ('move_type', 'in', ['out_invoice', 'out_refund'])]}
        moves = self.env['account.move'].read_group(
            # domain
            [ 
                ('company_id', '=', self.env.company.id),
                ('move_type', 'in', [ 'in_invoice', 'in_refund', 'out_invoice', 'out_refund' ]),
                ('state', '=', 'posted')
            ], 
            # fields
            [ 'amount_total:sum' ],
            # groupby
            [ 'invoice_date:month', 'move_type' ],
            # lazy: do all groupbys in one call.
            lazy=False
        )

        data = {}

        for m in moves:
            if not m['invoice_date:month'] in data:
                data[m['invoice_date:month']] = {
                    'date': m['invoice_date:month'],
                    'out_invoice': 0,
                    'in_invoice': 0,
                    'out_refund': 0,
                    'in_refund': 0
                }
            
            data[m['invoice_date:month']][m['move_type']] = m['amount_total']

        data = data.values()
        t_sales = 0
        t_purchases = 0
        t_balance = 0
        for d in data:
            d['total_sales'] = d['out_invoice'] - d['out_refund']
            d['total_purchases'] = d['in_invoice'] - d['in_refund']
            d['balance'] = d['total_sales'] - d['total_purchases']

            # Agregar a totales
            t_sales += d['total_sales']
            t_purchases += d['total_purchases']
            t_balance += d['balance']

            # TODO: Crear un helper para manejar monetary
            d['total_sales'] = locale.format_string("%.2f", d['total_sales'], grouping=True, monetary=True)
            d['total_purchases'] = locale.format_string("%.2f", d['total_purchases'], grouping=True, monetary=True)
            d['balance'] = locale.format_string("%.2f", d['balance'], grouping=True, monetary=True)

        # Formatear totales
        total_facturacion = t_sales
        t_sales = locale.format_string("%.2f", t_sales, grouping=True, monetary=True)
        t_purchases = locale.format_string("%.2f", t_purchases, grouping=True, monetary=True)
        t_balance = locale.format_string("%.2f", t_balance, grouping=True, monetary=True)

        category = None

        # TODO: chequear si se pasa a responsable inscripto
        # TODO: chequear si matchea con lo cargado en el sistema
        for c in categories:
            facturacion_anual = c['max_invoice']
            print("Checking", facturacion_anual)
            if facturacion_anual > total_facturacion:
                category = {
                    'char': c['char'],
                    'max_invoice': locale.format_string("%.2f", facturacion_anual, grouping=True, monetary=True),
                    # TODO: contemplar si vende bienes o servicios 
                    'payment': locale.format_string("%.2f", c['service_payment'], grouping=True, monetary=True)
                }
                break

        return {
            'name': 'Reporte Monotributo',
            'docs': data,
            'total': {
                'sales': t_sales,
                'purchases': t_purchases,
                'balance': t_balance
            },
            'category': category
        }

class ReportMonotributo:
    _name = 'l10n_ar.report.monotributo'

    def _print_report(self, report_type):
        self.ensure_one()
        # data = self._prepare_report_aged_partner_balance()
        # if report_type == "xlsx":
            # report_name = "a_f_r.report_aged_partner_balance_xlsx"
        # else:
            # report_name = "account_financial_report.aged_partner_balance"
        report_name = 'pyme_accounting.report_payslip'
        report_type = 'qweb-html'
        data = self.env['account.move'].read_group(
            [ ('move_type', 'in', [ 'out_invoice', 'out_refund' ])], # domain
            [ 'amount_total:sum' ],
            [ 'invoice_date:month' ]
        )

        for m in data:
            print(m)
            print(m.__context)

        report = self.env["ir.actions.report"].search(
            [("report_name", "=", report_name), ("report_type", "=", report_type)],
            limit=1,
        )

        return report.report_action(self, data=data)

    def get_report():

        # datas = {}
        # context = {}
        # data = self.read
        datas = {
            'ids': [],
            'model': 'l10n_ar.report.monotributo',
            'form': []
        }

        return {
            'type': 'ir.actions.report',
            'report_type': 'qweb-html', # Taken from general_ledger_wizard.py
            'report_name': 'name',
            'datas': datas
        }

        # return {
        #     'action': 'ir.actions.report',
        #     'name': 'Reporte Monotributo',
        #     # model
        #     'report_type': 'qweb-html', # Puede ser HTML o PDF
        #     'report_name': 'pyme_accounting.report_payslip', # Template ID
        #     'print_report_name': 'Monotributo Mes X',
        #     # 'binding_model_id'
        #     'binding_type': 'report'
        # }

# Clase base/models/ir_actions_report.py
# Ver account/wizard/account_report_common_view.xml
# Ver account/wizard/account_report_common.py
# Ver account/wizard/account_report_common_journal.py

# # TODO: Remove this

# self.ensure_one()
# report_name = 'pyme_accounting.report_payslip'
# report_type = 'qweb-html'
# data = {
#     'name': 'Template name'
# } # ....
# return (
#     self.env["ir.actions.report"]
#     .search(
#         [("report_name", "=", report_name), ("report_type", "=", report_type)],
#         limit=1,
#     )
#     .report_action(self, data=data)
# )

# ## TODO: End remove