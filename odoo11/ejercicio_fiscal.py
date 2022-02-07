from odoo import fields, models, _
import logging

_logger = logging.getLogger(__name__)

class EjercicioFiscal(models.Model):
    _inherit = "date.range"

    status = fields.Selection(selection=[
        ('open', 'Abierto'),
        ('closed', 'Cerrado')
    ], required=True, default="open", string="Estado")

    open_move_id = fields.Many2one('account.move', string="Asiento de Apertura")
    adjust_move_ids = fields.Many2many('account.move', string="Asientos de Ajuste Mensuales")
    refundicion_move_id = fields.Many2one('account.move', string="Asiento de Refundición de Resultados")
    closure_move_id = fields.Many2one('account.move', string="Asiento de Cierre")

    # CONFIGURACION
    refundicion_account_id = fields.Many2one('account.account', 
        required=True, string="Cuenta de Refundición de Resultados")
    journal_id = fields.Many2one('account.journal', string="Diario",
        domain=[('type', '=', 'general')], required=True)
    last_closure_move_id = fields.Many2one('account.move', 
        required=True, string="Asiento de Cierre del Ejercicio Anterior")

    # TODO: agregar cuentas de refundicion y recpam al plan contable

    def generar_apertura(self):
        # Para generar el asiento de apertura, se debe generar 
        # un asiento de reversión del asiento de cierre del ejercicio fiscal anterior
        self.open_move_id = self.last_closure_move_id.reverse_moves(
            self.date_start, self.journal_id)

    def generar_refundicion(self):
        # TODO: borrar asientos viejos
        # self.refundicion_move_id = False

        # Sacar los valores del reporte de sumas y saldos
        # account_financial_report/wizard/trial_balance_wizard.py
        # def _export()

        # lines = self.env['account.move.line'].search([])
        
        lines = []
        # adjustment = self.company_id.currency_id.round(adjustment)
        account_ids = self.env['account.account'].search([
            ('id', 'in', [2, 92])
        ])

        # Poner a 0 todas las cuentas de resultados
        total_adjustment = 0
        for account_id in account_ids:
            adjustment = 10 # TODO
            lines.append({
                'account_id': account_id.id, # line.get('account_id')[0],
                'name': 'Refundición de Resultados {}'.format(self.date_end),
                'date_maturity': self.date_end,
                'debit' if adjustment > 0 else 'credit': abs(adjustment)
            })
            total_adjustment += adjustment

        # Generar contrapartida
        lines.append({
            'account_id': self.refundicion_account_id.id, # line.get('account_id')[0],
            'name': 'Refundición de Resultados {}'.format(self.date_end),
            'date_maturity': self.date_end,
            'credit' if total_adjustment > 0 else 'debit': abs(total_adjustment)
        })

        # Crear Asiento de Refundicion de Resultados
        self.refundicion_move_id = self.env['account.move'].create({
            'journal_id': self.journal_id.id,
            'date': self.date_end,
            'ref': 'Refundición de Resultados {}'.format(self.date_end),
            'line_ids': [(0, 0, line_data) for line_data in lines],
        })