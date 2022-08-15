from odoo import http
from odoo.http import request
from odoo.exceptions import UserError

import requests
import logging

_logger = logging.getLogger(__name__)

# Inspirado en el banner de accounting de Odoo
# https://github.com/odoo/odoo/blob/a7f7233e0eae8ee101d745a9813cba930fd03dcb/addons/account/controllers/onboarding.py
# https://github.com/odoo/odoo/blob/a7f7233e0eae8ee101d745a9813cba930fd03dcb/addons/account/views/account_onboarding_templates.xml

class AccountDashboardController(http.Controller):

    @http.route('/pyme_accounting/account_dashboard', auth='user', type='json')
    def account_invoice_onboarding(self):
        # company = request.env.company

        # if not request.env.is_admin() or \
        #         company.account_invoice_onboarding_state == 'closed':
        #     return {}

        return {
            # 'html': request.env.ref('account.account_invoice_onboarding_panel')._render({
            #     'company': company,
            #     'state': company.get_and_update_account_invoice_onboarding_state()
            # })
            # 'html': '<div>ESTO ES UN BANNER!!!</div>'
        }

    @http.route('/pyme_accounting/me', auth='user', type='json')
    def account_me(self):
        return {
            'user_id': request.env.uid,
            'company_id': request.env.user.company_id.id,
            'db': request.session.db
        }

    @http.route('/pyme_accounting/logout', auth='user', type='json')
    def account_logout(self):
        resp = request.session.logout()
        return {
            'user_id': request.env.uid,
            'company_id': request.env.user.company_id.id,
            'db': request.session.db,
            'resp': resp
        }

    @http.route('/pyme_accounting/cuit', auth='user', type='json')
    def query_afip(self, **kwargs):
        vat = kwargs['vat']
        res = requests.get("https://afip.tangofactura.com/Rest/GetContribuyenteFull?cuit={}".format(vat))

        if res.status_code != 200:
            raise UserError("Hubo un error consultando en AFIP el cuit {}".format())

        p = res.json()
        
        resp = {}

        resp['name'] = p['Contribuyente']['nombre']

        if p['Contribuyente']['EsRI']:
            resp['condicion_fiscal']= 'iva_responsable_inscripto'
        if p['Contribuyente']['EsMonotributo']:
            resp['condicion_fiscal'] = 'responsable_monotributo'
            # self.monotributo_category = p['Contribuyente']['categoriasMonotributo'][0]['descCatMonotributo'][0]
        if p['Contribuyente']['EsExento']:
            resp['condicion_fiscal'] = 'iva_sujeto_exento'

        resp['tipo_persona'] = 'fisica' if p['Contribuyente']['tipoPersona'] == "FISICA" else 'juridica'

        # TODO:
        # p['Contribuyente']['EsConsumidorFinal'] # Consumidor Final

        # Codigo de Actividades
        resp['afip_activity_codes'] = list(map(lambda a: a['idActividad'], p['Contribuyente']['ListaActividades']))
        # afip_activity_ids = request.env["l10n_ar.afip.actividad"].search([
        #     ('code', 'in', activity_codes)
        # ])
        # resp['afip_activity_ids'] = list(map(lambda a: { 'id': a.id, 'code': a.code, 'name': a.name }, afip_activity_ids))
        resp['street'] = p['Contribuyente']['domicilioFiscal']['direccion']
        resp['city'] = p['Contribuyente']['domicilioFiscal']['localidad']
        # TODO: self.state_id # Provincia
        resp['zip'] = p['Contribuyente']['domicilioFiscal']['codPostal']

        return resp

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