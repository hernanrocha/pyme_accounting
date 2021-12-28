from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.osv import expression

import logging
import base64

_logger = logging.getLogger(__name__)

class AfipresponsabilityType(models.Model):
    _name = 'afip.responsability.type'
    _description = 'AFIP Responsability Type'
    _order = 'sequence'

    name = fields.Char(
        'Name',
        size=64,
        required=True,
        index=True,
    )
    sequence = fields.Integer(
        'Sequence',
    )
    code = fields.Char(
        'Code',
        size=8,
        required=True,
        index=True,
    )
    active = fields.Boolean(
        'Active',
        default=True
    )
    issued_letter_ids = fields.Many2many(
        'account.document.letter',
        'account_doc_let_responsability_issuer_rel',
        'afip_responsability_type_id',
        'letter_id',
        'Issued Document Letters',
        auto_join=True,
    )
    received_letter_ids = fields.Many2many(
        'account.document.letter',
        'account_doc_let_responsability_receptor_rel',
        'afip_responsability_type_id',
        'letter_id',
        'Received Document Letters',
        auto_join=True,
    )
    # hacemos esto para que, principalmente, monotributistas y exentos no
    # requieran iva, otra forma sería poner el impuesto no corresponde, pero
    # no queremos complicar vista y configuración con un impuesto que no va
    # a aportar nada
    company_requires_vat = fields.Boolean(
        string='Company requires vat?',
        help='Companies of this type will require VAT tax on every invoice '
        'line of a journal that use documents'
    )

    _sql_constraints = [('name', 'unique(name)', 'Name must be unique!'),
                        ('code', 'unique(code)', 'Code must be unique!')]

class ResPartnerIdCategory(models.Model):
    _name = "res.partner.id_category"
    _rec_name = "code"
    _order = "sequence"

    name = fields.Char(string="Nombre")
    code = fields.Char(string="Codigo")
    sequence = fields.Integer(
        default=10,
        required=True,
    )
    afip_code = fields.Integer(
        'AFIP Code',
        required=True
    )

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        domain = []
        if name:
            domain = [
                '|',
                ('code', '=ilike', name + '%'),
                ('name', operator, name)]
            if operator in expression.NEGATIVE_TERM_OPERATORS:
                domain = ['&', '!'] + domain[1:]
        accounts = self.search(domain + args, limit=limit)
        return accounts.name_get()

class ResPartner(models.Model):
    _inherit = 'res.partner'

    # https://github.com/ingadhoc/odoo-argentina/blob/11.0/l10n_ar_account/models/res_partner.py
    gross_income_number = fields.Char(
        'Gross Income Number',
        size=64,
    )
    gross_income_type = fields.Selection([
        ('multilateral', 'Multilateral'),
        ('local', 'Local'),
        ('no_liquida', 'No Liquida'),
    ],
        'Gross Income Type',
    )
    afip_responsability_type_id = fields.Many2one(
        'afip.responsability.type',
        'AFIP Responsability Type',
        auto_join=True,
        index=True,
    )
    main_id_category_id = fields.Many2one(
        string="Main Identification Category",
        comodel_name='res.partner.id_category',
        index=True,
        auto_join=True,
    )

class AccountDocumentLetter(models.Model):
    _name = 'account.document.letter'
    _description = 'Account Document Letter'

    name = fields.Char(
        'Name',
        required=True
    )
    document_type_ids = fields.One2many(
        'account.document.type',
        'document_letter_id',
        'Document Types',
        auto_join=True,
    )
    issuer_ids = fields.Many2many(
        'afip.responsability.type',
        'account_document_letter_responsability_issuer_rel',
        'document_letter_id',
        'afip_responsability_type_id',
        'Issuers',
        auto_join=True,
    )
    receptor_ids = fields.Many2many(
        'afip.responsability.type',
        'account_document_letter_responsability_receptor_rel',
        'document_letter_id',
        'afip_responsability_type_id',
        'Receptors',
        auto_join=True,
    )
    active = fields.Boolean(
        'Active',
        default=True
    )
    taxes_included = fields.Boolean(
        'Taxes Included?',
        help='Documents related to this letter will include taxes on reports',
    )
    # taxes_discriminated = fields.Boolean(
    #     'Taxes Discriminated on Invoices?',
    #     help="If True, the taxes will be discriminated on invoice report.")

    _sql_constraints = [('name', 'unique(name)', 'Name must be unique!'), ]

class AccountDocmentType(models.Model):
    _inherit = 'account.document.type'

    document_letter_id = fields.Many2one(
        'account.document.letter',
        'Document Letter',
        auto_join=True,
        index=True,
    )
    purchase_cuit_required = fields.Boolean(
        help='Verdadero si la declaración del CITI compras requiere informar '
        'CUIT'
    )
    purchase_alicuots = fields.Selection(
        [('not_zero', 'No Cero'), ('zero', 'Cero')],
        help='Cero o No cero según lo requiere la declaración del CITI compras'
    )

    @api.multi
    def get_document_sequence_vals(self, journal):
        vals = super(AccountDocmentType, self).get_document_sequence_vals(
            journal)
        if self.localization == 'argentina':
            vals.update({
                'padding': 8,
                'implementation': 'no_gap',
                'prefix': "%04i-" % (journal.point_of_sale_number),
            })
        return vals

    @api.multi
    def get_taxes_included(self):
        """
        In argentina we include taxes depending on document letter
        """
        self.ensure_one()
        if self.localization == 'argentina':
            if self.document_letter_id.taxes_included:
                # solo incluir el IVA, el resto se debe discriminar
                # return self.env['account.tax'].search([])
                return self.env['account.tax'].search(
                    [('tax_group_id.tax', '=', 'vat'),
                     ('tax_group_id.type', '=', 'tax')])
            # included_tax_groups = (
            #     self.document_letter_id.included_tax_group_ids)
            # if included_tax_groups:
            #     return self.env['account.tax'].search(
            #         [('tax_group_id', 'in', included_tax_groups.ids)])
        else:
            return super(AccountDocmentType, self).get_taxes_included()

class AccountMove(models.Model):
    _inherit = "account.move"

    document_type_id = fields.Many2one(
        'account.document.type',
        'Document Type',
        copy=False,
        auto_join=True,
        # states={'posted': [('readonly', True)]},
        index=True,
    )
    document_number = fields.Char(string="Numero de Cbte")