# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class Company(models.Model):
    _inherit = "res.company"

    country_id = fields.Many2one('res.country', default=lambda self: self._default_country_id())

    phone = fields.Char(related="partner_id.phone")
    email = fields.Char(related="partner_id.email")
    vat = fields.Char(related="partner_id.vat")
    l10n_ar_afip_responsibility_type_id = fields.Many2one(related="partner_id.l10n_ar_afip_responsibility_type_id")
    l10n_ar_gross_income_type = fields.Selection(related="partner_id.l10n_ar_gross_income_type")
    l10n_ar_gross_income_number = fields.Char(related="partner_id.l10n_ar_gross_income_number")

    monotributo_category = fields.Selection([
        ('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D'), ('E', 'E'), 
        ('F', 'F'), ('G', 'G'), ('H', 'H'), ('I', 'I'), ('J', 'J'), ('K', 'K')
    ], string="Categoria")
    monotributo_type = fields.Selection([('good', 'Bienes'), ('service', 'Servicios')])    
    
    def _default_country_id(self):
        country_ar = self.env['res.country'].search([('code', '=', 'AR')])
        return country_ar

    @api.model
    def create(self, vals):
        print("Creando compañia")
        c = super(Company, self).create(vals)
        print("Compañia creada", c)

        # chart_template_id = self.sudo().env.ref('l10n_ar.l10nar_ri_chart_template')
        # print("Template RI", chart_template_id)

        # # Agregar compañia
        # print("User", self.env.user)
        # print("Compañia", self.env.user.company_ids)
        # self.env.user.write({
        #     'company_ids': [(4, c.id, 0)]
        # })
        # print("Compañia", self.env.user.company_ids)

        # # Solo los admins pueden cargar el plan de cuentas
        # print("ADMIN", self.sudo().env.user)
        # admin_user = self.env['res.users'].with_user(2).search([('id', '=', 2)])
        # print("ADMIN", admin_user)
        # admin_user.write({
        #     'company_ids': [(4, c.id, 0)]
        # })
        # chart_template_id.with_user(2).with_company(c.id)._load(15.0, 15.0, c)
        # print("Plan de cuentas creado")

        # Obtener plan de cuenta Resp. Inscripto
        chart_template_id = self.env.ref('l10n_ar.l10nar_ri_chart_template')
        print("Template RI", chart_template_id)

        # Agregar compañia al usuario
        self.env.user.write({
            'company_ids': [(4, c.id, 0)]
        })

        # Agregar compañia al admin
        # TODO: Importar SUPERUSER_ID
        admin_user = self.env['res.users'].with_user(2).search([('id', '=', 2)])
        admin_user.write({
            'company_ids': [(4, c.id, 0)]
        })

        # Solo los admins pueden cargar el plan de cuentas
        chart_template_id.sudo()._load(15.0, 15.0, c)
        print("Plan de cuentas creado")

        return c