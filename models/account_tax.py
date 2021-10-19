# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)

class AccountTax(models.Model):
    _inherit = "account.tax"
    
    l10n_ar_tribute_afip_code = fields.Selection([
        ('01', '01 - National Taxes'),
        ('02', '02 - Provincial Taxes'),
        ('03', '03 - Municipal Taxes'),
        ('04', '04 - Internal Taxes'),
        ('06', '06 - VAT perception'),
        ('07', '07 - IIBB perception'),
        ('08', '08 - Municipal Taxes Perceptions'),
        ('09', '09 - Other Perceptions'),
        ('99', '99 - Others'),
    ], string='Código AFIP IVA Digital', related="tax_group_id.l10n_ar_tribute_afip_code")
    
    # values from http://www.afip.gob.ar/fe/documentos/OperacionCondicionIVA.xls
    l10n_ar_vat_afip_code = fields.Selection([
        ('0', 'Not Applicable'),
        ('1', 'Untaxed'),
        ('2', 'Exempt'),
        ('3', '0%'),
        ('4', '10.5%'),
        ('5', '21%'),
        ('6', '27%'),
        ('8', '5%'),
        ('9', '2,5%'),
    ], string='Código AFIP', related="tax_group_id.l10n_ar_vat_afip_code")
