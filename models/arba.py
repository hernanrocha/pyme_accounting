# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError

class ArbaRetencion(models.Model):
    _name = "l10n_ar.arba.retencion"

    date = fields.Date(string="Fecha")
    amount = fields.Float(string="Monto")


class ArbaRetencionBancaria(models.Model):
    _name = "l10n_ar.arba.retencion_bancaria"

    date = fields.Date(string="Fecha")
    amount = fields.Float(string="Monto")

class ArbaDevolucionBancaria(models.Model):
    _name = "l10n_ar.arba.devolucion_bancaria"

    date = fields.Date(string="Fecha")
    amount = fields.Float(string="Monto")

##### Retenciones/Percepciones
class ImpuestosDeduccion(models.Model):
    _name = "l10n_ar.impuestos.deduccion"
    _order = "date desc"

    # WIDGET DE CONCILIACION
    # Casos a Testear:
    # - Perc/Ret sin comprobante asociado
    # - Perc/Ret con comprobante asociado, valores diferentes
    #   - Se define un valor a tomar (por defecto la percepcion)
    #     - Se cambia el valor elegido de No Gravado a perc/ret., y se asocian
    # - Perc/Ret con comprobante asociado, mismos valores
    #   - Se cambia el valor de No Gravado al monto de la perc/ret. y se asocian
    # - Comprobantes del mismo periodo sin Perc/Ret
    #   - Opcionalmente crear ret/perc con el monto No Gravado

    company_id = fields.Many2one(
        'res.company',
        string='Empresa',
        required=True,
        readonly=True,
        default=lambda self: self.env['res.company']._company_default_get('l10n_ar.impuestos.deduccion')
    )

    # Informacion inicial. Puede cambiar con respecto al comprobante real
    date = fields.Date(string="Fecha")
    amount = fields.Float(string="Monto")
    control = fields.Char(string="Control")
    cuit = fields.Char(string="CUIT")
    invoice_pos = fields.Char(string="Pto de Venta")
    invoice_number = fields.Char(string="N° Cbte")
    invoice_description = fields.Char(string="Descripcion Cbte")

    # Referencia al comprobante
    move_id = fields.Many2one('account.move', string='Comprobante',
        index=True, readonly=True, auto_join=True, ondelete="set null",
        check_company=True)
    # Referencia la linea de impuesto asociada
    tax_id = fields.Many2one('account.move.line', string='Impuesto',
        index=True, readonly=True, auto_join=True, ondelete="set null",
        check_company=True)
    
    # Descripcion
    description = fields.Char(string="Descripción")
    # Fecha Ret/Perc
    apply_date = fields.Date(string="Fecha Ret/Perc")
    # Fecha Registración DJ
    publish_date = fields.Date(string="Fecha Registración DJ")
    # TODO: Agregar un modelo "tax" y "tax_group" para estos selections
    # Tipo
    type = fields.Selection([
        # ARBA
        ('arba_percepcion', 'ARBA - Percepción'),
        ('arba_retencion', 'ARBA - Retención'),
        ('arba_retencion_bancaria', 'ARBA - Retención Bancaria'),
        ('arba_devolucion_bancaria', 'ARBA - Devolución Bancaria'),

        # IVA
        
        # 493 - REG.PER.AL VALOR AGREGADO - EMPRESAS PROVEEDORAS.
        ('iva_percepcion', 'IVA - Percepción'),
        # Not used yet
        ('iva_retencion', 'IVA - Retención'),
    ], 'Tipo de Deducción')
    # Regimen
    tax = fields.Selection([
        ('arba', 'ARBA - Ingresos Brutos Bs. As.'),
        # 767 - SICORE - RETENCIONES Y PERCEPCIONES - IMPUESTO AL VALOR AGREGADO
        ('iva', 'IVA - Impuesto al Valor Agregado'),
    ], 'Impuesto asociado')
    state = fields.Selection([
        # Disponible para usar
        ('available', 'Disponible'),
        # Ya usada en una DJ
        ('used', 'Usada'),
        # Descartada por el usuario
        ('discarded', 'Descartada'),
        # Vencida sin uso
        ('expired', 'Vencida'),
    ], 'Estado')