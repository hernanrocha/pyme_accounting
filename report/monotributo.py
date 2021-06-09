# -*- coding: utf-8 -*-

from odoo import api, fields, models, _

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
        for d in data:
            # Handle as monetary
            d['total_sales'] = d['out_invoice'] - d['out_refund']
            d['total_purchases'] = d['in_invoice'] - d['in_refund']
            d['balance'] = d['total_sales'] - d['total_purchases']

        return {
            'name': 'Reporte Monotributo',
            'docs': data
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