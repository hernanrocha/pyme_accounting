odoo.define('client_act.sale_cust', function (require) {
'use strict';
var AbstractAction = require('web.AbstractAction');
var core = require('web.core');
var rpc = require('web.rpc');
var QWeb = core.qweb;
var SaleCustom = AbstractAction.extend({
    template: 'template_monotributo_anual',
    events: {},
    init: function(parent, action) {
        this._super(parent, action);
    },
    start: function() {
        var self = this;
        alert("Hello")
        self.load_data();
    },
    load_data: function () {
        var self = this;
        // self._rpc({
        //     model: 'sale.custom',
        //     method: 'get_sale_order',
        //     args: [],
        // }).then(function(datas) {
        //     console.log("dataaaaaa", datas)
        //     self.$('.table_view').html(QWeb.render('template_monotributo_anual', {
        //                 report_lines : datas,
        //     }));
        // });
    },
});
core.action_registry.add("report_monotributo_anual", SaleCustom);
return SaleCustom;
});

// from odoo import models, fields, api
// class SaleCustom(models.Model):
//    _name = 'sale.custom'
//    @api.model
//    def get_sale_order(self):
//        ret_list = []
//        req = (
//                    "SELECT sale_order.name, rp.name AS customer, sale_order.amount_total, sale_order.state "
//                    "FROM sale_order "
//                    "Join res_partner rp ON (sale_order.partner_id=rp.id)")
//        self.env.cr.execute(req)
//        for rec in self.env.cr.dictfetchall():
//            ret_list.append(rec)
//        return ret_list

odoo.define('monotributo.form.subview', function (require) {
    "use strict";
    
    var viewRegistry = require('web.view_registry');
    var FormView = require('web.FormView');
    var FormController = require('web.FormController')

    // Override /web/static/src/js/views/basic/basic_controller.js
    var MonotributoFormController = FormController.extend({
        // Do not show window to confirm changes
        canBeDiscarded(recordID) { 
            return Promise.resolve(true);
        }
    })
    
    var MonotributoFormView = FormView.extend({
        withControlPanel: false,
        config: _.extend({}, FormView.prototype.config, {
            //     Model: HelpdeskDashboardModel,
            //     Renderer: HelpdeskDashboardRenderer,
            Controller: MonotributoFormController,
        })
    });
        
    viewRegistry.add('form_monotributo', MonotributoFormView);
    
    return MonotributoFormView
})

odoo.define('monotributo.list.subview', function (require) {
    "use strict";
    
    var viewRegistry = require('web.view_registry');
    var ListView = require('web.ListView');
    
    var MonotributoListView = ListView.extend({
        withControlPanel: false,
    });
        
    viewRegistry.add('list_monotributo', MonotributoListView);
    
    return MonotributoListView
})