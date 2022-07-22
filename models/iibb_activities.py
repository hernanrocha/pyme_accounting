# -*- coding: utf-8 -*-

from odoo import fields, models, _

class IIBBArbaActividad(models.Model):
    _name ="l10n_ar.iibb.arba.actividad"

    code = fields.Char(string="Código", index=True)
    name = fields.Char(string="Nombre", index=True) 
    includes = fields.Char(string="Incluye")
    excludes = fields.Char(string="Excluye")