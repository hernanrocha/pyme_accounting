# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

# TODO: deprecate this model and move to a new service
class AfipCuitApocrifo(models.Model):
    _name ="l10n_ar.afip.cuit.apocrifo"

    cuit = fields.Char(string="CUIT", index=True) 
    fecha_apocrifo = fields.Date(string="Fecha Apócrifo")
    fecha_publicacion = fields.Date(string="Fecha Publicación")

    # TODO: novedades de cambio de condicion fiscal
    # TODO: "proyectar" monotributo para adelantarse

    @api.model
    def is_apocrifo(self, cuit):
        result = self.env['l10n_ar.afip.cuit.apocrifo'].search([('cuit', '=', cuit)])
        return len(result) > 0

class AfipCuitApocrifoWizard(models.TransientModel):
    _name ="l10n_ar.afip.cuit.apocrifo.wizard"

    state = fields.Selection(selection=[
        ('pending', 'Pendiente'),
        ('found','Apocrifos Encontrados'),
        ('not_found','Apocrifos No Encontrados')
    ], string='Estado', default='pending')

    def _compute_invoice_ids(self):
        for w in self:
            w.invoice_ids = [(5, 0, 0)]

    invoice_ids = fields.One2many(string="Comprobantes", comodel_name="account.move", compute=_compute_invoice_ids)

    def button_find_apocrifos(self):
        m = self.env['account.move'].search([
            ('state', 'in', ['draft', 'posted'])
        ])
        cuits = m.mapped('partner_id.vat')

        # TODO: this line will be moved to a different service
        apocrifos = self.env['l10n_ar.afip.cuit.apocrifo'].search([('cuit', 'in', cuits)])

        if len(apocrifos) > 0:
            self.state = 'found'
            self.invoice_ids = m.filtered(lambda m: m.partner_id.vat in apocrifos.mapped('cuit'))
            
        self.state = 'not_found'
        
        return {
            'title': 'Consulta de CUITs Apócrifos',
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'l10n_ar.afip.cuit.apocrifo.wizard',
            'res_id': self.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }