# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)

# IVA No Corresponde
def novat_line(line):
    codes = line.mapped('tax_ids').mapped('tax_group_id').mapped('l10n_ar_vat_afip_code')
    return '0' in codes

# No Gravado
def untaxed_line(line):
    codes = line.mapped('tax_ids').mapped('tax_group_id').mapped('l10n_ar_vat_afip_code')
    return '1' in codes
    
# Exento
def exempt_line(line):
    codes = line.mapped('tax_ids').mapped('tax_group_id').mapped('l10n_ar_vat_afip_code')
    return '2' in codes

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    display_price_subtotal = fields.Monetary(string="Subtotal", compute="_compute_display_price_subtotal")

    @api.depends('quantity', 'price_unit')
    def _compute_display_price_subtotal(self):
        for line in self:
            line.display_price_subtotal = line.quantity * line.price_unit

class AccountMove(models.Model):
    _inherit = "account.move"
    
    z_desde = fields.Integer(string="Z Cbte Desde")
    z_hasta = fields.Integer(string="Z Cbte Hasta")
    total_afip = fields.Monetary(string="Total AFIP")

    # TODO: esto esta generando siempre TI Z 0004-00001
    # def _get_last_sequence(self, relaxed=False):
    #     print("Getting last sequence in invoice")
    #     # TODO: llamar a super cuando no sean documentos oficiales de AFIP (comprobantes internos)
    #     return []
    commercial_partner_name = fields.Char('Razon Social', 
        related='commercial_partner_id.name', store=True)
    cuit = fields.Char('CUIT', 
        related='commercial_partner_id.vat', store=True)

    amount_total_untaxed = fields.Monetary(string='Total No Gravado', compute='_compute_display_amount')
    amount_total_exempt = fields.Monetary(string='Total Exento', compute='_compute_display_amount')
    display_amount_untaxed = fields.Monetary(string='No Gravado', compute='_compute_display_amount') # inverse='_inverse_amount_total'
    display_amount_exempt = fields.Monetary(string='Exento', compute='_compute_display_amount')
    display_amount_total = fields.Monetary(string='Total', compute='_compute_display_amount')

    perc_nacionales = fields.Monetary(string='Perc. Nacionales', readonly=True, compute='_compute_percepciones')
    perc_internos = fields.Monetary(string='Imp. Internos', readonly=True, compute='_compute_percepciones')
    perc_iva = fields.Monetary(string='Perc. IVA', readonly=True, compute='_compute_percepciones')
    perc_iibb = fields.Monetary(string='Perc. IIBB', readonly=True, compute='_compute_percepciones')
    perc_municipales = fields.Monetary(string='Perc. Municipales', readonly=True, compute='_compute_percepciones')
    perc_total = fields.Monetary(string='Perc. Total', readonly=True, compute='_compute_percepciones')

    amount_tax_21 = fields.Monetary(string='IVA 21%', compute='_compute_display_tax')
    amount_tax_10 = fields.Monetary(string='IVA 10.5%', compute='_compute_display_tax')
    amount_tax_27 = fields.Monetary(string='IVA 27%', compute='_compute_display_tax')
    amount_tax_5 = fields.Monetary(string='IVA 5%', compute='_compute_display_tax')
    amount_tax_25 = fields.Monetary(string='IVA 2.5%', compute='_compute_display_tax')
    amount_total_tax = fields.Monetary(string='Total IVA', compute='_compute_display_tax')
    
    amount_taxed_21 = fields.Monetary(string='Gravado 21%', compute='_compute_display_tax')
    amount_taxed_10 = fields.Monetary(string='Gravado 10.5%', compute='_compute_display_tax')
    amount_taxed_27 = fields.Monetary(string='Gravado 27%', compute='_compute_display_tax')
    amount_taxed_5 = fields.Monetary(string='Gravado 5%', compute='_compute_display_tax')
    amount_taxed_25 = fields.Monetary(string='Gravado 2.5%', compute='_compute_display_tax')
    amount_total_taxed = fields.Monetary(string='Total Gravado', compute='_compute_display_tax')

    display_amount_taxed = fields.Monetary(string='Gravado', compute='_compute_display_tax')
    display_amount_tax_21 = fields.Monetary(string='IVA 21%', compute='_compute_display_tax')
    display_amount_tax_10 = fields.Monetary(string='IVA 10.5%', compute='_compute_display_tax')
    display_amount_tax_27 = fields.Monetary(string='IVA 27%', compute='_compute_display_tax')
    display_amount_tax_5 = fields.Monetary(string='IVA 5%', compute='_compute_display_tax')
    display_amount_tax_25 = fields.Monetary(string='IVA 2.5%', compute='_compute_display_tax')
    display_perc_nacionales = fields.Monetary(string='Perc. Nacionales', compute='_compute_percepciones')
    display_perc_internos = fields.Monetary(string='Imp. Internos', compute='_compute_percepciones')
    display_perc_iva = fields.Monetary(string='Perc. IVA', compute='_compute_percepciones')
    display_perc_iibb = fields.Monetary(string='Perc. IIBB', compute='_compute_percepciones')
    display_perc_municipales = fields.Monetary(string='Perc. Municipales', compute='_compute_percepciones')

    @api.model
    def create_batch(self, data):
        records = []
        for record in data:
            move = self.create(dict(record))

            # Recalculate totals
            move._recompute_dynamic_lines(recompute_all_taxes=True, recompute_tax_base_amount=True)
            move._recompute_payment_terms_lines()
            move._compute_amount()

            records.append(move.id)
        return records

    @api.depends('l10n_latam_document_type_id')
    def _compute_display_z_desde_hasta(self):
        for move in self:
            move.display_z_desde_hasta = move.l10n_latam_document_type_id.code in ['83']

    display_z_desde_hasta = fields.Boolean(compute=_compute_display_z_desde_hasta)

    # Al agrupar los comprobantes, si se quiere mostrar el total de un campo computed,
    # se debe calcular manualmente. La alternativa es setear store=True en el campo
    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        res = super(AccountMove, self).read_group(domain, fields, groupby, offset=offset, limit=limit, orderby=orderby, lazy=lazy)
        
        # Todos los campos computed se van a pedir juntos, y el IVA 21% aparece siempre
        # TODO: generalizar esto para todos los computed
        if 'display_amount_tax_21' in fields:
            for line in res:
                if '__domain' in line:
                    lines = self.search(line['__domain'])

                    line['display_amount_untaxed'] = sum(lines.mapped('display_amount_untaxed'))
                    line['display_amount_exempt'] = sum(lines.mapped('display_amount_exempt'))
                    line['display_amount_taxed'] = sum(lines.mapped('display_amount_taxed'))
                    line['display_amount_total'] = sum(lines.mapped('display_amount_total'))
                    
                    line['display_amount_tax_21'] = sum(lines.mapped('display_amount_tax_21'))
                    line['display_amount_tax_10'] = sum(lines.mapped('display_amount_tax_10'))
                    line['display_amount_tax_27'] = sum(lines.mapped('display_amount_tax_27'))
                    line['display_amount_tax_5'] = sum(lines.mapped('display_amount_tax_5'))
                    line['display_amount_tax_25'] = sum(lines.mapped('display_amount_tax_25'))

                    line['display_perc_nacionales'] = sum(lines.mapped('display_perc_nacionales'))
                    line['display_perc_municipales'] = sum(lines.mapped('display_perc_municipales'))
                    line['display_perc_internos'] = sum(lines.mapped('display_perc_internos'))
                    line['display_perc_iva'] = sum(lines.mapped('display_perc_iva'))
                    line['display_perc_iibb'] = sum(lines.mapped('display_perc_iibb'))

        return res

    @api.depends('amount_untaxed', 'amount_tax', 'amount_total')
    def _compute_display_amount(self):
        for move in self:
            sign = -1 if move.move_type in [ 'in_refund', 'out_refund' ] else 1

            untaxed = sum(move.invoice_line_ids.filtered(untaxed_line).mapped('price_total'))
            novat = sum(move.invoice_line_ids.filtered(novat_line).mapped('price_total'))

            move.amount_total_untaxed = untaxed + novat
            move.amount_total_exempt = sum(move.invoice_line_ids.filtered(exempt_line).mapped('price_total'))

            move.display_amount_untaxed = sign * move.amount_total_untaxed
            move.display_amount_exempt = sign * move.amount_total_exempt
            move.display_amount_total = sign * move.amount_total
    
    @api.depends('amount_untaxed', 'amount_tax', 'amount_total')
    def _compute_display_tax(self):
        for move in self:
            sign = -1 if move.move_type in [ 'in_refund', 'out_refund' ] else 1

            # Obtener todas las lineas de IVA
            # - Filtrar las lineas de impuestos de tipo 'IVA' con codigo conocido
            # - Los montos Exentos, No Gravados y Gravados al 0% no generan 
            # linea de movimiento extra
            vat_taxes = move.line_ids.filtered(
                # (1) No Gravado
                # (2) Exento 
                # (3) 0%
                # (4) 10.5%
                # (5) 21%
                # (6) 27%
                # (8) 5%
                # (9) 2.5%
                lambda l: l.tax_group_id and 
                l.tax_group_id.l10n_ar_vat_afip_code in ['4', '5', '6', '8', '9']
            )

            # Lineas contables relacionadas con el IVA
            taxes_10 = vat_taxes.filtered(lambda x: x.tax_group_id.l10n_ar_vat_afip_code == '4')
            taxes_21 = vat_taxes.filtered(lambda x: x.tax_group_id.l10n_ar_vat_afip_code == '5')
            taxes_27 = vat_taxes.filtered(lambda x: x.tax_group_id.l10n_ar_vat_afip_code == '6')
            taxes_5 = vat_taxes.filtered(lambda x: x.tax_group_id.l10n_ar_vat_afip_code == '8')
            taxes_25 = vat_taxes.filtered(lambda x: x.tax_group_id.l10n_ar_vat_afip_code == '9')

            # Sumar para obtener el monto de cada IVA
            move.amount_tax_10 = sum(taxes_10.mapped('price_subtotal'))
            move.amount_tax_21 = sum(taxes_21.mapped('price_subtotal'))
            move.amount_tax_27 = sum(taxes_27.mapped('price_subtotal'))
            move.amount_tax_5 = sum(taxes_5.mapped('price_subtotal'))
            move.amount_tax_25 = sum(taxes_25.mapped('price_subtotal'))
            move.amount_total_tax = move.amount_tax_10 + \
                move.amount_tax_21 + move.amount_tax_27 + \
                move.amount_tax_5 +  move.amount_tax_25

            # Sumar para obtener el monto gravado por cada IVA
            move.amount_taxed_10 = sum(taxes_10.mapped('tax_base_amount'))
            move.amount_taxed_21 = sum(taxes_21.mapped('tax_base_amount'))
            move.amount_taxed_27 = sum(taxes_27.mapped('tax_base_amount'))
            move.amount_taxed_5 = sum(taxes_5.mapped('tax_base_amount'))
            move.amount_taxed_25 = sum(taxes_25.mapped('tax_base_amount'))
            move.amount_total_taxed = move.amount_taxed_10 + \
                move.amount_taxed_21 + move.amount_taxed_27 + \
                move.amount_taxed_5 +  move.amount_taxed_25

            # Para las NC, mostrar con signo negativo
            # El valor positivo se utiliza para IVA digital y otras DDJJ
            move.display_amount_tax_10 = sign * move.amount_tax_10
            move.display_amount_tax_21 = sign * move.amount_tax_21
            move.display_amount_tax_27 = sign * move.amount_tax_27
            move.display_amount_tax_5 = sign * move.amount_tax_5
            move.display_amount_tax_25 = sign * move.amount_tax_25
            
            move.display_amount_taxed = sign * move.amount_total_taxed

    @api.depends('amount_untaxed', 'amount_tax', 'amount_total')
    def _compute_percepciones(self):
        for move in self:
            sign = -1 if move.move_type in [ 'in_refund', 'out_refund' ] else 1

            move.perc_nacionales = move._get_percepcion('01')
            move.perc_municipales = move._get_percepcion('03')
            move.perc_internos = move._get_percepcion('04')
            move.perc_iva = move._get_percepcion('06')
            move.perc_iibb = move._get_percepcion('07')
            move.perc_total = move.perc_nacionales + move.perc_municipales + \
                move.perc_internos + move.perc_iva + move.perc_iibb
            # TODO: Otros tributos

            move.display_perc_nacionales = sign * move.perc_nacionales
            move.display_perc_municipales = sign * move.perc_municipales
            move.display_perc_internos = sign * move.perc_internos
            move.display_perc_iva = sign * move.perc_iva
            move.display_perc_iibb = sign * move.perc_iibb
            # TODO: Otros tributos

    # '01': Nacionales
    # '03': Municipales
    # '04': Internos
    # '06': IVA
    # '07': IIBB
    def _get_percepcion(self, code):
        perc = self.line_ids.filtered(lambda r: (
            r.tax_group_id and r.tax_group_id.l10n_ar_tribute_afip_code == code))
        
        return sum(perc.mapped('price_total'))