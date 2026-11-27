# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#############################################################################
from unittest.mock import MagicMock, patch

from odoo import Command
from odoo.tests import TransactionCase

MODULE = 'odoo.addons.jtl_ffn_merchant_connector.models'


def fake_response(json_data=None, ok=True, status_code=200, text='', content=True):
    """Build a minimal stand-in for a ``requests.Response``."""
    resp = MagicMock()
    resp.ok = ok
    resp.status_code = status_code
    resp.text = text
    resp.content = b'{}' if content else b''
    resp.json.return_value = json_data if json_data is not None else {}
    return resp


class JtlFfnCommon(TransactionCase):
    """Shared fixtures: one FFN profile, one warehouse mapping, one confirmed order."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.germany = cls.env.ref('base.de')
        cls.usa = cls.env.ref('base.us')
        cls.config = cls.env['jtl.ffn.config'].create({
            'name': 'Test FFN',
            'client_id': 'client',
            'client_secret': 'secret',
            'refresh_token': 'refresh',
        })
        cls.odoo_wh = cls.env.ref('stock.warehouse0')
        cls.ffn_wh = cls.env['jtl.ffn.warehouse'].create({
            'config_id': cls.config.id,
            'name': 'Main FFN',
            'odoo_warehouse_id': cls.odoo_wh.id,
            'ffn_warehouse_id': 'WH1',
            'is_default': True,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'FFN Product',
            'default_code': 'FFN-SKU-1',
            'barcode': '4006381333931',
            'type': 'consu',
            'is_storable': True,
            'weight': 1.5,
            'description_sale': 'Sale description',
        })
        cls.service = cls.env['product.product'].create({
            'name': 'FFN Service',
            'type': 'service',
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'John Doe',
            'street': 'Main Street 1',
            'street2': 'Apartment 2',
            'city': 'Berlin',
            'zip': '10115',
            'country_id': cls.germany.id,
            'email': 'john@example.com',
            'phone': '+4930123456',
        })
        cls.order = cls._create_order(cls.product)
        cls.order.action_confirm()
        cls.picking = cls.order.picking_ids[:1]
        cls.service_order = cls._create_order(cls.service)

    @classmethod
    def _create_order(cls, product):
        return cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'order_line': [Command.create({
                'product_id': product.id,
                'product_uom_qty': 2,
                'price_unit': 10.0,
            })],
        })

    def patch_model(self, model_name, attr, **kwargs):
        """Patch ``attr`` on the registry class of ``model_name``."""
        patcher = patch.object(type(self.env[model_name]), attr, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def patch_api(self, **kwargs):
        """Patch ``jtl.ffn.config._api_request``."""
        return self.patch_model('jtl.ffn.config', '_api_request', **kwargs)

    def make_order_sync(self, order=None, **vals):
        values = {
            'config_id': self.config.id,
            'sale_order_id': (order or self.order).id,
            'ffn_order_id': 'OB1',
            'push_state': 'sent',
        }
        values.update(vals)
        return self.env['jtl.ffn.order.sync'].create(values)
