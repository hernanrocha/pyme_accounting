##############################################################################
# For copyright and license notices, see __manifest__.py file in module root
# directory
##############################################################################
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from ast import literal_eval
import base64
import logging
import re

_logger = logging.getLogger(__name__)

# -- Todas las facturas emitidas, agrupadas por condicion fiscal del cliente
# -- TODO: Filtrar por fecha, company_id y posted (mostrar borrador??)
# SELECT mv.tax, mv.total, mv.l10n_ar_afip_responsibility_type_id,
# resp.name as name
# FROM (
# 	SELECT SUM(am.amount_tax_signed) as tax, SUM(am.amount_total_signed) as total,
# am.l10n_ar_afip_responsibility_type_id
# 	FROM account_move am
# 	WHERE move_type IN ('out_invoice', 'out_refund')
# 	GROUP BY l10n_ar_afip_responsibility_type_id
# ) mv
# -- l10n_ar_afip_responsibility_type_id: condicion fiscal del partner en las facturas
# LEFT JOIN l10n_ar_afip_responsibility_type resp
# ON mv.l10n_ar_afip_responsibility_type_id = resp.id

def format_amount(amount):
    return '{:0.2f}'.format(amount)

def format_iva(code):
    # (1) No Gravado
    # (2) Exento 
    # (3) 0%
    codes = {
        '4': '10.5%',
        '5': '21%',
        '6': '27%',
        '8': '5%',
        '9': '2.5%',
    }
    return codes[code]

def split_iva(vat_taxes, label):
    _logger.info(" - Splitting: {} - {}".format(vat_taxes, vat_taxes.mapped('tax_group_id.l10n_ar_vat_afip_code')))
    lines = []
    for afip_code in vat_taxes.mapped('tax_group_id.l10n_ar_vat_afip_code'):
        taxes = vat_taxes.filtered(lambda x: x.tax_group_id.l10n_ar_vat_afip_code == afip_code)
        
        # TODO: factura en otra moneda

        # Factura en pesos
        imp_neto = sum(taxes.mapped('tax_base_amount'))
        imp_liquidado = sum(taxes.mapped('price_subtotal'))
        lines.append([ 
            '1234',
            label,
            format_iva(afip_code),
            format_amount(imp_neto),
            format_amount(imp_liquidado),
            format_amount(imp_liquidado + imp_neto)
        ])
    return lines

# Las lineas "No gravadas", "Exentas" y "0%" no tienen una linea de impuestos asociada
# Las que tienen un monto IVA, en cambio, tienen una linea especifica.
# Se caracterizan por tener un tax_group_id diferente de NULL
# Las lineas que tienen un mismo IVA se agrupan en una sola

# TODO: No duplicar estas funciones
def untaxed_exempt_line(line):
    codes = line.mapped('tax_ids').mapped('tax_group_id').mapped('l10n_ar_vat_afip_code')
    return '1' in codes or '2' in codes

def taxed_0_line(line):
    codes = line.mapped('tax_ids').mapped('tax_group_id').mapped('l10n_ar_vat_afip_code')
    return '3' in codes

def taxed_line(line):
    # TODO: ignorar retenciones y percepciones
    return line.tax_group_id

