# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = "account.move"
    
    z_desde = fields.Integer(string="Z Cbte Desde")
    z_hasta = fields.Integer(string="Z Cbte Hasta")

    # TODO: esto esta generando siempre TI Z 0004-00001
    # def _get_last_sequence(self, relaxed=False):
    #     print("Getting last sequence in invoice")
    #     # TODO: llamar a super cuando no sean documentos oficiales de AFIP (comprobantes internos)
    #     return []
    commercial_partner_name = fields.Char('Razon Social', 
        related='commercial_partner_id.name', store=True)
    cuit = fields.Char('CUIT', 
        related='commercial_partner_id.vat', store=True)

    display_amount_untaxed = fields.Monetary(string='No Gravado', store=True, readonly=True,
        compute='_compute_display_amount') # inverse='_inverse_amount_total'
    display_amount_tax = fields.Monetary(string='IVA', store=True, readonly=True,
        compute='_compute_display_amount') # inverse='_inverse_amount_total'
    display_amount_total = fields.Monetary(string='Total', store=True, readonly=True,
        compute='_compute_display_amount') # inverse='_inverse_amount_total'

    @api.depends(
        'amount_untaxed',
        'amount_tax',
        'amount_total')
    def _compute_display_amount(self):
        for move in self:
            refund = move.move_type in [ 'in_refund', 'out_refund' ]
            
            move.display_amount_untaxed = -move.amount_untaxed if refund else move.amount_untaxed
            move.display_amount_tax = -move.amount_tax if refund else move.amount_tax
            move.display_amount_total = -move.amount_total if refund else move.amount_total