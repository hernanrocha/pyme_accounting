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

# TODO: separar las ventas por actividad
class IngresosBrutosArbaWizard(models.Model):
    _name = "l10n_ar.iibb.arba.wizard"
    _inherit = [ 'report.pyme_accounting.base' ]
    _description = 'Reporte de Ingresos Brutos ARBA'

    @api.depends('date_from', 'date_to')
    def _compute_name(self):
        for r in self:
            if r.date_from and r.date_to:
                r.name = 'Liquidación IIBB {} al {}'.format(
                    r.date_from.strftime('%d/%m/%Y'), 
                    r.date_to.strftime('%d/%m/%Y'))
            else:
                r.name = 'Liquidación IIBB'

    name = fields.Char(compute=_compute_name)

    # Determinacion del impuesto
    iibb_report_sale_total = fields.Float(string="Total de Ventas")
    iibb_company_tax_percentage = fields.Float(string="Alicuota", compute="_compute_iibb_company_tax_percentage")
    iibb_company_min_amount = fields.Float(string="Impuesto Minimo", compute="_compute_iibb_company_min_amount")
    iibb_report_tax_subtotal = fields.Float(string="Impuesto Determinado", compute="_compute_iibb_report_tax_subtotal")
    
    # Calculo de deducciones
    iibb_report_percepciones = fields.Float(string="Percepciones", compute="_compute_iibb_report_percepciones")
    iibb_report_retenciones = fields.Float(string="Retenciones", compute="_compute_iibb_report_retenciones")
    iibb_report_retenciones_bancarias = fields.Float(string="Retenciones Bancarias", compute="_compute_iibb_report_retenciones_bancarias")
    iibb_report_devoluciones_bancarias = fields.Float(string="Devoluciones Bancarias", compute="_compute_iibb_report_devoluciones_bancarias")
    iibb_report_deducciones = fields.Float(string="Total Deducciones", compute="_compute_iibb_report_deducciones")

    # Saldo a favor / a pagar
    iibb_report_tax_prev_saldo = fields.Float(string="Saldo a favor del periodo anterior")
    iibb_report_tax_total_saldo = fields.Float(string="Saldo a favor del período", compute="_compute_iibb_report_tax_total_saldo")
    iibb_report_tax_total_to_pay = fields.Float(string="Saldo a pagar", compute="_compute_iibb_report_tax_total_to_pay")

    # Relaciones
    iibb_percepciones = fields.Many2many(comodel_name="l10n_ar.impuestos.deduccion",
        relation="l10n_ar_iibb_arba_percepciones")
    iibb_retenciones = fields.Many2many(comodel_name="l10n_ar.impuestos.deduccion",
        relation="l10n_ar_iibb_arba_retenciones")
    iibb_retenciones_bancarias = fields.Many2many(comodel_name="l10n_ar.impuestos.deduccion",
        relation="l10n_ar_iibb_arba_retenciones_bancarias")
    iibb_devoluciones_bancarias = fields.Many2many(comodel_name="l10n_ar.impuestos.deduccion",
        relation="l10n_ar_iibb_arba_devoluciones_bancarias")

    move_id = fields.Many2one(comodel_name="account.move",
        string="Asiento Generado", ondelete="cascade")
    line_ids = fields.One2many('account.move.line', related="move_id.line_ids")

    def generate_iibb(self):
        # TODO: Mostrar una seccion con las facturas en borrador

        journal_taxes = self.env['account.journal'].search([
            ('name', '=', 'Impuestos')
        ])
        if not journal_taxes:
            # TODO: permitir crear diarios
            journal_taxes = self.env['account.journal'].sudo().create({
                'company_id': self.company_id.id,
                'name': 'Impuestos',
                'type': 'general',
                'code': 'IMP',
            })
        # TODO: buscar por codigo y no por nombre
        account_iibb = self.env['account.account'].search([
            # TODO: hacer dependiente de la compañia
            ('company_id', '=', self.env.company.id),
            ('name', '=', 'IIBB ARBA')
        ])
        account_percepciones = self.env['account.account'].search([
            # TODO: hacer dependiente de la compañia
            ('company_id', '=', self.env.company.id),
            ('name', '=', 'Percepción IIBB Buenos Aires sufrida')
        ])
        account_saldo_a_favor = self.env['account.account'].search([
            # TODO: hacer dependiente de la compañia
            ('company_id', '=', self.env.company.id),
            ('name', '=', 'Saldo a favor IIBB Buenos Aires')
        ])
        _logger.info("Cuentas: {} - {} - {}".format(account_iibb, account_percepciones, account_saldo_a_favor))

        # TODO: crear asiento a pagar
        if not self.move_id:
            self.move_id = self.env['account.move'].create({
                'state': 'draft',
                'ref': 'Devengacion de IIBB',
                'date': self.date_to,
                'journal_id': journal_taxes.id
            })
        else:
            self.move_id.write({ 
                'date': self.date_to 
            })


        self.move_id.line_ids = [(5,0,0)]
        if self.iibb_report_tax_total_to_pay > 0:
            self.move_id.write({
                'line_ids': [
                    # Impuesto IIBB
                    (0, 0, { 'account_id': account_iibb.id, 'debit': self.iibb_report_tax_subtotal }),
                    # Saldo a favor del periodo
                    (0, 0, { 'account_id': account_saldo_a_favor.id, 'debit': -self.iibb_report_tax_total_saldo }),
                    # Percepcion IIBB
                    (0, 0, { 'account_id': account_percepciones.id, 'credit': -self.iibb_report_percepciones }),
                    # TODO: Retencion IIBB
                    (0, 0, { 'account_id': account_percepciones.id, 'credit': -self.iibb_report_retenciones }),
                    # TODO: Retencion IIBB Banco
                    (0, 0, { 'account_id': account_percepciones.id, 'credit': -self.iibb_report_retenciones_bancarias }),
                    # TODO: Devolucion IIBB Banco
                    (0, 0, { 'account_id': account_percepciones.id, 'debit': self.iibb_report_devoluciones_bancarias }),
                    # Saldo a favor IIBB periodo anterior
                    (0, 0, { 'account_id': account_saldo_a_favor.id, 'credit': -self.iibb_report_tax_prev_saldo }),
                ]
            })
        else:
            self.move_id.write({
                'line_ids': [
                    # Impuesto IIBB
                    (0, 0, { 'account_id': account_iibb.id, 'debit': self.iibb_report_tax_subtotal }),
                    # Saldo a favor del periodo
                    (0, 0, { 'account_id': account_saldo_a_favor.id, 'debit': -self.iibb_report_tax_total_saldo }),
                    # Percepcion IIBB
                    (0, 0, { 'account_id': account_percepciones.id, 'credit': -self.iibb_report_percepciones }),
                    # TODO: Retencion IIBB
                    # (0, 0, { 'account_id': 1, 'credit': 0 }),
                    # TODO: Retencion IIBB Banco
                    # (0, 0, { 'account_id': 1, 'credit': 0 }),
                    # TODO: Devolucion IIBB Banco
                    # (0, 0, { 'account_id': 1, 'credit': 0 }),
                    # Saldo a favor IIBB periodo anterior
                    (0, 0, { 'account_id': account_saldo_a_favor.id, 'credit': -self.iibb_report_tax_prev_saldo }),
                ]
            })

    def calculate_iibb(self):
        # TODO: tener en cuenta notas de credito/debito
        # TODO: cancelar las facturas pendientes (state=draft)

        # Debe: Total de ventas * 1.50%
        # Debe: Devolucion IIBB Banco

        # Haber:
        # - Percepcion IIBB
        # - Retencion IIBB
        # - Retencion IIBB Banco
        # - Saldo a Favor

        # Buscar percepciones
        account_percepciones = self.env['account.account'].search([
            # TODO: hacer dependiente de la compañia
            ('company_id', '=', self.env.company.id),
            ('name', '=', 'Percepción IIBB p. Buenos Aires sufrida')
        ])
        account_saldo_anterior = self.env['account.account'].search([
            # TODO: hacer dependiente de la compañia
            ('company_id', '=', self.env.company.id),
            ('name', '=', 'Saldo a favor IIBB p. Buenos Aires')
        ])

        # Calcular percepciones
        self.iibb_percepciones = self.env['l10n_ar.impuestos.deduccion'].search([
            ('type', '=', 'arba_percepcion'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])

        # Calcular retenciones
        # TODO: filtrar por compañia y por fecha
        self.iibb_retenciones = self.env['l10n_ar.impuestos.deduccion'].search([
            ('type', '=', 'arba_retencion'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),            
        ])

        # Calcular retenciones bancarias
        # TODO: filtrar por compañia y por fecha
        self.iibb_retenciones_bancarias = self.env['l10n_ar.impuestos.deduccion'].search([
            ('type', '=', 'arba_retencion_bancaria'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])
        
        # Calcular devoluciones bancarias
        self.iibb_devoluciones_bancarias = self.env['l10n_ar.impuestos.deduccion'].search([
            ('type', '=', 'arba_devolucion_bancaria'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])

        saldo_a_favor = self.env['account.move.line'].read_group([
            ('parent_state', '=', 'posted'),
            ('account_id', '=', account_saldo_anterior.id),
        ], ['balance:sum'], ['account_id'])
        saldo_anterior = saldo_a_favor[0]['balance'] if len(saldo_a_favor) > 1 else 0

        # Buscar Facturas de Compras
        in_invoices = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to)
        ])
        print(len(in_invoices), in_invoices)

        # TODO: tener en cuenta las in_refund

        # Buscar Facturas de Ventas
        out_invoices = self.env['account.move'].search([
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to)
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
        self.iibb_report_tax_prev_saldo = -saldo_anterior

        # TODO: obtener deducciones no tomadas del periodo anterior

        # TODO: Permitir "tomarse" o no tomarse deducciones con un widget=boolean_toggle

        # TODO: agregar "intereses al generar el pago"

        self.generate_iibb()

    def _compute_iibb_company_tax_percentage(self):
        for p in self:
            p.iibb_company_tax_percentage = self.env.company.iibb_tax_percentage

    def _compute_iibb_company_min_amount(self):
        for p in self:
            p.iibb_company_min_amount = self.env.company.iibb_min_amount

    @api.depends('iibb_report_sale_total')
    def _compute_iibb_report_tax_subtotal(self):
        for p in self:
            p.iibb_report_tax_subtotal = max(
                p.iibb_report_sale_total * float(p.iibb_company_tax_percentage) / 100,
                p.iibb_company_min_amount
            )

    @api.depends('iibb_percepciones')
    def _compute_iibb_report_percepciones(self):
        for p in self:
            p.iibb_report_percepciones = -sum(p.iibb_percepciones.mapped('amount'))

    @api.depends('iibb_retenciones')
    def _compute_iibb_report_retenciones(self):
        for p in self:
            p.iibb_report_retenciones = -sum(p.iibb_retenciones.mapped('amount'))

    @api.depends('iibb_retenciones_bancarias')
    def _compute_iibb_report_retenciones_bancarias(self):
        for p in self:
            p.iibb_report_retenciones_bancarias = -sum(p.iibb_retenciones_bancarias.mapped('amount'))

    @api.depends('iibb_devoluciones_bancarias')
    def _compute_iibb_report_devoluciones_bancarias(self):
        for p in self:
            p.iibb_report_devoluciones_bancarias = sum(p.iibb_devoluciones_bancarias.mapped('amount'))

    @api.depends('iibb_report_percepciones', 'iibb_report_retenciones', 'iibb_report_retenciones_bancarias', 'iibb_report_devoluciones_bancarias')
    def _compute_iibb_report_deducciones(self):
        for p in self:
            p.iibb_report_deducciones = p.iibb_report_percepciones + p.iibb_report_retenciones + p.iibb_report_retenciones_bancarias + p.iibb_report_devoluciones_bancarias

    @api.depends('iibb_report_tax_subtotal', 'iibb_report_tax_prev_saldo', 'iibb_report_deducciones')
    def _compute_iibb_report_tax_total_saldo(self):
        self.iibb_report_tax_total_saldo = 0
        for p in self:
            saldo = p.iibb_report_tax_subtotal + p.iibb_report_tax_prev_saldo + p.iibb_report_deducciones
            if saldo <= 0:
                p.iibb_report_tax_total_saldo = -saldo

    @api.depends('iibb_report_tax_subtotal', 'iibb_report_tax_prev_saldo', 'iibb_report_deducciones')
    def _compute_iibb_report_tax_total_to_pay(self):
        self.iibb_report_tax_total_to_pay = 0
        for p in self:
            saldo = p.iibb_report_tax_subtotal + p.iibb_report_tax_prev_saldo + p.iibb_report_deducciones
            if saldo > 0:
                p.iibb_report_tax_total_to_pay = saldo