class ReportIvaF2002(models.Model):
    _name = 'report.pyme_accounting.report_iva_f2002'

    def _get_report_values(self, docids, data=None):
        _logger.info("GETTING INFO F.2002")

        _logger.info("COMPROBANTES DE VENTA EMITIDOS")
        debito_ventas = self.get_ventas(self.get_digital_invoices('out_invoice'))
        _logger.info("NOTAS DE CREDITO EMITIDAS")
        credito_nc_emitidas = self.get_ventas(self.get_digital_invoices('out_refund'))

        _logger.info("COMPROBANTES DE COMPRA RECIBIDOS")
        credito_compras = self.get_compras(self.get_digital_invoices('in_invoice'))        
        _logger.info("NOTAS DE CREDITO RECIBIDAS")
        debito_nc_recibidas = self.get_compras(self.get_digital_invoices('in_refund'))
        

        return {
            'name': 'IVA Por Actividad - F. 2002',
            # Primer Parrafo
            'debito_ventas': debito_ventas,
            # TODO
            # 'debito_ventas_bienes': [],
            'debito_nc_recibidas': debito_nc_recibidas,
            'credito_compras': credito_compras,
            'credito_nc_emitidas': credito_nc_emitidas,
            'operaciones_no_gravadas': [],
            # TODO
            # 'credito_acuenta': [],
            # TODO
            # Segundo Parrafo
            'ingresos_retenciones': [],
            'ingresos_percepciones': [],
            'ingresos_acuenta': [],

        }

    def get_digital_invoices(self, move_type):
        _logger.info('{} - {} - {}'.format(self.env, self.env.company.id, self.env.user.company_id))

        # TODO: filtrado por fechas, confirmado
        return self.env['account.move'].search(
            [
                ('company_id', '=', self.env.company.id),
                ('state', '=', 'posted'),
                ('move_type', '=', move_type),
            ], 
            order='invoice_date asc')

    def get_ventas(self, invoices):
        _logger.info("Invoices: {}".format(invoices))
        _logger.info("Afip Resp: {}".format(invoices.mapped('l10n_ar_afip_responsibility_type_id').mapped('code')))
        
        # Para NC de Compras, es lo mismo que facturas de compra:
        # - Bienes en mercado local
        # -
        # Para NC de Ventas, es lo mismo que facturas de venta:
        # - RI
        # - CF, Exentos y No Alcanzados
        # - Monotributistas
        # - Op. Gravadas al 0%
        # - Op. No Gravadas y Exentas
        #
        # Para Venta de Bienes de Uso:
        # - Responsables Inscriptos
        # - CF, Monotributistas, Exentos, No Alcanzados

        # TODO: separar por actividad

        # Condicion Fiscal
        # 1 - IVA Responsable Inscripto
        # 4 - Exento
        # 5 - Consumidor Final
        # 6 - Monotributo
        # 99 - No Alcanzado

        lines = []

        # Responsables inscriptos
        inv_ri = invoices.filtered(
            lambda i: i.l10n_ar_afip_responsibility_type_id.code == '1')
        _logger.info("inv_ri: {}".format(inv_ri))
        lines_ri = inv_ri.mapped('line_ids').filtered(taxed_line)
        _logger.info("lines_ri: {}".format(lines_ri))
        lines.extend(split_iva(lines_ri, "Responsables Inscriptos"))

        # Consumidores Finales, Exentos y No Alcanzados
        inv_cf_ex_na = invoices.filtered(
            lambda i: i.l10n_ar_afip_responsibility_type_id.code in [ '4', '5', '99' ])
        _logger.info("inv_cf_ex_na: {}".format(inv_cf_ex_na))
        lines_cf_ex_na = inv_cf_ex_na.mapped('line_ids').filtered(taxed_line)
        lines.extend(split_iva(lines_cf_ex_na, "Cons. Finales, Exentos y No Alcanzados"))
        
        # Monotributistas
        inv_mt = invoices.filtered(
            lambda i: i.l10n_ar_afip_responsibility_type_id.code == '6')
        _logger.info("inv_mt: {}".format(inv_mt))
        lines_mt = inv_mt.mapped('line_ids').filtered(taxed_line)
        lines.extend(split_iva(lines_mt, "Monotributistas"))
        
        # Operaciones Gravadas al 0%
        lines_taxed_0 = invoices.mapped('invoice_line_ids').filtered(taxed_0_line)
        _logger.info("lines_taxed_0: {}".format(lines_taxed_0))
        if len(lines_taxed_0):
            amount = sum(lines_taxed_0.mapped('price_total'))
            lines.append([ 
                '1234',
                "Operaciones Gravadas al 0%",
                "0%",
                format_amount(amount),
                format_amount(0),
                format_amount(amount),
            ])

        # Operaciones Exentas / No Gravadas
        lines_untaxed_exempt = invoices.mapped('invoice_line_ids').filtered(untaxed_exempt_line)
        _logger.info("lines_untaxed_exempt: {}".format(lines_untaxed_exempt))
        if len(lines_untaxed_exempt):
            amount = sum(lines_untaxed_exempt.mapped('price_total'))
            lines.append([ 
                '1234',
                "Operaciones No Gravadas y Exentas",
                "0%",
                format_amount(amount),
                format_amount(0),
                format_amount(amount),
            ])
        
        _logger.info("lines: {}".format(lines))

        # Calcular Totales
        total = [ 0.00, 0.00, 0.00 ]
        for line in lines:
            total[0] += float(line[3])
            total[1] += float(line[4])
            total[2] += float(line[5])
        
        total[0] = format_amount(total[0])
        total[1] = format_amount(total[1])
        total[2] = format_amount(total[2])

        return { 'lines': lines, 'total': total }

    def get_compras(self, invoices):
        _logger.info("Invoices: {}".format(invoices))
        _logger.info("Afip Resp: {}".format(invoices.mapped('l10n_ar_afip_responsibility_type_id').mapped('code')))
        
        lines = []

        # Responsables inscriptos
        lines_all = invoices.mapped('line_ids').filtered(taxed_line)
        _logger.info("lines_all: {}".format(lines_all))
        lines.extend(split_iva(lines_all, "Compra de Bienes (excepto Bs de Uso)"))
        
        # Operaciones Gravadas al 0%
        lines_taxed_0 = invoices.mapped('invoice_line_ids').filtered(taxed_0_line)
        _logger.info("lines_taxed_0: {}".format(lines_taxed_0))
        if len(lines_taxed_0):
            amount = sum(lines_taxed_0.mapped('price_total'))
            lines.append([ 
                '1234',
                "Operaciones Gravadas al 0%",
                "0%",
                format_amount(amount),
                format_amount(0),
                format_amount(amount),
            ])

        # Operaciones Exentas / No Gravadas
        lines_untaxed_exempt = invoices.mapped('invoice_line_ids').filtered(untaxed_exempt_line)
        _logger.info("lines_untaxed_exempt: {}".format(lines_untaxed_exempt))
        if len(lines_untaxed_exempt):
            amount = sum(lines_untaxed_exempt.mapped('price_total'))
            lines.append([ 
                '1234',
                "Operaciones No Gravadas y Exentas",
                "0%",
                format_amount(amount),
                format_amount(0),
                format_amount(amount),
            ])
        
        _logger.info("lines: {}".format(lines))

        # Calcular Totales
        total = [ 0.00, 0.00, 0.00 ]
        for line in lines:
            total[0] += float(line[3])
            total[1] += float(line[4])
            total[2] += float(line[5])
        
        total[0] = format_amount(total[0])
        total[1] = format_amount(total[1])
        total[2] = format_amount(total[2])

        return { 'lines': lines, 'total': total }    

