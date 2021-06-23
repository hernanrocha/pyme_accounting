# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import base64
import xlrd
import datetime

class PurchaseImportBankBapro(models.TransientModel):
    _name = "l10n_ar.import.bank.bapro"
    _description = "Importar extracto bancario Bco. Provincia"

    # TODO: unificar con bank_id
    bank = fields.Selection(
        [("bapro", "Banco Provincia"), ('other', 'Otro')], 
        string="Banco",
        default="bapro",
        required=True)
    
    file = fields.Binary(string="Resumen Bancario")

    def parse(self):
        self.parse_bapro()

    def parse_bapro(self):
        [data] = self.read()

        if not data['file']:
            raise UserError("Debes cargar un archivo valido")
        
        file_content = base64.decodestring(data['file'])

        book = xlrd.open_workbook(file_contents=file_content or b'')
        sheets = book.sheet_names()
        sheet_name = sheets[0]
        print(sheet_name)
        sheet = book.sheet_by_name(sheet_name)

        # TODO: crear un diario por Banco???
        # TODO: Definir tipo de banco la informacion del diario
        bank_journal = self.env['account.journal'].search([('name', '=', 'Banco')])

        # { 'acc_number', 'bank_id' }
        # { show_on_dashboard: True, type: 'bank' }
        # <menuitem id="menu_action_account_bank_journal_form" action="action_new_bank_setting" groups="account.group_account_manager" sequence="1"/>
        # (res.company).setting_init_bank_account_action()
        # model account.setup.bank.manual.config
        # create({ 'new_journal_name': 'Banco HSBC XXXX', 'acc_number': XXXXXXXXXXXX, bank_id })
        # validate()

        statement_data = {
            # TODO: nombrar con el mes
            'name': 'Extracto Bco. Provincia',
            'journal_id': bank_journal.id,
            # TODO: Ultimo dia del mes del extracto
            'date': datetime.date.today(),
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
        }
        print("Statement", statement_data)
        statement = self.env['account.bank.statement'].create(statement_data)

        lines_data = []

        for rowx, row in enumerate(map(sheet.row, range(sheet.nrows)), 1):
            values = []

            if rowx == 2:
                # 'Fecha: 01/07/2019  Hora: 08:51'
                d = datetime.datetime.strptime(row[1].value[7:17], "%d/%m/%Y").date()
                print("Fecha", d)
                statement.write({ 'date': d })
                continue

            if rowx == 4:
                # TODO: primero parsear el extracto bancario y luego obtener el journal o crearlo
                # TODO: si se va a crear uno nuevo, mostrar una advertencia
                # 'Cuenta: 6177-11893/4'
                acc = row[1].value[8:]
                print("Cuenta", acc)
                continue

            # Skip first 3 lines
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
            lines_data.append({
                'date': values[1],
                'payment_ref': values[2],
                'amount': float(values[3]),
                'statement_id': statement.id,
            })

        # Agregar todas las lineas del extracto para aumentar la eficiencia
        print("Creando ", len(lines_data), "lineas")
        self.env['account.bank.statement.line'].create(lines_data)

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
            'target': 'main',
        }
