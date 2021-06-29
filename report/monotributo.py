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
categories = [
    {
        'char': 'A',
        'max_invoice': 282444.69,
        'service_payment': 1955.68,
        'goods_payment': 1955.68
    },
    {
        'char': 'B',
        'max_invoice': 423667.03,
        'service_payment': 2186.80,
        'goods_payment': 2186.80
    },
    {
        'char': 'C',
        'max_invoice': 564889.40,
        'service_payment': 2499.91,
        'goods_payment': 2457.65
    },
    {
        'char': 'D',
        'max_invoice': 847334.12,
        'service_payment': 2947.94,
        'goods_payment': 2878.37
    },
    {
        'char': 'E',
        'max_invoice': 1129778.77,
        'service_payment': 3872.18,
        'goods_payment': 3482.04
    },
    {
        'char': 'F',
        'max_invoice': 1412223.49,
        'service_payment': 4634.89,
        'goods_payment': 4003.69
    },
    {
        'char': 'G',
        'max_invoice': 1694668.19,
        'service_payment': 5406.02,
        'goods_payment': 4558.61
    },
    {
        'char': 'H',
        'max_invoice': 2353705.82,
        'service_payment': 9451.93,
        'goods_payment': 7886.41
    },
    {
        'char': 'I',
        'max_invoice': 2765604.35,
        'service_payment': 0,
        'goods_payment': 11336.71
    },
    {
        'char': 'J',
        'max_invoice': 3177502.86,
        'service_payment': 0,
        'goods_payment': 13019.83
    },
    {
        'char': 'K',
        'max_invoice': 3530558.74,
        'service_payment': 0,
        'goods_payment': 14716.41
    },
]

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