# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class AfipActividad(models.Model):
    _name ="l10n_ar.afip.actividad"

    code = fields.Char(string="Código", index=True)
    name = fields.Char(string="Nombre", index=True) 
    description = fields.Char(string="Descripción")