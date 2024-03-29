# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError

import requests
import logging

_logger = logging.getLogger(__name__)

class Company(models.Model):
    _inherit = "res.company"

    country_id = fields.Many2one('res.country', default=lambda self: self._default_country_id())

    phone = fields.Char(related="partner_id.phone")
    email = fields.Char(related="partner_id.email")
    vat = fields.Char(related="partner_id.vat")
    tipo_persona = fields.Selection([('fisica', 'Física'), ('juridica', 'Jurídica')],
        string="Tipo de Persona")

    # TODO: guardar este valor en el invoice por si cambia la condicion fiscal
    l10n_ar_afip_responsibility_type_id = fields.Many2one(related="partner_id.l10n_ar_afip_responsibility_type_id")
    l10n_ar_gross_income_type = fields.Selection(related="partner_id.l10n_ar_gross_income_type")
    l10n_ar_gross_income_number = fields.Char(related="partner_id.l10n_ar_gross_income_number")

    # TODO: se puede cambiar de monotributo a responsable inscripto en cualquier momento
    # Error: "No se puede cambiar la responsabilidad AFIP de esta compañía porque ya existen movimientos contables."
    # TODO: de RI a monotributo solo se puede cambiar despues de 3 años calendario
    # (01/01 dentro de mas de 3 años)

    # Monotributo
    monotributo_category = fields.Selection([
        ('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D'), ('E', 'E'), 
        ('F', 'F'), ('G', 'G'), ('H', 'H'), ('I', 'I'), ('J', 'J'), ('K', 'K')
    ], string="Categoria")
    monotributo_type = fields.Selection([('good', 'Bienes'), ('service', 'Servicios')])
    monotributo_social = fields.Boolean(string="Monotributo Social", default=False)
    monotributo_paga_impositivo = fields.Boolean(string="Paga Componente Impositivo", default=True)
    monotributo_paga_sipa = fields.Boolean(string="Paga SIPA", default=True)
    monotributo_paga_obra_social = fields.Boolean(string="Paga Obra Social", default=True)
    monotributo_adherentes = fields.Integer(string="Cantidad Adherentes")

    @api.depends(
        'monotributo_category',
        'monotributo_type',
        'monotributo_social', 
        'monotributo_paga_obra_social',
        'monotributo_paga_impositivo', 
        'monotributo_paga_sipa', 
        'monotributo_adherentes')
    def _compute_monotributo_pago(self):
        # https://monotributo.afip.gob.ar/public/ayuda/Alta/Paso1.aspx
        # Social: obra_social / 2
        # Servicios: servicios + sipa + obra_social
        # Muebles: muebles + sipa + obra_social
        for c in self:
            if c.monotributo_social:
                cat = self.env["nano.monotributo.categoria"].search([
                    ('name', '=', c.monotributo_category)
                ])
                c.monotributo_pago = cat.monto_obra_social / 2
                continue

            cat = self.env["nano.monotributo.categoria"].search([
                ('name', '=', c.monotributo_category)
            ])

            pago = 0
            if c.monotributo_paga_impositivo:
                pago += cat.monto_servicios if c.monotributo_type else cat.monto_bienes
            if c.monotributo_paga_sipa:
                pago += cat.monto_sipa
            if c.monotributo_paga_obra_social:
                pago += cat.monto_obra_social
            if c.monotributo_adherentes:
                pago += c.monotributo_adherentes * cat.monto_obra_social
            c.monotributo_pago = pago

    monotributo_pago = fields.Float(string="Pago", compute=_compute_monotributo_pago)

    # AFIP
    afip_activity_ids = fields.Many2many('l10n_ar.afip.actividad', string='Actividades AFIP', help="La primera actividad de la lista debe ser la actividad principal")

    # IIBB
    iibb_tax_percentage = fields.Float(string="Alícuota (%)", default=1.50)
    iibb_min_amount = fields.Float(string="Impuesto Mínimo", default=0)
    # Nomenclador en ARBA: NAIIB-18
    # - http://www.arba.gov.ar/archivos/Publicaciones/naiib18.pdf
    # - https://www.arba.gov.ar/Informacion/InfoGeneral/Naiib18/naiib.asp?lugar=E&apartado=IIBB
    # Reporte de Ventas:
    # Actividad  | Gravado | Alicuota IVA | IVA | Total 
    # 000001     |     XXX |          21% | XXX |   XXX 
    # 000001     |     XXX |          27% | XXX |   XXX 
    # 000002     |     XXX |          21% | XXX |   XXX 
    #            |     XXX |              | XXX |   XXX
    #
    # Montos No Gravados/Exentos: XXX
    iibb_arba_activity_ids = fields.Many2many('l10n_ar.iibb.arba.actividad', string='Actividades ARBA', help='Lista de actividades en ARBA')

    agente_percepcion_arba = fields.Boolean(string="Agente Percepcion ARBA", default=False)
    agente_retencion_arba = fields.Boolean(string="Agente Retencion ARBA", default=False)
    agente_percepcion_agip = fields.Boolean(string="Agente Percepcion AGIP", default=False)
    agente_retencion_agip = fields.Boolean(string="Agente Retencion AGIP", default=False)
    agente_retencion_sicore = fields.Boolean(string="Agente Retencion SICORE", default=False)

    def _default_country_id(self):
        country_ar = self.env['res.country'].search([('code', '=', 'AR')])
        return country_ar

    def query_afip(self):
        # TODO: Don't save in DB yet
        # https://www.odoo.com/es_ES/forum/ayuda-1/how-to-access-the-return-values-of-on-change-without-saving-38961
        
        res = requests.get("https://afip.tangofactura.com/Rest/GetContribuyenteFull?cuit={}".format(self.vat))

        if res.status_code != 200:
            raise UserError("Hubo un error consultando en AFIP el cuit {}".format(self.vat))

        p = res.json()
        # TODO: Agregar campo razon social
        self.name = p['Contribuyente']['nombre']

        # TODO: No se puede cambiar existiendo comprobantes
        # if p['Contribuyente']['EsRI']:
        #     self.l10n_ar_afip_responsibility_type_id = 1
        # if p['Contribuyente']['EsMonotributo']:
        #     self.l10n_ar_afip_responsibility_type_id = 6
        #     self.monotributo_category = p['Contribuyente']['categoriasMonotributo'][0]['descCatMonotributo'][0]
        # if p['Contribuyente']['EsExento']:
        #     self.l10n_ar_afip_responsibility_type_id = 4

        # TODO:
        # p['Contribuyente']['EsConsumidorFinal'] # Consumidor Final

        # Codigo de Actividades
        activity_codes = list(map(lambda a: a['idActividad'], p['Contribuyente']['ListaActividades']))
        self.afip_activity_ids = self.env["l10n_ar.afip.actividad"].search([
            ('code', 'in', activity_codes)
        ])
        self.street = p['Contribuyente']['domicilioFiscal']['direccion']
        self.city = p['Contribuyente']['domicilioFiscal']['localidad']
        # TODO: self.state_id # Provincia
        self.zip = p['Contribuyente']['domicilioFiscal']['codPostal']

        # _logger.info("Query CUIT {}".format(self.vat))
        # result = {
        #     "datosGenerales": {
        #         "apellido": "ARANGUREN",
        #         "nombre": "JUAN FRANCISCO",
        #         "tipoPersona": "FISICA"
        #     },
        #     "datosRegimenGeneral": {
        #         "actividad": [
        #             {
        #                 "descripcionActividad": "VENTA AL POR MENOR POR INTERNET",
        #                 "idActividad": "479101",
        #                 "orden": "1"
        #             }
        #         ],
        #         "impuesto": [
        #             {
        #                 "descripcionImpuesto": "GANANCIAS PERSONAS FISICAS",
        #                 "idImpuesto": "11",
        #                 "periodo": "202104"
        #             }
        #         ],
        #         "categoriaAutonomo": {
        #             "descripcionCategoria": "T3 CAT I INGRESOS HASTA $25.000",
        #             "idCategoria": "301",
        #             "idImpuesto": "308"
        #         }
        #     }
        # }
        
        # datos = result["datosGenerales"]
        # if datos["tipoPersona"] == "FISICA":
        #     # Nombre y apellido
        #     self.name = "{} {}".format(datos["nombre"], datos["apellido"])

        #     if result["datosMonotributo"]:
        #         # Monotributo
        #         self.monotributo_category = "A"
        #     else:
        #         # Responsable Inscripto
        #         self.monotributo_category = ""
        # else:
        #     # Razon social
        #     self.name = "{}".format(datos["razonSocial"])

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

        # TODO: cambiar a empresa creada recientemente

        return c