from odoo import api, fields, models, _

import logging
import datetime

_logger = logging.getLogger(__name__)

class ReportBase(models.Model):
    _name = 'report.pyme_accounting.base'

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        readonly=True,
        default=lambda self: self.env['res.company']._company_default_get('account.vat.ledger')
    )
    type = fields.Selection(
        [('sale', 'Venta'), ('purchase', 'Compra')],
        "Type",
        # required=True
    )

    name = fields.Char('Nombre') 
    date_from = fields.Date(string='Fecha Desde', required=True, readonly=True,
        default=lambda self: self._default_date_from(),
        states={'draft': [('readonly', False)]})
    date_to = fields.Date(string='Fecha Hasta', required=True, readonly=True,
        default=lambda self: self._default_date_to(),
        states={'draft': [('readonly', False)]})
    state = fields.Selection(
        [('draft', 'Borrador'), ('presented', 'Presentado'), ('cancel', 'Cancelado')],
        'Estado',
        required=True,
        default='draft'
    )
    note = fields.Html("Notas")

    def _default_date_from(self):
        today = datetime.date.today()
        first = today.replace(day=1)
        last_month_end = first - datetime.timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        return last_month_start

    def _default_date_to(self):
        today = datetime.date.today()
        first = today.replace(day=1)
        last_month_end = first - datetime.timedelta(days=1)
        return last_month_end