# Todas las lineas de factura indicando el impuesto asociado
# TODO: Filtrar solo las de IVA
# SELECT lines.tax_id, lines.tax_name,
# sum(lines.amount_taxed) amount_taxed, 
# sum(lines.amount_tax) amount_tax, 
# sum(lines.amount_total) amount_total
# FROM
# (SELECT
# 	am.id move_id, am.name as name, 
# 	line.id line_id,
# 	tax.id as tax_id, 
# 	tax.tax_group_id tax_group_id,
# 	tax.name as tax_name,
# 	line.price_subtotal amount_taxed, 
# 	(line.price_total - line.price_subtotal) amount_tax,
# 	line.price_total amount_total
# 	-- line.exclude_from_invoice_tab,
# 	--am.amount_tax_signed as tax, am.amount_total_signed as total, am.l10n_ar_afip_responsibility_type_id
# 	FROM account_move am
# 	JOIN account_move_line line
# 	ON line.move_id = am.id
# 	-- Tabla NxN entre line y tax
# 	JOIN account_move_line_account_tax_rel mtl
# 	ON line.id = mtl.account_move_line_id
# 	-- Tabla de taxes
# 	JOIN account_tax tax
# 	ON tax.id = mtl.account_tax_id
# 	WHERE am.move_type IN ('out_invoice')
# 	AND am.company_id = 4
# 	AND line.exclude_from_invoice_tab IS NOT TRUE
# 	ORDER BY am.date -- TODO: definir este valor
# ) lines
# GROUP BY lines.tax_id, lines.tax_name

