#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions (odoo@cybrosys.com)
#
#    This program is under the terms of the Odoo Proprietary License v1.0 (OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the Software
#    or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
#    DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
#    ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
#    For full details, see https://www.odoo.com/documentation/20.0/legal/licenses/licenses.html
#
#############################################################################
from odoo.addons.wm_subscription.hooks import uninstall_hook
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPremiumMenusHidden(TransactionCase):
    """Once the module is installed its real menus replace the placeholders."""

    XMLIDS = ('wm_contracts_billing.menu_wm_subscription_premium',
              'wm_contracts_billing.menu_wm_subscription_plan_premium')

    def test_placeholders_hidden_and_real_menus_active(self):
        for xmlid in self.XMLIDS:
            self.assertFalse(self.env.ref(xmlid).active, xmlid)
        for xmlid in ('wm_subscription.menu_wm_subscription', 'wm_subscription.menu_wm_subscription_plan'):
            self.assertTrue(self.env.ref(xmlid).active, xmlid)

    def test_uninstall_hook_restores_placeholders(self):
        uninstall_hook(self.env)
        for xmlid in self.XMLIDS:
            self.assertTrue(self.env.ref(xmlid).active, xmlid)
