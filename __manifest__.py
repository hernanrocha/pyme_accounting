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
        'base',
        'account',
        'purchase',
        'sale_management',
        'multi_step_wizard', # https://github.com/OCA/server-ux@14.0
        'l10n_ar',
        'l10n_ar_afipws_fe'
    ],
    'data': [
        'security/ir.model.access.csv',

        'wizard/arba_afip_views.xml',
        'wizard/arba_report_views.xml',
        
        # Import
        'wizard/import_purchase_excel.xml',
        'wizard/import_sale_compemitidos.xml',
        'wizard/import_sale_compenlinea.xml',
        'wizard/import_sale_pem.xml',
        'wizard/import_sale_webservice.xml',
        'wizard/import_sale_excel.xml',

        # Reports
        'report/basic_report.xml',

        # AFIP
        'wizard/afip_certificates_views.xml',

        'views/company_views.xml',
        'views/import_views.xml',
        'views/firm_views.xml',
        'views/sales_views.xml',

        # Menu
        'views/account_menuitem.xml',

        # Data
        "data/l10n_ar.afip.cuit.apocrifo.csv",
        "data/l10n_latam.document.type.csv",
        "data/product.template.csv",
        "data/product_template.xml"
    ],
    'images': [], # 'static/description/banner.png'
    'application': True,
}
