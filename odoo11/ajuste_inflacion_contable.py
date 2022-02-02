from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta

import logging

_logger = logging.getLogger(__name__)

# Basado en ADHOC 
# https://github.com/ingadhoc/odoo-argentina-ee/blob/13.0/l10n_ar_account_tax_settlement/wizards/inflation_adjustment.py

# TODO: Agregar categoria en el asiento para poder luego filtrar
# por valor historico y por el valor ajustado
# TODO: Tener en cuenta el año/periodo fiscal actual
# TODO: reutilizar el mismo asiento, y permitir confirmarlo
# TODO: para tipo anual, agrupar ajuste por cuenta

class Account(models.Model):
    _inherit = "account.account"

    partida_monetaria = fields.Boolean(string="Partida Monetaria",
        default=True, help="Las Partidas Monetarias no son tenidas en cuenta durante el ajuste por inflación")

class InflationAdjustmentIndex(models.Model):
    _name = 'inflation.adjustment.index'
    _description = 'Inflation Adjustment Index'
    _order = 'date desc'
    _rec_name = 'date'

    date = fields.Date(
        string="Fecha",
        required=True,
    )
    value = fields.Float(
        string="Índice",
        required=True,
        digits=(12,4),
    )
    xml_id = fields.Char(compute='_compute_xml_id', string="External ID")

    @api.depends()
    def _compute_xml_id(self):
        res = self.get_external_id()
        for action in self:
            action.xml_id = res.get(action.id)

    @api.model
    def find(self, date):
        """ :return: recordset (empty if not found)
        """
        range = self.get_dates(date)
        return self.search([
            ('date', '>=', range.get('date_from')),
            ('date', '<=', range.get('date_to')),
        ], limit=1)

    @api.constrains('date')
    def check_date_unique(self):
        for rec in self:
            repeated = self.find(rec.date)
            if len(repeated) > 1:
                rec_date = fields.Date.from_string(rec.date)
                raise ValidationError(_(
                    "Ya existe un indice para el periodo %s %s. Solo"
                    " puedes tener un indice de inflación por mes" % (
                        rec_date.strftime("%B"), rec_date.year)))

    @api.constrains('date')
    def check_day(self):
        for rec in self:
            date = fields.Date.from_string(rec.date)
            if date.day != 1:
                raise ValidationError(_(
                    "El indice debe comenzar el primer día de cada mes"))

    @api.constrains('date')
    def check_xml_id(self):
        """ always create the xml_id when create a new record of this model.
        """
        if self.env.context.get('install_mode', False):
            return

        model_data = self.env['ir.model.data']
        for rec in self.filtered(lambda x: not x.xml_id):
            date = fields.Date.from_string(rec.date)
            metadata = {
                'name': 'index_%02d_%s' % (date.month, date.year),
                'model': self._name,
                'module': 'l10n_ar_account_tax_settlement',
                'res_id': rec.id,
                'noupdate': True,
            }
            model_data.create(metadata)

    def get_dates(self, date=None):
        """ Get the begining and end date of a period.
        if self is set then will return the index of the period.
        If not then will take into account the date given to
        compute the begin/end of the month where this date belong
        :return: dictionary of of the form
            {'date_from': 'YYYY-MM-DD' ,'date_to': 'YYYY-MM-DD'}
        """
        if self:
            self.ensure_one()
            date = self.date

        date_from = fields.Date.from_string(date) + relativedelta(day=1)
        # TODO NOT sure is this is ok
        date_to = date_from + relativedelta(months=1, days=-1)
        res = {
            'date_from': fields.Date.to_string(date_from),
            'date_to': fields.Date.to_string(date_to),
        }
        return res

