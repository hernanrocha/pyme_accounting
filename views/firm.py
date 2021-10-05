# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class ResPartner(models.Model):
    _inherit = "res.company"

    @api.model
    def action_company_activities(self):
        company_partner_ids = self.env['res.company'].search([]).mapped('partner_id').mapped('id')

        return {
            'type': 'ir.actions.act_window',
            'name': 'Actividades',
            'target': 'main',
            'context': self.env.context,
            'view_type': 'activity',
            'view_mode': 'activity',
            'res_model': 'res.partner',
            'domain': [('id', 'in', company_partner_ids)]
        }

    @api.model
    def action_company_calendar(self):
        company_partner_ids = self.env['res.company'].search([]).mapped('partner_id')
        activity_ids = company_partner_ids.activity_ids.mapped('id')
        # _logger(activity_ids)

        # raise UserError("Error interno")

        return {
            'type': 'ir.actions.act_window',
            'name': 'Actividades',
            'target': 'main',
            'context': {
                'default_res_model_id': 1,
            },
            'view_id': self.env.ref('pyme_accounting.view_activities_calendar').id,
            'view_type': 'calendar',
            'view_mode': 'calendar',
            'res_model': 'mail.activity',
            'domain': [('id', 'in', activity_ids)]
        }