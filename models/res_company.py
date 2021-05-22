# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class Company(models.Model):
    _inherit = "res.company"

    country_id = fields.Many2one('res.country', default=lambda self: self._default_country_id())
    firm_client = fields.Boolean(string="Cliente del Estudio", default=True)

    phone = fields.Char(related="partner_id.phone")
    email = fields.Char(related="partner_id.email")
    vat = fields.Char(related="partner_id.vat")
    l10n_ar_afip_responsibility_type_id = fields.Many2one(related="partner_id.l10n_ar_afip_responsibility_type_id")
    l10n_ar_gross_income_type = fields.Selection(related="partner_id.l10n_ar_gross_income_type")
    l10n_ar_gross_income_number = fields.Char(related="partner_id.l10n_ar_gross_income_number")
    
    
    def _default_country_id(self):
        country_ar = self.env['res.country'].search([('code', '=', 'AR')])
        return country_ar