class InflationAdjustment(models.Model):
    _name = 'inflation.adjustment'
    _description = 'Inflation adjustment'

    name = fields.Char(string="Nombre")
    state = fields.Selection(
        selection=[('draft', 'Borrador'), ('presented', 'Confirmado'), ('cancel', 'Cancelado')],
        string="Estado", required=True, default='draft')
    date_from = fields.Date(string="Fecha Desde", required=True)
    date_to = fields.Date(string="Fecha Hasta", required=True)
    tipo = fields.Selection(
        selection=[('mensual', 'Mensual'), ('anual', 'Anual')],
        string="Tipo de Ajuste", required=True, default="anual")
    journal_id = fields.Many2one(
        'account.journal',
        string="Diario",
        domain=[('type', '=', 'general')],
        required=True
    )
    company_id = fields.Many2one('res.company', required=True, readonly=True, string="Empresa",
        default=lambda self: self.env['res.company']._company_default_get('inflation.adjustment'))
    account_id = fields.Many2one(
        'account.account',
        string="Cuenta RECPAM",
        domain=[('deprecated', '=', False)],
        required=True,
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        'Cuenta Analítica',
    )
    start_index = fields.Float(compute='_compute_index')
    end_index = fields.Float(compute='_compute_index')
    open_closure_entry = fields.Selection(
         [('yes', 'Si'),
          ('no', 'No')],
        string="Ha realizado asientos de cierre/apertura?",
        default='no',
        help="Si usted ha realizado los asientos de cierre/apertura debe"
        " indicarnos cuales son para poder excluir los mismos en el cálculo."
    )
    closure_move_id = fields.Many2one('account.move', string="Asiento de cierre")
    open_move_id = fields.Many2one('account.move', string="Asiento de apertura")
    adjust_move_id = fields.Many2one('account.move', readonly=True, string="Asiento de ajuste")
    adjust_line_ids = fields.One2many('account.move.line', readonly=True, related="adjust_move_id.line_ids")

    @api.depends('date_from', 'date_to')
    def _compute_index(self):
        """ Update index when dates has been updated, raise a warning when
        the index period does not exist
        """
        index_model = self.env['inflation.adjustment.index']
        if self.date_from:
            self.start_index = index_model.find(self.date_from).value
        if self.date_to:
            self.end_index = index_model.find(self.date_to).value

    def get_periods(self, start_date=None, end_date=None):
        """ return a list of periods where the inflation adjustment will be
        applied.
        If not found index in any of the months in the selected period then
        a UserError exception will be thrown
        :return: [{
          'date_from': <first_date_month>, (for first period date_from date)
          'date_to': <last_date_month>,
          'factor': end_index / <month_index>,
          'index': recordset('inflation.adjustment.index')}, ...]
        """
        if self:
            self.ensure_one()
            start_date = self.date_from
            end_date = self.date_to
            end_index = self.end_index
        else:
            end_index = self.env['inflation.adjustment.index'].find(end_date).value

        if not start_date or not end_date:
            raise UserError(_(
                'Por favor indique el rango de fecha de inicio y fin'))

        res = []
        cur_date = start_date
        end = end_date

        indexes = self.env['inflation.adjustment.index'].search([])

        while cur_date < end:
            # cur_date de tipo datetime.Date
            cur_date_date = fields.Date.from_string(cur_date)

            date_to = fields.Date.to_string(cur_date_date + relativedelta(months=1, days=-1))
            if date_to > end:
                date_to = end

            index = indexes.filtered(
                lambda x: x.date >= cur_date and x.date < date_to)
            if not index:
                raise UserError(_(
                    'El asiento de ajuste por inflación no puede ser generado'
                    ' ya que hace falta el indice de ajuste para el periodo'
                    ' %s %s' % (
                        cur_date.strftime("%B"), cur_date.year)))

            res.append({
                'date_from': cur_date,
                'date_to': date_to,
                'index': index,
                'factor': (end_index / index.value) - 1.0,
            })
            cur_date = fields.Date.to_string(cur_date_date + relativedelta(months=1, day=1))
        return res

    def get_move_line_domain(self):
        res = [
            ('account_id.partida_monetaria', '=', False),
            ('company_id', '=', self.company_id.id),
            ('move_id.state', '=', 'posted'),
        ]
        if self.open_move_id:
            res += [('move_id', '!=', self.open_move_id.id)]
        if self.closure_move_id:
            res += [('move_id', '!=', self.closure_move_id.id)]
        return res

    def get_recpam_adjustment(self, adj_diff, name):
        return {
            'account_id': self.account_id.id,
            'name': name,
            'debit' if adj_diff < 0 else 'credit': abs(adj_diff),
            'date_maturity': self.date_to,
            'analytic_account_id': self.analytic_account_id.id,
        }

    def confirm(self):
        """ Search all the related account.move.line and will create the
        related inflation adjustment journal entry for the specification.
        """
        account_move_line = self.env['account.move.line']
        adjustment_total = {'debit': 0.0, 'credit': 0.0}
        lines = []

        # Generate account.move.line adjustment for start of the period
        domain = self.get_move_line_domain()
        domain += [
            ("account_id.user_type_id.include_initial_balance", '=', True),
            ('date', '<', self.date_from)]
        init_data = account_move_line.read_group(
            domain, ['account_id', 'balance'], ['account_id'],
        )
        before_date_from = fields.Date.from_string(self.date_from) + relativedelta(months=-1)
        before_date_from = fields.Date.to_string(before_date_from)
        # NOTE: find() recibe de tipo str
        before_index = self.env['inflation.adjustment.index'].find(before_date_from)

        # NOTE: Ambos son de tipo str
        periods = self.env['inflation.adjustment'].get_periods(before_date_from, self.date_from)

        initial_factor = (self.end_index / before_index.value) - 1.0

        # TODO: Revisar que esto este funcionando bien.
        # Se utiliza solo para cuentas que corresponden al balance inicial (Ganancias, etc)
        # https://github.com/odoo/odoo/blob/11.0/addons/account/data/data_account_type.xml
        for line in init_data:
            adjustment = line.get('balance') * initial_factor
            if self.company_id.currency_id.is_zero(adjustment):
                continue
            else:
                adjustment = self.company_id.currency_id.round(adjustment)
            lines.append({
                'account_id': line.get('account_id')[0],
                'name': 'Ajuste por inflación cuentas al inicio ({} * {:.2f}%)'.format(
                    line.get('balance'), 
                    initial_factor * 100.0),
                'date_maturity': before_date_from,
                'debit' if adjustment > 0 else 'credit': abs(adjustment),
                'analytic_account_id': self.analytic_account_id.id,
            })
            adjustment_total[
                'debit' if adjustment > 0 else 'credit'] += abs(adjustment)

        # Get period month list
        periods = self.get_periods()

        # Recorrer cada mes para realizar el ajuste correspondiente
        for period in periods:
            # Buscar account.move.lines durante ese mes
            domain = self.get_move_line_domain()
            domain += [('date', '>=', period.get('date_from')),
                       ('date', '<=', period.get('date_to'))]
            data = account_move_line.read_group(
                domain, ['account_id', 'balance'], ['account_id', 'date'])
            date_from = period.get('date_from')
            
            # Realizar el ajuste para cada cuenta
            for line in data:
                adjustment = line.get('balance') * period.get('factor')
                if self.company_id.currency_id.is_zero(adjustment):
                    continue
                
                adjustment = self.company_id.currency_id.round(adjustment)
                lines.append({
                    'account_id': line.get('account_id')[0],
                    'name': 'Ajuste por inflación {} ({} * {:.2f}%)'.format(
                        fields.Date.from_string(date_from).strftime('%m-%Y'),
                        line.get('balance'),
                        period.get('factor') * 100.0),
                    'date_maturity': period.get('date_from'),
                    'debit' if adjustment > 0 else 'credit': abs(adjustment),
                    'analytic_account_id': self.analytic_account_id.id,
                })
                adjustment_total[
                    'debit' if adjustment > 0 else 'credit'] += abs(adjustment)

            # Si aplica, realizar el ajuste RECPAM mensual
            # TODO: separar en varios asientos
            if self.tipo == 'mensual':
                adj_diff = adjustment_total.get('debit', 0.0) - adjustment_total.get(
                    'credit', 0.0)

                # No generar ajuste en meses que no es necesario
                if self.company_id.currency_id.is_zero(adj_diff):
                    continue

                mes = fields.Date.from_string(period.get('date_from')).strftime('%m-%Y')
                lines.append(self.get_recpam_adjustment(adj_diff, 
                    'Ajuste por inflación Mensual {}'.format(mes)))
                
                adjustment_total['credit'] = 0
                adjustment_total['debit'] = 0

        if not lines:
            raise UserError(_(
                "No hemos encontrado ningún asiento contable asociado al"
                " periodo seleccionado."
            ))

        # Generate total amount adjustment line
        if self.tipo == 'anual':
            adj_diff = adjustment_total.get('debit', 0.0) - adjustment_total.get(
                'credit', 0.0)

            lines.append(self.get_recpam_adjustment(adj_diff, 
                'Ajuste por inflación Global {} / {}'.format(
                    fields.Date.from_string(self.date_from).strftime('%m-%Y'),
                    fields.Date.from_string(self.date_to).strftime('%m-%Y')
                )))
            
        # TODO: Borrar asiento anterior
        # TODO: Solo generar aca para anual
        # Generate account.move
        self.adjust_move_id = self.env['account.move'].create({
            'journal_id': self.journal_id.id,
            'date': self.date_to,
            'ref': 'Ajuste por inflación {} / {}'.format(
                fields.Date.from_string(self.date_from).strftime('%m-%Y'),
                fields.Date.from_string(self.date_to).strftime('%m-%Y')
            ),
            'line_ids': [(0, 0, line_data) for line_data in lines],
        })