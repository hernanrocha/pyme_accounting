# -*- coding:utf-8 -*-

{
    'name': 'PYME Contabilidad',
    'category': 'Accounting',
    'version': '14.0.0.0.1',
    'sequence': 1,
    'author': 'Hernan Rocha',
    'summary': 'PYME Contabilidad para Odoo 14 Community Edition',
    # 'live_test_url': 'https://www.youtube.com/watch?v=0kaHMTtn7oY',
    'description': "",
    # 'website': 'https://www.odoomates.tech',
    'external_dependencies': { 
        "python": [], 
        "bin": []
    },
    'depends': [
        # Odoo Base Modules
        'base',            # Base
        'account',         # Contabilidad
        'purchase',        # Compras
        'l10n_ar',         # Localizacion Argentina
        # 'l10n_latam_base',
        # 'l10n_latam_invoice_document',
        'sale_management', # Ventas
        'web',             # Web Backend
        # 'portal'         # Web Login

        # 
        # 'report_xlsx', # Reporte XLSX

        # Localizacion Argentina         https://github.com/ctmil/odoo-argentina.git@14.0
        # 'l10n_ar_account_vat_ledger',  # IVA Compras/Ventas
        # 'l10n_ar_account_iva_digital', # IVA Digital
        # 'account_move_tax',            # Impuestos

        # Mantenimiento
        # Session Manager

        ### PYTHON pip install python-json-logger
    ],
    'assets': {
        'web._assets_primary_variables': [
            # 'pyme_accounting/static/src/scss/primary_variables.scss'
        ]
    },
    'data': [
        # # https://github.com/odoo/odoo/blob/bbc338438518bbb7d0e9ad1a313e872f95a36870/addons/web/static/src/js/views/list/list_renderer.js
        # # Web
        # 'views/web.xml',

        # # CTMIL Odoo-Argentina. Modulos account_move_tax, vat_ledger, iva_digital
        # # TODO: Mover a un modulo diferente
        # 'iva/move_view.xml',
        # 'iva/account_vat_report_view.xml',
        # 'iva/iva_2002.xml',

        # Security Records
        'security/ir.model.access.csv',
        # 'security/record_rules.xml',

        # 'wizard/arba_afip_views.xml',
        # 'wizard/arba_report_views.xml',
        
        # # Empresas - Contabilidad
        # 'views/account_views.xml',
        # 'views/account_move_views.xml',
        # 'views/product_views.xml',
        # 'views/report_monotributo.xml',

        # # Empresas - Importar
        # 'wizard/import_purchase_excel.xml',
        # 'wizard/import_purchase_deducciones_arba.xml',
        # 'wizard/import_purchase_comprecibidos.xml',
        # 'wizard/import_purchase_rg3685.xml',
        # 'wizard/import_sale_compemitidos.xml',
        # 'wizard/import_sale_compenlinea.xml',
        # 'wizard/import_sale_pem.xml',
        # 'wizard/import_sale_excel.xml',
        # 'wizard/import_sale_rg3685.xml',
        # 'wizard/import_afip_retenciones.xml',
        # 'wizard/import_bank_bapro.xml',

        # 'templates/basic.xml',

        # # Reports
        # 'report/basic_report.xml',
        # 'report/report_iva_f2002.xml',
        # 'report/monotributo.xml',
        # # 'views/report_iibb.xml', # Asientos contables relacionados con IIBB

        # # Menu - Mi Estudio
        # 'views/company_views.xml',
        # 'views/import_views.xml',
        # 'views/firm_views.xml',
        # 'views/sales_views.xml',
        # 'views/afip_activities.xml',
        # 'views/afip_apocrifos.xml',

        # # Menu
        # 'views/account_menuitem.xml',

        # # Cross-Company Data
        # "data/nano.monotributo.categoria.csv",
        # "data/l10n_ar.afip.actividad.csv",
        # "data/l10n_ar.afip.cuit.apocrifo.csv",
        # "data/l10n_latam.document.type.csv",
        # "data/account.tax.template.csv",
        # "data/account.account.template.csv",
        # "data/account_tax_template_data.xml",

        # # Company Dependent Data
        # # TODO: si es necesario, se debe hacer por empresa, o crear primero los impuestos.
        # # El producto no tiene company_id, pero los impuestos no estan creados aun
        # # "data/product.template.csv",
        # # "data/product_template.xml"

        # ODOO 11
        'odoo11/table_views.xml',
        'odoo11/account_menuitem.xml',

        # ODOO 11: Data de otros modulos
        'odoo11/data/account_account_tag.xml',
        'odoo11/data/afip_responsability_type.xml',
        'odoo11/data/res_partner_id_category_data.xml',
        'odoo11/data/account_document_letter.xml',
        'odoo11/data/account.document.type.csv',
    ],
    'images': [], # 'static/description/banner.png'
    'qweb': [
        'static/src/xml/base.xml',
    ],
    'application': True,
    # 'active': True, # This indicates whether this module must install automatically or not.
    # 'pre_init_hook': 'pre_init', takes a cursor as its only argument, this function is executed prior to the module’s installation.
    # 'auto_install': True
}
