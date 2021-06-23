# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import base64
import xlrd
import datetime

class PurchaseImportBankBapro(models.TransientModel):
    _inherit = "l10n_ar.import.bank.bapro"
    
    bank = fields.Selection(
        selection_add=[("hsbc", "Banco HSBC"),('other',)], 
        ondelete={"hsbc": "set default"}, # TODO: set other
    )

    def parse(self):
        if self.bank == 'hsbc':
            self.parse_hsbc()
        super(PurchaseImportBankBapro, self).parse()

    def parse_hsbc(self):
        raise UserError("Banco HSBC no implementado")