import xmlrpc.client
url = 'http://localhost:8069'
db = 'odoo'
username = 'admin'
password = 'admin'
common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(url))
uid = common.authenticate(db, username, password, {})
models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(url))
view = models.execute_kw(db, uid, password, 'ir.ui.view', 'search_read', [[('name', '=', 'mrp.production.form')]], {'fields': ['arch_db']})
for v in view:
    print(v['arch_db'][:1000])
