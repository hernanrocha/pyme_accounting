# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import xml.etree.ElementTree as ET
import base64
from datetime import datetime

ns = {'ss': 'urn:schemas-microsoft-com:office:spreadsheet'}

def cell_data(cells, index):
    return cells[index].find('ss:Data', ns).findtext('.')

class PurchaseImportDeduccionesArbaRLine(models.TransientModel):
    _name = "l10n_ar.import.purchase.deducciones.arba.rline"

    date = fields.Date(string="Fecha")
    amount = fields.Float(string="Monto")
    
    # TODO: borrar esto de la vista de edicion
    import_id = fields.Many2one(comodel_name="l10n_ar.import.purchase.deducciones.arba", ondelete="cascade", readonly=True, invisible=True)

class PurchaseImportDeduccionesArbaRBLine(models.TransientModel):
    _name = "l10n_ar.import.purchase.deducciones.arba.rbline"

    date = fields.Date(string="Fecha")
    amount = fields.Float(string="Monto")

    # TODO: borrar esto de la vista de edicion
    import_id = fields.Many2one(comodel_name="l10n_ar.import.purchase.deducciones.arba", ondelete="cascade", readonly=True, invisible=True)

class PurchaseImportDeduccionesArbaDBLine(models.TransientModel):
    _name = "l10n_ar.import.purchase.deducciones.arba.dbline"

    date = fields.Date(string="Fecha")
    amount = fields.Float(string="Monto")

    # TODO: borrar esto de la vista de edicion
    import_id = fields.Many2one(comodel_name="l10n_ar.import.purchase.deducciones.arba", ondelete="cascade", readonly=True, invisible=True)

