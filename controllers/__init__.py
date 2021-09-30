# -*- coding: utf-8 -*-

import logging
import pprint
import requests
import json

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# /web/main.py

# from odoo.addons.payment_mercadopago.mercadopago import mercadopago

class MyController(http.Controller):

    # @http.route('/productos/<model("product.template"):product>', auth='public', website=True)
    # def test_get_product(self, product):

    # def test_params(self, **kw):
    #   return request.params["nombre"]

    # type: json/http (json es JRPC, http es WEB)
    # auth: none,public,user

    @http.route('/ping', type='http', auth='none')
    def handler(self):
        #  # Render custom template with data
        #  return http.request.render('template.name', {
        #     'product_id': 124
        # })
        # if 'json' in request.params:
        #     return { 'json': True, 'age': 19 }
        
        # return "Hola mundo"
        return "OK"

    # @http.route('/helloweb', type='http', auth='user')
    # def handler(self):
    #     if 'json' in request.params:
    #         return request.render('pyme_accounting.base_template_id', {
    #             'nombre': "Hernan",
    #             'product': {
    #                 "name": "Mesa",
    #                 "list_price": 203.20,
    #             }
    #         })
        
    #     # context = request.env['ir.http'].webclient_rendering_context()
    #     # response = request.render('web.webclient_bootstrap', qcontext=context)
    #     # response.headers['X-Frame-Options'] = 'DENY'
    #     # return response
    #     return "Hello world"

    # @http.route('/cuit', type='json', auth='none')
    # def get_cuit(self):
    #     cuit = request.params['cuit']
    #     res = requests.get('https://afip.tangofactura.com/Rest/GetContribuyenteFull?cuit={}'.format(cuit))
    #     res = res.json()
    #     return res

# class SendgridController(http.Controller):

#     @http.route('/payment/mercadopago/ipn/', type='json', auth='none')
#     def mercadopago_ipn(self, **post):
#         """ MercadoPago IPpprN. """
#         # recibimo algo como http://www.yoursite.com/notifications?topic=payment&id=identificador-de-la-operación
#         #segun el topic: # luego se consulta con el "id"
#         _logger.info('Beginning MercadoPago IPN form_feedback with post data %s', pprint.pformat(post))  # debug
#         # querys = parse.urlsplit(request.httprequest.url).query
#         # params = dict(parse.parse_qsl(querys))
#         # _logger.info(params)
#         # if (params and ('topic' in params or 'type' in params) and ('id' in params or 'data.id' in params)):
#         #     self.mercadopago_validate_data( **params )
#         # else:
#         #     self.mercadopago_validate_data(**post)
#         return ''