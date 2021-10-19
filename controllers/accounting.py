from odoo import http
from odoo.http import request

# Inspirado en el banner de accounting de Odoo
# https://github.com/odoo/odoo/blob/a7f7233e0eae8ee101d745a9813cba930fd03dcb/addons/account/controllers/onboarding.py
# https://github.com/odoo/odoo/blob/a7f7233e0eae8ee101d745a9813cba930fd03dcb/addons/account/views/account_onboarding_templates.xml

class AccountDashboardController(http.Controller):

    @http.route('/pyme_accounting/account_dashboard', auth='user', type='json')
    def account_invoice_onboarding(self):
        # company = request.env.company

        # if not request.env.is_admin() or \
        #         company.account_invoice_onboarding_state == 'closed':
        #     return {}

        return {
            # 'html': request.env.ref('account.account_invoice_onboarding_panel')._render({
            #     'company': company,
            #     'state': company.get_and_update_account_invoice_onboarding_state()
            # })
            # 'html': '<div>ESTO ES UN BANNER!!!</div>'
        }