# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = "account.move"

    # TODO: esto esta generando siempre TI Z 0004-00001
    # def _get_last_sequence(self, relaxed=False):
    #     print("Getting last sequence in invoice")
    #     # TODO: llamar a super cuando no sean documentos oficiales de AFIP (comprobantes internos)
    #     return []
    commercial_partner_name = fields.Char('Razon Social', 
        related='commercial_partner_id.name', store=True)