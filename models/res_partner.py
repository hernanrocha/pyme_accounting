# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class Partner(models.Model):
    _inherit = "res.partner"

    # TODO: estos overrides de strings van por codigo. aca no funcionan
    phone = fields.Char(string="Teléfono")
    email = fields.Char(string="E-mail")
    vat = fields.Char(string="CUIT")
    # l10n_ar_afip_responsibility_type_id = fields.Many2one()
    # l10n_ar_gross_income_type = fields.Selection()
    # l10n_ar_gross_income_number = fields.Char()

