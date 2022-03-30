# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

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
    iibb_report_tax_subtotal = fields.Float(string="Impuesto Determinado")
    
    # Calculo de deducciones
    iibb_report_percepciones = fields.Float(string="Percepciones")
    iibb_report_retenciones = fields.Float(string="Retenciones")
    iibb_report_retenciones_bancarias = fields.Float(string="Retenciones Bancarias")
    iibb_report_devoluciones_bancarias = fields.Float(string="Devoluciones Bancarias")
    iibb_report_deducciones = fields.Float(string="Total Deducciones")

    # Saldo a favor / a pagar
    iibb_report_tax_prev_saldo = fields.Float(string="Saldo a favor del periodo anterior")
    iibb_report_tax_total_saldo = fields.Float(string="Saldo a favor del período")
    iibb_report_tax_total_to_pay = fields.Float(string="Saldo a pagar")

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
        string="Asiento de IIBB", ondelete="cascade")
    line_ids = fields.One2many('account.move.line', related="move_id.line_ids")
    move_id_state = fields.Selection(related="move_id.state")
    
    payment_move_id = fields.Many2one(comodel_name="account.move",
        string="Asiento de Pago", ondelete="cascade")
    payment_line_ids = fields.One2many('account.move.line', related="payment_move_id.line_ids")
    payment_move_id_state = fields.Selection(related="payment_move_id.state")

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
        account_saldo_anterior = self.env['account.account'].search([
            # TODO: hacer dependiente de la compañia
            ('company_id', '=', self.env.company.id),
            ('name', '=', 'Saldo a favor IIBB Buenos Aires')
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

        # Buscar Facturas de Compras
        in_invoices = self.env['account.move'].search([
            ('company_id', '=', self.env.company.id),
            ('move_type', '=', 'in_invoice'),
            ('state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to)
        ])
        print(len(in_invoices), in_invoices)

        # Buscar Facturas de Ventas
        out_invoices = self.env['account.move'].search([
            ('company_id', '=', self.env.company.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to)
        ])
        print(len(out_invoices), out_invoices)

        # Buscar Notas de Credito de Ventas
        out_refunds = self.env['account.move'].search([
            ('move_type', '=', 'out_refund'),
            ('state', '=', 'posted'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to)
        ])

        # Ventas
        ventas = 0
        for invoice in out_invoices:
            ventas += invoice.amount_total

        # NC
        for invoice in out_refunds:
            ventas += invoice.amount_total
        
        self.iibb_report_sale_total = ventas

        deducciones = 0
        for invoice in in_invoices:
            deducciones += invoice.arba_iibb
        # TODO poner negativo?
        self.iibb_report_deducciones = -deducciones

        # TODO: calcular saldo del periodo anterior
        self.iibb_report_tax_prev_saldo = -sum(self.env['account.move.line'].search([
            ('parent_state', '=', 'posted'),
            ('account_id', '=', account_saldo_anterior.id),
        ]).mapped('balance'))

        # TODO: obtener deducciones no tomadas del periodo anterior

        # TODO: Permitir "tomarse" o no tomarse deducciones con un widget=boolean_toggle

        # TODO: agregar "intereses al generar el pago"

        # Generacion de subtotales
        self.iibb_report_tax_subtotal = max(
            self.iibb_report_sale_total * float(self.iibb_company_tax_percentage) / 100,
            self.iibb_company_min_amount
        )

        self.iibb_report_percepciones = -sum(self.iibb_percepciones.mapped('amount'))
        self.iibb_report_retenciones = -sum(self.iibb_retenciones.mapped('amount'))
        self.iibb_report_retenciones_bancarias = -sum(self.iibb_retenciones_bancarias.mapped('amount'))
        self.iibb_report_devoluciones_bancarias = sum(self.iibb_devoluciones_bancarias.mapped('amount'))
        self.iibb_report_deducciones = self.iibb_report_percepciones + self.iibb_report_retenciones + self.iibb_report_retenciones_bancarias + self.iibb_report_devoluciones_bancarias

        self.iibb_report_tax_total_saldo = 0
        self.iibb_report_tax_total_to_pay = 0
        saldo = self.iibb_report_tax_subtotal + self.iibb_report_tax_prev_saldo + self.iibb_report_deducciones
        if saldo <= 0:
            self.iibb_report_tax_total_saldo = -saldo
        else:
            self.iibb_report_tax_total_to_pay = saldo

        self._compute_move_id()

    def button_present(self):
        self.calculate_iibb()
        super(IngresosBrutosArbaWizard, self).button_present()
        self.move_id.action_post()

    def button_pay(self):
        super(IngresosBrutosArbaWizard, self).button_pay()
        self.payment_move_id.action_post()

    def button_cancel(self):
        if self.state == 'paid':
            self.payment_move_id.button_draft()
        
        if self.state in ['presented', 'paid']:
            self.move_id.button_draft()

        self.payment_move_id.button_cancel()
        self.move_id.button_cancel()        
        super(IngresosBrutosArbaWizard, self).button_cancel()

    def _compute_iibb_company_tax_percentage(self):
        for p in self:
            p.iibb_company_tax_percentage = self.env.company.iibb_tax_percentage

    def _compute_iibb_company_min_amount(self):
        for p in self:
            p.iibb_company_min_amount = self.env.company.iibb_min_amount
    
    def _compute_move_id(self):
        # TODO: Mostrar una seccion con las facturas en borrador

        journal_taxes = self.env['account.journal'].search([
            ('company_id', '=', self.env.company.id),
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
            ('company_id', '=', self.env.company.id),
            ('name', '=', 'IIBB ARBA')
        ])
        account_percepciones = self.env['account.account'].search([
            ('company_id', '=', self.env.company.id),
            ('name', '=', 'Percepción IIBB Buenos Aires sufrida')
        ])
        account_saldo_a_favor = self.env['account.account'].search([
            ('company_id', '=', self.env.company.id),
            ('name', '=', 'Saldo a favor IIBB Buenos Aires')
        ])
        account_a_pagar = self.env['account.account'].search([
            ('company_id', '=', self.env.company.id),
            ('name', '=', 'IIBB a pagar')
        ])
        # TODO: permitir pagar en efectivo / banco
        account_efectivo = self.env['account.account'].search([
            ('company_id', '=', self.env.company.id),
            ('code', '=', '1.1.1.01.001')   # Efectivo
        ])
        _logger.info("Cuentas: {} - {} - {}".format(account_iibb, account_percepciones, account_saldo_a_favor))

        # TODO: crear asiento a pagar
        if not self.move_id:
            self.move_id = self.env['account.move'].create({
                'state': 'draft',
                'ref': 'Devengación de IIBB',
                'date': self.date_to,
                'journal_id': journal_taxes.id
            })
        else:
            self.move_id.write({ 
                'date': self.date_to 
            })

        if not self.payment_move_id:
            self.payment_move_id = self.env['account.move'].create({
                'state': 'draft',
                'ref': 'Pago de IIBB',
                'date': self.date_to,
                'journal_id': journal_taxes.id
            })
        else:
            self.payment_move_id.write({ 
                'date': self.date_to 
            })

        line_ids = []

        # Impuesto IIBB
        line_ids.append((0, 0, { 
            'account_id': account_iibb.id, 
            'name': 'IIBB ARBA',
            'debit': self.iibb_report_tax_subtotal 
        }))

        # Deducciones
        if self.iibb_report_percepciones != 0:
            line_ids.append((0, 0, { 
                'account_id': account_percepciones.id, 
                'name': 'Percepciones ARBA',
                'credit': -self.iibb_report_percepciones 
            }))
        if self.iibb_report_retenciones != 0:
            line_ids.append((0, 0, { 
                'account_id': account_percepciones.id, 
                'name': 'Retenciones ARBA',
                'credit': -self.iibb_report_retenciones 
            }))
        if self.iibb_report_retenciones_bancarias != 0:
            line_ids.append((0, 0, { 
                'account_id': account_percepciones.id, 
                'name': 'Retención Bancarias ARBA',
                'credit': -self.iibb_report_retenciones_bancarias 
            }))
        if self.iibb_report_devoluciones_bancarias != 0:
            line_ids.append((0, 0, { 
                'account_id': account_percepciones.id, 
                'name': 'Devoluciones Bancarias ARBA',
                'debit': self.iibb_report_devoluciones_bancarias 
            }))

        # Saldo "A Favor" periodo anterior
        if self.iibb_report_tax_prev_saldo != 0:
            line_ids.append((0, 0, { 
                'account_id': account_saldo_a_favor.id,
                'name': 'Saldo a favor Periodo Anterior', 
                'credit': -self.iibb_report_tax_prev_saldo 
            }))

        # Saldo "A Pagar" o "A Favor"
        if self.iibb_report_tax_total_to_pay > 0:
            # Saldo a pagar
            line_ids.append((0, 0, { 
                'account_id': account_a_pagar.id, 
                'name': 'IIBB ARBA a Pagar',
                'credit': self.iibb_report_tax_total_to_pay
            }))
        else:
            # Saldo a favor del periodo
            line_ids.append((0, 0, { 
                'account_id': account_saldo_a_favor.id, 
                'name': 'IIBB ARBA a Favor',
                'debit': self.iibb_report_tax_total_saldo
            }))

        # Asiento de IIBB
        self.move_id.line_ids = [(5,0,0)]
        self.move_id.write({ 'line_ids': line_ids })

        # Asiento de Pago
        self.payment_move_id.line_ids = [(5,0,0)]
        
        if self.iibb_report_tax_total_to_pay > 0:
            self.payment_move_id.write({ 'line_ids': [
                (0, 0, { 
                    'account_id': account_iibb.id,
                    'debit': self.iibb_report_tax_total_to_pay
                }),
                (0, 0, { 
                    'account_id': account_efectivo.id,
                    'credit': self.iibb_report_tax_total_to_pay
                })
            ] })
