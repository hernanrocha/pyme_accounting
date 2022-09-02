from odoo import http
from odoo.http import request
from odoo.exceptions import UserError

import requests
import logging
import os
import base64
import uuid
from pathlib import Path

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
        db = request.session.db
        resp = request.session.logout()
        return {
            'user_id': request.env.uid,
            'company_id': request.env.user.company_id.id,
            'db': db,
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
        afip_activity_codes = list(map(lambda a: a['idActividad'], p['Contribuyente']['ListaActividades']))
        afip_activity_ids = request.env["l10n_ar.afip.actividad"].search([
            ('code', 'in', afip_activity_codes)
        ])
        resp['afip_activity_ids'] = list(map(lambda a: { 'id': a.id, 'code': a.code, 'name': a.name }, afip_activity_ids))
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

    @http.route('/pyme_accounting/monotributo', auth='user', type='json')
    def monotributo_mensual(self, **kwargs):
        include_draft = kwargs['include_draft']
        states = ['draft', 'posted'] if include_draft else ['posted']
        
        moves = request.env['account.move'].read_group(
            # domain
            [ 
                ('company_id', '=', request.env.company.id),
                ('move_type', 'in', [ 'in_invoice', 'in_refund', 'out_invoice', 'out_refund' ]),
                ('state', 'in', states)
            ], 
            # fields
            [ 'amount_total:sum' ],
            # groupby
            [ 'invoice_date:month', 'move_type' ],
            # lazy: do all groupbys in one call.
            lazy=False
        )

        month_line_ids = []

        data = {}

        for m in moves:
            # Cargar por primera vez una linea de mes
            # TODO: cargar automaticamente los ultimos 12 meses
            if not m['invoice_date:month'] in data:
                data[m['invoice_date:month']] = {
                    'date': m['invoice_date:month'],
                    'out_invoice': 0,
                    'in_invoice': 0,
                    'out_refund': 0,
                    'in_refund': 0
                }
            
            data[m['invoice_date:month']][m['move_type']] = m['amount_total']

        t_sales = 0
        # t_purchases = 0
        # t_balance = 0
        
        for d in data.items():
            ventas = d[1]['out_invoice'] - d[1]['out_refund']
            compras = d[1]['in_invoice'] - d[1]['in_refund']
            month_line_ids.append({
                'mes': d[0],
                'ventas': ventas,
                'compras': compras,
                'resultado': ventas - compras
            })

            # Agregar a totales
            t_sales += ventas
            # t_purchases += compras
            # t_balance += ventas - compras

        # TODO: obtener facturacion anual, pago mensual, etc.
        # for c in categories:
        #     facturacion_anual = c['max_invoice']
            
        #     # Si está dentro del limite de facturación, seleccionar esa categoria
        #     if facturacion_anual > self.facturacion_anual:
        #         self.categoria = c['char']
        #         self.maximo_facturacion = facturacion_anual
        #         self.pago_mensual = c['service_payment']
        #         return

        # Actualizar Facturacion Total
        return {
            'month_line_ids': month_line_ids,
            'facturacion_anual': t_sales
        }

    @http.route('/pyme_accounting/demo_pem', auth='public', type='json')
    def demo_pem(self, **kwargs):
        pem = kwargs['pem_file']
        
        # Make sure /tmp/nanocontadores exists
        Path("/tmp/nanocontadores").mkdir(parents=True, exist_ok=True) 

        # Guardar PEM
        xmlfile = str(uuid.uuid4())
        _logger.info("Guardando archivo PEM como {}.pem".format(xmlfile))
        with open('/tmp/nanocontadores/{}.pem'.format(xmlfile), 'w') as writer:
            writer.write(base64.decodebytes(pem.encode('utf-8')).decode('utf-8'))
        
        # Convertir PEM a XML
        _logger.info("Convirtiendo archivo PEM {}.pem en XML".format(xmlfile))
        ret = os.system('openssl cms -verify -in /tmp/nanocontadores/{}.pem -inform PEM -noverify -out /tmp/nanocontadores/{}.xml'.format(xmlfile, xmlfile))
        if ret != 0:
            raise UserError("Hubo un error analizando el archivo .PEM")
        _logger.info("Return OpenSSL {}".format(ret))
        
        raw_xml = ''
        with open('/tmp/nanocontadores/{}.xml'.format(xmlfile), 'r') as reader:
            raw_xml = base64.b64encode(reader.read().encode('ISO-8859-1')) 

        # Borrar archivos PEM y XML temporales
        # os.remove('/tmp/nanocontadores/{}.pem'.format(xmlfile))
        # os.remove('/tmp/nanocontadores/{}.xml'.format(xmlfile))

        return { 'pem_xml': raw_xml }