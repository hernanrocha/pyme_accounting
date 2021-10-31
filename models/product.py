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
    
    # Actividad AFIP para ventas
    available_afip_activity_ids = fields.One2many('l10n_ar.afip.actividad', compute=_compute)
    afip_activity_id = fields.Many2one('l10n_ar.afip.actividad', index=True, string='Actividad')

    # Categoria de compras en F. 2002
    afip_f2002_category = fields.Selection(selection=[
        ('bienes','Compra de Bienes'),
        ('locaciones','Locaciones'),
        ('servicios','Prestaciones de Servicio'),
        # ('inversiones_bienes', 'Inversiones en Bienes de uso'),
        # ('bienes_usados', 'Compra de Bienes Usados a CF'),
        # ('turiva', 'TurIVA'),
        # ('otros_conceptos', 'Otros Conceptos'),
    ], string='Categoría Formulario IVA 2002')

    # def create(self):
    #     p = self.env['product.product'].create({
    #         'company_id': self.company_id,
    #         'name': 'CIGARRILLOS',
    #         'type': 'consu', # consu / service
    #         # Ventas
    #         'sale_ok': True,
    #         'afip_activity_id': self.company_id.afip_activity_ids[0] if self.company_id.afip_activity_ids else False,
    #         'taxes_id': [(5,0,0)],
    #         # Compras
    #         'purchase_ok': False,
    #         'supplier_taxes_ids': [(5,0,0)],
    #     })