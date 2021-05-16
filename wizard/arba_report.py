# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging
import csv
import io
import base64
import datetime
import calendar

_logger = logging.getLogger(__name__)

class IngresosBrutosArbaWizard(models.Model):
    _name = "l10n_ar.iibb.arba.wizard"
    _description = 'Reporte de Ingresos Brutos ARBA'

    iibb_report_date_from = fields.Date(string="Fecha Inicio", default=lambda self: self._default_date_from())
    iibb_report_date_to = fields.Date(string="Fecha Fin", default=lambda self: self._default_date_to())
    iibb_report_tax_percentage = fields.Selection(string="Alicuota", selection=[('1.50', '1.50%')], default="1.50")
    iibb_report_min_amount = fields.Float(string="Impuesto Mínimo", default=615)

    # TODO: obtain default currency_id=19
    # TODO: tener en cuenta el minimo ($615 en este caso)
    iibb_report_sale_total = fields.Float(string="Total de Ventas")
    
    iibb_report_tax_subtotal = fields.Float(string="Impuesto Determinado", compute="_compute_iibb_report_tax_subtotal")
    
    iibb_report_percepciones = fields.Float(string="Percepciones", compute="_compute_iibb_report_percepciones")

    iibb_report_deducciones = fields.Float(string="Deducciones", compute="_compute_iibb_report_deducciones")
    iibb_report_tax_prev_saldo = fields.Float(string="Saldo a favor del periodo anterior")

    iibb_report_tax_total_saldo = fields.Float(string="Saldo a favor del período", compute="_compute_iibb_report_tax_total_saldo")
    iibb_report_tax_total_to_pay = fields.Float(string="Saldo a Pagar", compute="_compute_iibb_report_tax_total_to_pay")

    iibb_percepciones = fields.Many2many(comodel_name="account.move.line")

    def generate_iibb(self):
        journal_taxes = self.env['account.journal'].search([
            ('name', '=', 'Impuestos')
        ])
        account_iibb = self.env['account.account'].search([
            ('name', '=', 'IIBB Prov. Bs. As.')
        ])
        account_percepciones = self.env['account.account'].search([
            ('name', '=', 'Percepción IIBB p. Buenos Aires sufrida')
        ])
        account_saldo_a_favor = self.env['account.account'].search([
            ('name', '=', 'Saldo a favor IIBB p. Buenos Aires')
        ])

        # TODO: crear asiento a pagar
        move = self.env['account.move'].create({
            'ref': 'Devengacion de IIBB',
            'date': self.iibb_report_date_to,
            'journal_id': journal_taxes.id
        })

        move.write({
            'line_ids': [
                # Impuesto IIBB
                (0, 0, { 'account_id': account_iibb.id, 'debit': self.iibb_report_tax_subtotal }),
                # Saldo a favor del periodo
                (0, 0, { 'account_id': account_saldo_a_favor.id, 'debit': -self.iibb_report_tax_total_saldo }),
                # Percepcion IIBB
                (0, 0, { 'account_id': account_percepciones.id, 'credit': -self.iibb_report_percepciones }),
                # TODO: Percepcion IIBB Banco
                # (0, 0, { 'account_id': 1, 'credit': 0 }),
                # TODO: Retencion IIBB
                # (0, 0, { 'account_id': 1, 'credit': 0 }),
                # TODO: Retencion IIBB Banco
                # (0, 0, { 'account_id': 1, 'credit': 0 }),
                # Saldo a favor IIBB periodo anterior
                (0, 0, { 'account_id': account_saldo_a_favor.id, 'credit': -self.iibb_report_tax_prev_saldo }),
            ]
        })

        # TODO: tener en cuenta el caso de IIBB a pagar

        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'main',
        }

    def calculate_iibb(self):
        # TODO: tener en cuenta notas de credito/debito
        # TODO: cancelar las facturas pendientes (state=draft)

        # Debe: Total de ventas * 1.50%

        # Haber:
        # - Percepcion IIBB
        # - Percepcion IIBB Banco
        # - Retencion IIBB
        # - Retencion IIBB Banco
        # - Saldo a Favor

        # Buscar percepciones
        account_percepciones = self.env['account.account'].search([
            ('name', '=', 'Percepción IIBB p. Buenos Aires sufrida')
        ])
        account_saldo_anterior = self.env['account.account'].search([
            ('name', '=', 'Saldo a favor IIBB p. Buenos Aires')
        ])

        self.iibb_percepciones = self.env['account.move.line'].search([
            ('parent_state', '=', 'posted'),
            ('account_id', '=', account_percepciones.id),
            ('date', '>=', self.iibb_report_date_from),
            ('date', '<=', self.iibb_report_date_to),
        ])

        saldo_anterior = self.env['account.move.line'].read_group([
            ('parent_state', '=', 'posted'),
            ('account_id', '=', account_saldo_anterior.id),
        ], ['balance:sum'], ['account_id'])
        print("SALDO ANTERIOR", saldo_anterior[0])

        # Buscar Facturas de Compras
        in_invoices = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('date', '>=', self.iibb_report_date_from),
            ('date', '<=', self.iibb_report_date_to)
        ])
        print(len(in_invoices), in_invoices)

        # Buscar Facturas de Ventas
        out_invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('date', '>=', self.iibb_report_date_from),
            ('date', '<=', self.iibb_report_date_to)
        ])
        print(len(out_invoices), out_invoices)

        # Ventas
        ventas = 0
        for invoice in out_invoices:
            ventas += invoice.amount_total
        self.iibb_report_sale_total = ventas

        deducciones = 0
        for invoice in in_invoices:
            deducciones += invoice.arba_iibb
        # TODO poner negativo?
        self.iibb_report_deducciones = -deducciones

        # TODO: calcular saldo del periodo anterior
        self.iibb_report_tax_prev_saldo = -saldo_anterior[0]['balance']

        # TODO: obtener deducciones no tomadas del periodo anterior

        # TODO: agregar "intereses al generar el pago"

        # TODO: crear helper para mantenerse en la misma ventana o revisar los recalculate existentes
        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'l10n_ar.iibb.arba.wizard',
            'res_id': self.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    @api.depends('iibb_report_sale_total', 'iibb_report_tax_percentage')
    def _compute_iibb_report_tax_subtotal(self):
        for p in self:
            p.iibb_report_tax_subtotal = p.iibb_report_sale_total * float(p.iibb_report_tax_percentage) / 100

    @api.depends('iibb_percepciones')
    def _compute_iibb_report_percepciones(self):
        for p in self:
            p.iibb_report_percepciones = 0
            for perc in p.iibb_percepciones:
                p.iibb_report_percepciones -= perc.balance

    @api.depends('iibb_report_percepciones')
    def _compute_iibb_report_deducciones(self):
        for p in self:
            # TODO: add percepciones_banco, retenciones, retenciones_banco
            p.iibb_report_deducciones = p.iibb_report_percepciones

    @api.depends('iibb_report_tax_subtotal', 'iibb_report_tax_prev_saldo', 'iibb_report_deducciones')
    def _compute_iibb_report_tax_total_saldo(self):
        self.iibb_report_tax_total_saldo = 0
        for p in self:
            saldo = p.iibb_report_tax_subtotal + p.iibb_report_tax_prev_saldo + p.iibb_report_deducciones
            if saldo <= 0:
                p.iibb_report_tax_total_saldo = saldo

    @api.depends('iibb_report_tax_subtotal', 'iibb_report_tax_prev_saldo', 'iibb_report_deducciones')
    def _compute_iibb_report_tax_total_to_pay(self):
        self.iibb_report_tax_total_to_pay = 0
        for p in self:
            saldo = p.iibb_report_tax_subtotal + p.iibb_report_tax_prev_saldo + p.iibb_report_deducciones
            if saldo > 0:
                p.iibb_report_tax_total_to_pay = saldo

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