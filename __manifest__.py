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
        'sale_management', # Ventas
    ],
    'data': [
        'security/ir.model.access.csv',

        'wizard/arba_afip_views.xml',
        'wizard/arba_report_views.xml',
        
        # Import
        'wizard/import_purchase_excel.xml',
        'wizard/import_purchase_deducciones_arba.xml',
        'wizard/import_sale_compemitidos.xml',
        'wizard/import_sale_compenlinea.xml',
        'wizard/import_sale_pem.xml',
        'wizard/import_sale_excel.xml',
        'wizard/import_bank_bapro.xml',

        # Reports
        'report/basic_report.xml',

        # Menu - Mi Estudio
        'views/company_views.xml',
        'views/import_views.xml',
        'views/firm_views.xml',
        'views/sales_views.xml',

        # Menu
        'views/account_menuitem.xml',

        # Data
        "data/l10n_ar.afip.cuit.apocrifo.csv",
        "data/l10n_latam.document.type.csv",
        "data/account.tax.template.csv",
        "data/product.template.csv",
        "data/product_template.xml"
    ],
    'images': [], # 'static/description/banner.png'
    'application': True,
}
