# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class AfipCuitApocrifo(models.Model):
    _name ="l10n_ar.afip.cuit.apocrifo"

    cuit = fields.Char(string="CUIT", index=True) 
    fecha_apocrifo = fields.Date(string="Fecha Apocrifo")
    fecha_publicacion = fields.Date(string="Fecha Publicación")

    @api.model
    def is_apocrifo(self, cuit):
        result = self.env['l10n_ar.afip.cuit.apocrifo'].search([('cuit', '=', cuit)])
        return len(result) > 0