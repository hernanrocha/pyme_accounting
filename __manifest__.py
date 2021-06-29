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
    'depends': [
        # Odoo Base Modules
        'base',            # Base
        'account',         # Contabilidad
        'purchase',        # Compras
        'l10n_ar',         # Localizacion Argentina
        # 'l10n_latam_base',
        # 'l10n_latam_invoice_document',
        'sale_management', # Ventas
        # 'web'            # Web Backend
        # 'portal'         # Web Login

        # Localizacion Argentina         https://github.com/ctmil/odoo-argentina.git@14.0
        # 'l10n_ar_reports',             # Reportes Argentinos
        # 'l10n_ar_account_iva_digital', # IVA Digital

        # Mantenimiento
        # Session Manager
    ],
    'data': [
        # Security Records
        'security/ir.model.access.csv',
        'security/record_rules.xml',

        'wizard/arba_afip_views.xml',
        'wizard/arba_report_views.xml',
        
        # Import
        'wizard/import_purchase_excel.xml',
        'wizard/import_purchase_deducciones_arba.xml',
        'wizard/import_purchase_comprecibidos.xml',
        'wizard/import_sale_compemitidos.xml',
        'wizard/import_sale_compenlinea.xml',
        'wizard/import_sale_pem.xml',
        'wizard/import_sale_excel.xml',
        'wizard/import_bank_bapro.xml',

        # Reports
        'report/basic_report.xml',
        # 'views/report_iibb.xml', # Asientos contables relacionados con IIBB

        # Menu - Mi Estudio
        'views/company_views.xml',
        'views/import_views.xml',
        'views/firm_views.xml',
        'views/sales_views.xml',

        # Menu
        'views/account_menuitem.xml',

        # Cross-Company Data
        "data/l10n_ar.afip.cuit.apocrifo.csv",
        "data/l10n_latam.document.type.csv",
        "data/account.tax.template.csv",

        # Company Dependent Data
        # TODO: si es necesario, se debe hacer por empresa, o crear primero los impuestos.
        # El producto no tiene company_id, pero los impuestos no estan creados aun
        # "data/product.template.csv",
        # "data/product_template.xml"
    ],
    'images': [], # 'static/description/banner.png'
    'qweb': [
        'static/src/xml/base.xml'
    ],
    'application': True,
    # 'active': True, # This indicates whether this module must install automatically or not.
    # 'pre_init_hook': 'pre_init', takes a cursor as its only argument, this function is executed prior to the module’s installation.
}
