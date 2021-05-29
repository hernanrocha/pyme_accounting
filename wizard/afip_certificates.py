# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class AfipCertificatesWizard(models.TransientModel):
    _name = "l10n_ar.afip.certificates.wizard"
    _inherit = ['multi.step.wizard.mixin']
    _description = "Administrar Certificados AFIP"

    # Step 1: create and validate certificate
    auth_req = fields.Text(string="Solicitud", readonly=True, 
    default="""--------------BEGIN--CERTIFICATE-------------------
adasdasdasdasdsadadasdasdasdasdsadadasdasdasdasdsad
adasdasdasdasdsadadasdasdasdasdsadadasdasdasdasdsad
adasdasdasdasdsadadasdasdasdasdsadadasdasdasdasdsad
adasdasdasdasdsadadasdasdasdasdsadadasdasdasdasdsad
adasdasdasdasdsadadasdasdasdasdsadadasdasdasdasdsad
adasdasdasdasdsadadasdasdasdasdsadadasdasdasdasdsad
--------------END--CERTIFICATE---------------------""")
    auth_resp = fields.Text(string="Respuesta")

    # Step 2: create delegations
    delegate_1 = fields.Boolean(string="Factura Electrónica")
    delegate_2 = fields.Boolean(string="Factura Electrónica de Exportacion")
    delegate_3 = fields.Boolean(string="Consulta de Padron")
    delegate_4 = fields.Boolean(string="Consulta de Cotizacion")

    # pending, validated, error
    # delegate_1_state = fields.Selection(readonly=True)
    # delegate_2_state = fields.Selection(readonly=True)
    # delegate_3_state = fields.Selection(readonly=True)
    # delegate_4_state = fields.Selection(readonly=True)

    currency_id = fields.Char(string='Moneda', default="DOL")

    @api.model
    def _selection_state(self):
        return [
            ('start', 'Inicio'),
            ('certificate', 'Crear Certificado'),
            ('delegation', 'Delegación de Servicios'),
            ('final', 'Completado'),
        ]

    def state_exit_start(self):
        self.state = 'certificate'

    def state_exit_certificate(self):
        # TODO: parse certificate. maybe call to dummy?
        self.state = 'delegation'

    def state_exit_delegation(self):
        # TODO: for each 
        self.state = 'final'

    def action_last_invoice(self):
        pass

        # TODO: Implement this
        # if afip_ws in ("wsfe", "wsmtxca"):
        #     last = ws.CompUltimoAutorizado(document_type.code, self.l10n_ar_afip_pos_number)
        #     print("LAST", last)

    def action_validate_invoice(self):
        # TODO: Aplicar rate limit a llamadas AFIP
        # TODO: Extender a factura de exportacion
        # TODO: Convertir a "Importar factura"
        # CompConsultar(tipo_cbte, punto_vta, cbte_nro, reproceso=False)
        # CbteTipo=6 (Factura C)
        # PtoVta=1 (PdV 1)
        # CbteDesde=2 (Comprobante 2)
        ws = self.env.user.company_id.get_connection('wsfe').connect()
        cae = ws.CompConsultar(6, 1, 1)
        print("COMPROBANTE")
        print(cae)
        # 71124921033563
        print(ws.factura)
        # {'concepto': 1, 'tipo_doc': 80, 'nro_doc': 20222222223, 'tipo_cbte': 6, 'punto_vta': 1, 'cbt_desde': 1, 'cbt_hasta': 1, 'fecha_cbte': '20210321', 'imp_total': 2159.0, 'imp_tot_conc': 0.0, 'imp_neto': 1959.97, 'imp_op_ex': 0.0, 'imp_trib': 0.0, 'imp_iva': 199.03, 'fecha_serv_desde': '', 'fecha_serv_hasta': '', 'fecha_venc_pago': '', 'moneda_id': 'PES', 'moneda_ctz': 1.0, 'cbtes_asoc': [], 'tributos': [], 'iva': [{'iva_id': 5, 'base_imp': 631.39, 'importe': 132.59}, {'iva_id': 8, 'base_imp': 1328.58, 'importe': 66.42}], 'opcionales': [], 'compradores': [], 'cae': '71124921033563', 'resultado': 'A', 'fch_venc_cae': '20210331', 'obs': []}

    def action_list_pos(self):
        self.ensure_one()
        # afip_ws = self.afip_ws

        afip_ws = 'wsfe'
        if not afip_ws:
            raise UserError(_('No AFIP WS selected'))
        ws = self.env.user.company_id.get_connection(afip_ws).connect()
        if afip_ws == 'wsfex':
            ret = ws.GetParamPtosVenta()
            print("PdV wsfex", ret)
        elif afip_ws == 'wsfe':
            ret = ws.ParamGetPtosVenta(sep=" ")
            print("PdV wsfe", ret)
        else:
            raise UserError(_(
                'Get point of sale for ws %s is not implemented yet') % (
                afip_ws))
        msg = (_(" %s %s") % (
            '. '.join(ret), " - ".join([ws.Excepcion, ws.ErrMsg, ws.Obs])))
        title = _('Enabled Point Of Sales on AFIP\n')
        raise UserError(title + msg)

    def action_get_currency(self):
        # Obtener company del usuario
        ws = self.env.user.company_id.get_connection('wsfe').connect()

        cotizacion = ws.ParamGetCotizacion(self.currency_id)
        print("COTIZACION")
        print(cotizacion)

        # Mas metodos en el siguiente snippet
        # http://www.sistemasagiles.com.ar/trac/wiki/PyAfipWs
        # https://github.com/reingart/pyafipws/blob/develop/wsfev1.py
        # concepto = ws.ParamGetTiposConcepto()
        # print("CONCEPTOS")
        # print(concepto)
        # docs = ws.ParamGetTiposDoc()
        # print("DOCS")
        # print(docs)
        # iva = ws.ParamGetTiposIva()
        # print("IVAS")
        # print(iva)
        # monedas = ws.ParamGetTiposMonedas()
        # print("MONEDAS")
        # print(monedas)
        # opcional = ws.ParamGetTiposOpcional()
        # print("OPCIONAL")
        # print(opcional)
        # tributos = ws.ParamGetTiposTributos()
        # print("TRIBUTOS")
        # print(tributos)
        # paises = ws.ParamGetTiposPaises()
        # print("PAISES")
        # print(paises)
