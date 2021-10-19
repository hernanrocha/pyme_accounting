from odoo import api, fields, models, _
from odoo.exceptions import UserError

import logging

_logger = logging.getLogger(__name__)

class AccountJournal(models.Model):
    _inherit = "account.journal"

    # TODO: configurar esto al crearlo (y usar esto para default value)
    def _compute_afip_type(self):
        for journal in self:
            if journal.type == 'purchase':
                journal.afip_type = 'purchase'
            elif journal.type == 'sale' and journal.name.find('Comprobantes Emitidos') != -1:
                journal.afip_type = 'sale_emitidos'
            elif journal.type == 'sale' and journal.name.find('Controlador Fiscal') != -1:
                journal.afip_type = 'sale_pem'
            else:
                journal.afip_type = 'other'

    afip_type = fields.Selection(
        [
            ('purchase', 'Compras'), 
            ('sale_emitidos', 'Comprobantes En Linea'), 
            ('sale_pem', 'Controlador Fiscal'),
            ('other', 'Otros')
        ],
        'Tipo de Diario AFIP',
        compute=_compute_afip_type)

    # override title action
    def open_action(self):
        s = super(AccountJournal, self).open_action()
        _logger.info(s)

        # action = self.env["ir.actions.act_window"]._for_xml_id('pyme_accounting.id')
        ctx = self._context.copy()
        return {
            'name': 'Ventas',
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            # 'target': 'new',
            # 'view_id': self.env.ref('account.view_move_form').id,
            'context': ctx,
        }

    def action_import_pem(self):
        ctx = self._context.copy()

        # ctx['default_journal_id'] = self.id
        # if self.type == 'sale':
        #     ctx['default_move_type'] = 'out_refund' if ctx.get('refund') else 'out_invoice'
        # elif self.type == 'purchase':
        #     ctx['default_move_type'] = 'in_refund' if ctx.get('refund') else 'in_invoice'
        # else:
        #     ctx['default_move_type'] = 'entry'
        #     ctx['view_no_maturity'] = True

        return {
            'name': 'Importar Ventas de Controlador Fiscal',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'l10n_ar.import.sale.pem',
            'target': 'new',
            # 'view_id': self.env.ref('account.view_move_form').id,
            'context': ctx,
        }

    def action_import_comp_emitidos(self):
        ctx = self._context.copy()

        return {
            'name': 'Importar Comprobantes Emitidos',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'l10n_ar.afip.import_sale',
            'target': 'new',
            # 'view_id': self.env.ref('account.view_move_form').id,
            'context': ctx,
        }

    def action_import_comp_recibidos(self):
        ctx = self._context.copy()

        return {
            'name': 'Importar Comprobantes Recibidos',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'l10n_ar.import.purchase.comprecibidos',
            'target': 'new',
            'context': ctx,
        }