# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class ArbaRetencion(models.Model):
    _name = "l10n_ar.arba.retencion"

    date = fields.Date(string="Fecha")
    amount = fields.Float(string="Monto")


class ArbaRetencionBancaria(models.Model):
    _name = "l10n_ar.arba.retencion_bancaria"

    date = fields.Date(string="Fecha")
    amount = fields.Float(string="Monto")

class ArbaDevolucionBancaria(models.Model):
    _name = "l10n_ar.arba.devolucion_bancaria"

    date = fields.Date(string="Fecha")
    amount = fields.Float(string="Monto")
