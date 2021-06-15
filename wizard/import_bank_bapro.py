# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import base64
import xlrd
import datetime

class PurchaseImportBankBapro(models.TransientModel):
    _name = "l10n_ar.import.bank.bapro"
    _description = "Importar extracto bancario Bco. Provincia"

    file = fields.Binary(string="Resumen (*.xls)")

    def parse(self):
        [data] = self.read()

        if not data['file']:
            raise UserError("Debes cargar un archivo valido")
        
        file_content = base64.decodestring(data['file'])

        book = xlrd.open_workbook(file_contents=file_content or b'')
        sheets = book.sheet_names()
        sheet_name = sheets[0]
        print(sheet_name)
        sheet = book.sheet_by_name(sheet_name)

        bank_journal = self.env['account.journal'].search([('name', '=', 'Banco')])

        statement = self.env['account.bank.statement'].create({
            'name': 'Extracto Bco. Provincia',
            'journal_id': bank_journal.id,
            'date': datetime.date.today(),
            'accounting_date': datetime.date.today(),
            # TODO: obtener estos valores
            'balance_start': 0,
            'balance_end_real': 0,
            #                 Importe     Saldo
            # 1er asiento     232.340,00   -41.499,33
            # Ultimo            X         -261.445,59

            # Saldo inicial: saldo(0) - import(0)        = -273.839,33
            # Saldo final:   saldo(n)                    = -261.445,59
            # Balance:       saldo_final - saldo_inicial =   12.393,74

            # En el dashboard:
            # - Saldo en el Libro Mayor    $ 12.393,74
            # - Último extracto          $ -261.445,59
        })

        for rowx, row in enumerate(map(sheet.row, range(sheet.nrows)), 1):
            values = []

            # Skip first 5 lines
            if rowx < 6:
                print("Skipping line", rowx)
                continue

            # Parse cells in row
            for colx, cell in enumerate(row, 1):

                if cell.ctype is xlrd.XL_CELL_NUMBER:
                    is_float = cell.value % 1 != 0.0
                    values.append(str(cell.value) if is_float else str(int(cell.value))
                    )
                elif cell.ctype is xlrd.XL_CELL_DATE:
                    dt = datetime.datetime(*xlrd.xldate.xldate_as_tuple(cell.value, book.datemode))
                    values.append(dt)
                elif cell.ctype is xlrd.XL_CELL_BOOLEAN:
                    values.append(u'True' if cell.value else u'False')
                elif cell.ctype is xlrd.XL_CELL_ERROR:
                    raise ValueError(
                        _("Invalid cell value at row %(row)s, column %(col)s: %(cell_value)s") % {
                            'row': rowx,
                            'col': colx,
                            'cell_value': xlrd.error_text_from_code.get(cell.value, _("unknown error code %s", cell.value))
                        }
                    )
                else:
                    values.append(cell.value)

            print(values)

            # Detect end of file
            # TODO: Revisar cantidad de lineas correctas ()
            if values[3] == '':
                print("Reached EOF")
                break

            # 0 Vacio, 1 Fecha, 2 Descripcion, 3 Monto, 4 Acumulado
            # Create statement line
            statement.line_ids.create({
                'date': values[1],
                'payment_ref': values[2],
                'amount': float(values[3]),
                'statement_id': statement.id,
            })

        # Tipos de movimiento encontrados:
        # - AFIP RE.R4289L234179002 ID.30627000983	
        # - ARBA RE.I M CTACTE 1903 ID.0760077518
        # - BIP CR TR 19/06-C.000795039860 ORI:0014-01-628100508092
        # - BIP DB TR 07/06-C.000598045743 DES:0014-03-617705310369 CUIL/CUIT: 27403976437
        # - BIP DB.TR.05/06-C.561955 DES:0011-20-25203751204244 DOC/CUIL/CUIT:
        # - CHEQUE POR VENTANILLA 008218093	
        # - IMPUESTO CREDITO -LEY 25413
        # - IMPUESTO DEBITO -LEY 25413
        # - IMPUESTO I.BRUTOS - PERCEPCION
        # - IMPUESTO SELLOS	
        # - RETENCION ARBA
        # - ZOO LOGIC SA RE.FA0001-00521742 ID.03929
        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'account.bank.statement',
            'res_id': statement.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'primary',
        }