# Ver lineas de impuestos. Puede haber mas de una por linea de factura
# Por ejemplo una para IVA, otra para percepcion, etc.
# Las facturas con IVA No Gravado/Exento no tienen linea de impuesto
# SELECT tl.id, tl.move_id move_id, tl.tax_line_id tax_id, tl.tax_group_id, 
# tl.tax_base_amount, tl.price_unit, tl.tax_exigible 
# FROM account_move_line tl
# WHERE tax_line_id IS NOT NULL
#
# company_id => Empresa
# move_id => ID de Factura Padre
# currency_id => Moneda (Peso)
# partner_id => Cliente/Proveedor
# parent_state => Estado de la factura (Posted/Draft)
# tax_line_id => ID del impuesto (IVA 21%/IVA 10.5%)
# tax_group_id => Gravado/No Gravado/Municipales/Provinciales
# tax_base_amount => 4524.89 (Monto Gravado)
# price_unit => 475.11 (IVA)
# tax_exigible => true (se puede tomar???)
# l10n_latam_document_type_id => Tipo de factura (A,B,C)

# Lineas de factura con montos de IVA
# SELECT
# am.id move_id, am.name as name, 
# line.id line_id, 
# tax.id as tax_id, tax.name as tax_name,
# line.price_subtotal amount_taxed, 
# (line.price_total - line.price_subtotal) amount_tax, 
# line.price_total amount_total
# -- line.exclude_from_invoice_tab,
# --am.amount_tax_signed as tax, am.amount_total_signed as total, am.l10n_ar_afip_responsibility_type_id
# FROM account_move am
# JOIN account_move_line line
# ON line.move_id = am.id
# JOIN account_move_line_account_tax_rel mtl
# ON line.id = mtl.account_move_line_id
# JOIN account_tax tax
# ON tax.id = mtl.account_tax_id
# WHERE am.move_type IN ('out_invoice')
# AND am.company_id = 4
# AND line.exclude_from_invoice_tab IS NOT TRUE
# ORDER BY am.date -- TODO: definir este valor

# TODO: Por que se usa commercial_partner_id y no partner_id
# TODO: name vs display_name en res_partner



# PARRAFO 1

# DEBITO FISCAL (VENTAS)
#  
# JOIN 1: Codigo Actividad => Cada actividad AFIP de la empresa (definida por producto)
# 
# JOIN 2: Operacion con    => [
#   "Responsables Inscriptos", 
#   "Cons. Finales, Exentos y No Alcanzados",
#   "Monotributistas"
# ]
# Filtrar operaciones de tipo "Otros conceptos", "Operaciones no gravadas y exentas"
# En SOS Contador, [ 
# "2. Cons. Final, Exento y No Alcanzados", 
# "4. Op. Gravadas al 0%", 
# "5. Operaciones No Gravadas y Exentas excepto exportaciones" ]
#
# JOIN 3: Tasa IVA (para las basicas)
#
# Mostrar: Neto, IVA, Total

# DEBITO FISCAL (VENTAS BIENES DE USO)
# Es igual, solo que aplica a productos marcados como bienes de uso

# NOTAS DE CREDITO RECIBIDAS (COMPRAS)