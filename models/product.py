# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)

class Product(models.Model):
    _inherit = "product.product"

    def _compute(self):
        for m in self:
            m.available_afip_activity_ids = self.company_id.afip_activity_ids
    
    available_afip_activity_ids = fields.One2many('l10n_ar.afip.actividad', compute=_compute)
    afip_activity_id = fields.Many2one('l10n_ar.afip.actividad', index=True, string='Actividad')
