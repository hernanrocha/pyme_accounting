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

class AccountInvoice(models.Model):
    _inherit = "account.invoice"

    amount_total_signed = fields.Float(string="Total Con Signo")
    amount_untaxed_signed = fields.Float(string="Monto Imponible Con Signo")
    amount_total = fields.Float(string="Total")
    amount_untaxed = fields.Float(string="Monto Imponible")

class ResPartner(models.Model):
    _inherit = "res.partner"

    main_id_number = fields.Char(default="20372183404")

    # l10n_ar_account_withholding
    arba_alicuot_ids = fields.One2many(
        'res.partner.arba_alicuot',
        'partner_id',
        'Alícuotas PERC-RET',
    )

# ingadhoc/odoo-argentina - l10n_ar_account_withholding/models/res_partner.py
class ResPartnerArbaAlicuot(models.Model):
    # TODO rename model to res.partner.tax or similar
    _name = "res.partner.arba_alicuot"
    _order = "to_date desc, from_date desc, tag_id, company_id"

    partner_id = fields.Many2one(
        'res.partner',
        required=True,
        ondelete='cascade',
    )
    tag_id = fields.Many2one(
        'account.account.tag',
        domain=[('applicability', '=', 'taxes')],
        required=True,
        change_default=True,
    )
    company_id = fields.Many2one(
        'res.company',
        required=True,
        ondelete='cascade',
        default=lambda self: self.env.user.company_id,
    )
    from_date = fields.Date(
    )
    to_date = fields.Date(
    )
    numero_comprobante = fields.Char(
    )
    codigo_hash = fields.Char(
    )
    alicuota_percepcion = fields.Float(
    )
    alicuota_retencion = fields.Float(
    )
    grupo_percepcion = fields.Char(
    )
    grupo_retencion = fields.Char(
    )
    withholding_amount_type = fields.Selection([
        ('untaxed_amount', 'Untaxed Amount'),
        ('total_amount', 'Total Amount'),
    ],
        'Base para retenciones',
        help='Base amount used to get withholding amount',
    )
    regimen_percepcion = fields.Char(
        size=3,
        help="Utilizado para la generación del TXT para SIRCAR.\n"
        "Tipo de Régimen de Percepción (código correspondiente según "
        "tabla definida por la jurisdicción)"
    )
    regimen_retencion = fields.Char(
        size=3,
        help="Utilizado para la generación del TXT para SIRCAR.\n"
        "Tipo de Régimen de Retención (código correspondiente según "
        "tabla definida por la jurisdicción)"
    )
    api_codigo_articulo_retencion = fields.Selection([
        ('001', '001: Art.1 - inciso A - (Res. Gral. 15/97 y Modif.)'),
        ('002', '002: Art.1 - inciso B - (Res. Gral. 15/97 y Modif.)'),
        ('003', '003: Art.1 - inciso C - (Res. Gral. 15/97 y Modif.)'),
        ('004', '004: Art.1 - inciso D pto.1 - (Res. Gral. 15/97 y Modif.)'),
        ('005', '005: Art.1 - inciso D pto.2 - (Res. Gral. 15/97 y Modif.)'),
        ('006', '006: Art.1 - inciso D pto.3 - (Res. Gral. 15/97 y Modif.)'),
        ('007', '007: Art.1 - inciso E - (Res. Gral. 15/97 y Modif.)'),
        ('008', '008: Art.1 - inciso F - (Res. Gral. 15/97 y Modif.)'),
        ('009', '009: Art.1 - inciso H - (Res. Gral. 15/97 y Modif.)'),
        ('010', '010: Art.1 - inciso I - (Res. Gral. 15/97 y Modif.)'),
        ('011', '011: Art.1 - inciso J - (Res. Gral. 15/97 y Modif.)'),
        ('012', '012: Art.1 - inciso K - (Res. Gral. 15/97 y Modif.)'),
        ('013', '013: Art.1 - inciso L - (Res. Gral. 15/97 y Modif.)'),
        ('014', '014: Art.1 - inciso LL pto.1 - (Res. Gral. 15/97 y Modif.)'),
        ('015', '015: Art.1 - inciso LL pto.2 - (Res. Gral. 15/97 y Modif.)'),
        ('016', '016: Art.1 - inciso LL pto.3 - (Res. Gral. 15/97 y Modif.)'),
        ('017', '017: Art.1 - inciso LL pto.4 - (Res. Gral. 15/97 y Modif.)'),
        ('018', '018: Art.1 - inciso LL pto.5 - (Res. Gral. 15/97 y Modif.)'),
        ('019', '019: Art.1 - inciso M - (Res. Gral. 15/97 y Modif.)'),
        ('020', '020: Art.2 - (Res. Gral. 15/97 y Modif.)'),
    ],
        string='Código de Artículo/Inciso por el que retiene',
    )
    api_codigo_articulo_percepcion = fields.Selection([
        ('021', '021: Art.10 - inciso A - (Res. Gral. 15/97 y Modif.)'),
        ('022', '022: Art.10 - inciso B - (Res. Gral. 15/97 y Modif.)'),
        ('023', '023: Art.10 - inciso D - (Res. Gral. 15/97 y Modif.)'),
        ('024', '024: Art.10 - inciso E - (Res. Gral. 15/97 y Modif.)'),
        ('025', '025: Art.10 - inciso F - (Res. Gral. 15/97 y Modif.)'),
        ('026', '026: Art.10 - inciso G - (Res. Gral. 15/97 y Modif.)'),
        ('027', '027: Art.10 - inciso H - (Res. Gral. 15/97 y Modif.)'),
        ('028', '028: Art.10 - inciso I - (Res. Gral. 15/97 y Modif.)'),
        ('029', '029: Art.10 - inciso J - (Res. Gral. 15/97 y Modif.)'),
        ('030', '030: Art.11 - (Res. Gral. 15/97 y Modif.)'),
    ],
        string='Código de artículo Inciso por el que percibe',
    )
    api_articulo_inciso_calculo_selection = [
        ('001', '001: Art. 5º 1er. párrafo (Res. Gral. 15/97 y Modif.)'),
        ('002', '002: Art. 5º inciso 1)(Res. Gral. 15/97 y Modif.)'),
        ('003', '003: Art. 5° inciso 2)(Res. Gral. 15/97 y Modif.)'),
        ('004', '004: Art. 5º inciso 4)(Res. Gral. 15/97 y Modif.)'),
        ('005', '005: Art. 5° inciso 5)(Res. Gral. 15/97 y Modif.)'),
        ('006', '006: Art. 6º inciso a)(Res. Gral. 15/97 y Modif.)'),
        ('007', '007: Art. 6º inciso b)(Res. Gral. 15/97 y Modif.)'),
        ('008', '008: Art. 6º inciso c)(Res. Gral. 15/97 y Modif.)'),
        ('009', '009: Art. 12º)(Res. Gral. 15/97 y Modif.)'),
        ('010', '010: Art. 6º inciso d)(Res. Gral. 15/97 y Modif.)'),
        ('011', '011: Art. 5° inciso 6)(Res. Gral. 15/97 y Modif.)'),
        ('012', '012: Art. 5° inciso 3)(Res. Gral. 15/97 y Modif.)'),
        ('013', '013: Art. 5° inciso 7)(Res. Gral. 15/97 y Modif.)'),
        ('014', '014: Art. 5° inciso 8)(Res. Gral. 15/97 y Modif.)'),
    ]
    api_articulo_inciso_calculo_percepcion = fields.Selection(
        api_articulo_inciso_calculo_selection,
        string='Artículo/Inciso para el cálculo percepción',
    )
    api_articulo_inciso_calculo_retencion = fields.Selection(
        api_articulo_inciso_calculo_selection,
        string='Artículo/Inciso para el cálculo retención',
    )

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    withholding_base_amount = fields.Float(string="Monto Imponible")