class PurchaseImportDeduccionesArba(models.TransientModel):
    _name = "l10n_ar.import.purchase.deducciones.arba"
    _description = "Importar deducciones de ARBA en compras"

    arba_file = fields.Binary(string="Deducciones de ARBA (*.xml)")
    # percepciones
    retenciones = fields.One2many(string="Retenciones", comodel_name="l10n_ar.import.purchase.deducciones.arba.rline", inverse_name="import_id")
    retenciones_bancarias = fields.One2many(string="Retenciones Bancarias", comodel_name="l10n_ar.import.purchase.deducciones.arba.rbline", inverse_name="import_id")
    devoluciones_bancarias = fields.One2many(string="Devoluciones Bancarias", comodel_name="l10n_ar.import.purchase.deducciones.arba.dbline", inverse_name="import_id")
    # TODO: percepciones aduaneras

    notes = fields.Char(string="Notas", readonly=True)

    def parse_purchases(self):
        [data] = self.read()

        if not data['arba_file']:
            raise UserError("Debes cargar un archivo de deducciones de ARBA")

        # Leer archivo
        file_content = base64.decodestring(data['arba_file'])
        root = ET.fromstring(file_content)

        self._parse_percepciones(root)
        self._parse_retenciones(root)
        self._parse_retenciones_bancarias(root)
        self._parse_devoluciones_bancarias(root)

        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'l10n_ar.import.purchase.deducciones.arba',
            'res_id': self.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }
        
    def generate_purchases(self):
        # self._generate_percepciones()
        self._generate_retenciones()
        self._generate_retenciones_bancarias()
        self._generate_devoluciones_bancarias()

    # Percepciones
    def _parse_percepciones(self, root):
        percepciones = root.find("ss:Worksheet[@ss:Name='Percepciones']", ns)
        table = percepciones.find('ss:Table', ns)

        # 0 Tipo comprobante, 1 Letra comprobante, 2 Sucursal, 3 Emision, 4 CUIT Agente
        # 5 Fecha Percepcion Agente, 6 Importe percepcion agente, 
        # 7 Fecha Percepcion contrib., 8 Importe contrib., 9 Estado
        rows = table.findall('ss:Row', ns)[1:]
        for row in rows:
            cells = row.findall('ss:Cell', ns)

            # tipo_comprobante = cell_data(cells, 0) # FA,NC,ND
            # letra_comprobante = cell_data(cells, 1) # A,B,C
            numero_comprobante = "{}-{}".format(cell_data(cells, 2).zfill(5), cell_data(cells, 3).zfill(8))
            cuit = cell_data(cells, 4)
            # Chequear si es importe de agente o de contribuyente
            fecha = cell_data(cells, 7)
            importe = cell_data(cells, 8)
            
            print("[Percepcion]", fecha, cuit, numero_comprobante, importe)

    # Retenciones
    def _parse_retenciones(self, root):
        retenciones = root.find("ss:Worksheet[@ss:Name='Retenciones']", ns)
        table = retenciones.find('ss:Table', ns)

        rows = table.findall('ss:Row', ns)[1:]
        # 0 Sucursal, 1 Emision, 2 CUIT Agente
        # 3 Fecha Retencion agente, 4 Importe retencion agente
        # 5 Fecha Retencion contrib., 6 Importe retencion contrib., 7 Estado
        for row in rows:
            cells = row.findall('ss:Cell', ns)

            # tipo_comprobante = cell_data(cells, 0) # FA,NC,ND
            # letra_comprobante = cell_data(cells, 1) # A,B,C

            sucursal = cell_data(cells, 0)     # 1
            emision = cell_data(cells, 1)      # 55589978 (id correlativo para el agente??)
            cuit_agente = cell_data(cells, 2)  # 30703000534
            # Chequear si es importe de agente o de contribuyente
            fecha = cell_data(cells, 5)        # 19/04/2021
            importe = cell_data(cells, 6)      # 5.00
            estado = cell_data(cells, 7)       # Debe ser "Alta"

            print("[Retencion]", fecha, importe, estado, emision)
            self.retenciones.create({
                'date': datetime.strptime(fecha, '%d/%m/%Y'),
                'amount': float(importe),
                'import_id': self.id,
            })

        print()

    # Retenciones bancarias
    def _parse_retenciones_bancarias(self, root):
        retenciones = root.find("ss:Worksheet[@ss:Name='Retenciones bancarias']", ns)
        table = retenciones.find('ss:Table', ns)

        rows = table.findall('ss:Row', ns)[1:]
        # 0 CUIT Banco, 1 CBU, 2 Fecha Retencion, 
        # 3 Tipo de cuenta agente, 4 Tipo de moneda agente, 5 Importe retencion agente
        # 6 Tipo de cuenta contrib., 7 Tipo de moneda contrib., 8 Importe retencion contrib.
        # 9 Estado
        for row in rows:
            cells = row.findall('ss:Cell', ns)

            fecha = cell_data(cells, 2)    # 11/04/2021
            importe = cell_data(cells, 8)  # 3.01
            estado = cell_data(cells, 9)   # Debe ser "Alta"

            print("[RetencionBancaria]", fecha, importe, estado)
            self.retenciones_bancarias.create({
                'date': datetime.strptime(fecha, '%d/%m/%Y'),
                'amount': float(importe),
                'import_id': self.id,
            })
        
        print()

    # Devoluciones bancarias
    def _parse_devoluciones_bancarias(self, root):
        retenciones = root.find("ss:Worksheet[@ss:Name='Devoluciones bancarias']", ns)
        table = retenciones.find('ss:Table', ns)

        rows = table.findall('ss:Row', ns)[1:]
        # 0 CUIT Banco, 1 CBU, 2 Fecha Retencion
        # 3 Tipo de cuenta agente, 4 Tipo de moneda agente, 5 Importe devolucion agente  
        # 6 Tipo de cuenta contrib., 7 Tipo de moneda contrib., 8 Importe devolucion contrib.
        # 9 Estado
        for row in rows:
            cells = row.findall('ss:Cell', ns)

            fecha = cell_data(cells, 2)
            importe = cell_data(cells, 8)

            self.devoluciones_bancarias.create({
                'date': datetime.strptime(fecha, '%d/%m/%Y'),
                'amount': float(importe),
                'import_id': self.id,
            })

            # for i in range(len(cells)):
            #     print(cell_data(cells, i))

    # TODO: Percepciones aduaneras
    # def _parse_percepciones_aduaneras(self, root):
    # retenciones = root.find("ss:Worksheet[@ss:Name='Percepciones aduaneras']", ns)
    # table = retenciones.find('ss:Table', ns)

    # def _generate_percepciones(self):
    #     # TODO
    #     pass

    def _generate_retenciones(self):
        for retencion in self.retenciones:
            ret = self.env['l10n_ar.arba.retencion'].create({
                'date': retencion.date,
                'amount': retencion.amount,
            })
            print("Retencion", ret)

    def _generate_retenciones_bancarias(self):
        for retencion in self.retenciones_bancarias:
            ret = self.env['l10n_ar.arba.retencion_bancaria'].create({
                'date': retencion.date,
                'amount': retencion.amount,
            })
            print("Retencion Bancaria", ret)

    def _generate_devoluciones_bancarias(self):
        for devolucion in self.devoluciones_bancarias:
            dev = self.env['l10n_ar.arba.devolucion_bancaria'].create({
                'date': devolucion.date,
                'amount': devolucion.amount,
            })
            print("Devolucion Bancaria", dev)


    # TODO: Percepciones aduaneras
    # def _generate_percepciones_aduaneras(self, root):