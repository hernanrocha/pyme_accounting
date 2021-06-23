# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import base64
import xlrd
import datetime

class PurchaseImportBankBapro(models.TransientModel):
    _inherit = "l10n_ar.import.bank.bapro"
    
    bank = fields.Selection(
        selection_add=[("bna", "Banco Nacion"),('other',)], 
        ondelete={"bna": "set default"}, # TODO: set other
    )

    def parse(self):
        if self.bank == 'bna':
            self.parse_bna()
        super(PurchaseImportBankBapro, self).parse()

    def parse_bna(self):
        raise UserError("El BNA No implementado")