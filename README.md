## QWeb View 

- Javascript
https://github.com/odoo/odoo/blob/a7f7233e0eae8ee101d745a9813cba930fd03dcb/addons/web/static/src/legacy/js/views/qweb/qweb_view.js

- JRPC
qweb_render_view


En los normales se llama a web/action/load
  {"jsonrpc":"2.0","method":"call","params":{"action_id":345},"id":865494874}
  { "result": {
      "id": 345, 
      "name": "Importar Comprobantes Recibidos", 
      "type": "ir.actions.act_window", 
      "view_id": false, 
      "domain": false, 
      "context": "{}", 
      "res_id": 0, 
      "res_model": "l10n_ar.import.purchase.comprecibidos", 
      "target": "new", 
      "view_mode": "form", 
      "views": [[false, "form"]], 
      "limit": 80, 
      "groups_id": []
  }

web/dataset/call_kw/l10n_ar.import.purchase.comprecibidos/load_views


Views:
web/static/src/js/views/view_registry.js

var FormView = require('web.FormView');
var GraphView = require('web.GraphView');
var KanbanView = require('web.KanbanView');
var ListView = require('web.ListView');
var PivotView = require('web.PivotView');
var CalendarView = require('web.CalendarView');

var KanbanRenderer = require('web.KanbanRenderer');
var ListRenderer = require('web.ListRenderer');

El widget pie_chart (web/static/src/js/widgets/pie_chart.js)


# Esto en FormRenderer muestra una notificacion
this.$('.o_notification_box').remove();
if (this.alertFields[this.state.res_id]) {
    var $notification = $(qweb.render('notification-box', {type: 'info'}))
        .append(qweb.render('translation-alert', {
            fields: this.alertFields[this.state.res_id],
            lang: _t.database.parameters.name
        }));
    if (this.$('.o_form_statusbar').length) {
        this.$('.o_form_statusbar').after($notification);
    } else if (this.$('.o_form_sheet_bg').length) {
        this.$('.o_form_sheet_bg').prepend($notification);
    } else {
        this.$el.prepend($notification);
    }
}


WIDGETS
https://www.odoo.com/documentation/15.0/developer/reference/javascript/javascript_reference.html#widgets

Owl Widget          QWeb Template
web.ControlPanel    src/xml/base.xml > web.ControlPanel


                                       ListView.buttons (boton Crear/Editar)


CACHE MISS / ASSETS Regeneration

Errores comunes de Odoo
https://www.moldeointeractive.com.ar/en_US/blog/moldeo-interactive-1/post/los-errores-de-odoo-839


MANY2ONE OPTIONS

Para editar "inline" y no con un popup, agregar editable=0
<tree editable="0">
</tree>

ONE2MANY OPTIONS

Para deshabilitar create y create/edit

https://www.odoo.com/es_ES/forum/ayuda-1/how-to-remove-create-and-edit-from-many2one-field-92242

<field name="account_id"
    options="{'no_create': True, 'no_create_edit': True}"
    domain="[('company_id', '=', company_id)]" />

o 

<field name="account_id" widget="selection"
    options="{'create': False, 'create_edit': False}"
    domain="[('company_id', '=', company_id)]" />


Solucion a cache error

-- SELECT * 
DELETE
FROM ir_attachment
WHERE url IS NOT NULL