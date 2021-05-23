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
        'sale_management'
    ],
    'data': [
        # 'security/hr_payroll_security.xml',
        'security/ir.model.access.csv',
        'wizard/arba_afip_views.xml',
        'wizard/arba_report_views.xml',
        'wizard/afip_import_sales_views.xml',
        'wizard/import_sale_pem.xml',
        'views/company_views.xml',
        'views/import_views.xml',
        'views/firm_views.xml',
        'views/account_menuitem.xml'
    ],
    'images': [], # 'static/description/banner.png'
    'application': True,
}
