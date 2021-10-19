odoo.define('web.session.patch', function (require) {
"use strict";

var utils = require('web.utils');

// Se sobreescribe la clase, no el objeto (service)
var session = require('web.Session');

utils.patch(session, 'session patch', {
    setCompanies(main_company_id, company_ids) {
        var hash = $.bbq.getState()
        hash.cids = company_ids.sort(function(a, b) {
            if (a === main_company_id) {
                return -1;
            } else if (b === main_company_id) {
                return 1;
            } else {
                return a - b;
            }
        }).join(',');
        utils.set_cookie('cids', hash.cids || String(main_company_id));
        $.bbq.pushState({'cids': hash.cids}, 0);

        // Volver a la pagina principal para evitar errores de permisos
        location.replace("/web");
    }
})

})