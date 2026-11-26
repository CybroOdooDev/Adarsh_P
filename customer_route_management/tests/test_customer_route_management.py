# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2026-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    This program is under the terms of the Odoo Proprietary License v1.0
#    (OPL-1) It is forbidden to publish, distribute, sublicense, or
#    sell copies of the Software or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
#    IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
#    CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT
#    OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR
#    THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
#############################################################################
import html
import io
import json

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from odoo import Command
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

XLSX_MIMETYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class RouteTestCommon(AccountTestInvoicingCommon):
    """A delivery route with one area and its customers, and invoices."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += cls.env.ref(
            'customer_route_management.group_delivery_route_manager')
        cls.no_tax = cls.env['account.tax']
        cls.delivery_route = cls.env['delivery.route'].create({'name': 'North Route'})
        cls.route_line = cls.env['route.line'].create({
            'route': 'North Zone',
            'delivery_route_link_id': cls.delivery_route.id,
        })
        cls.partner_a.write({'location_id': cls.route_line.id, 'sequence': 20})
        cls.child_contact = cls.env['res.partner'].create({
            'name': 'Child Contact',
            'parent_id': cls.partner_a.id,
            'location_id': cls.route_line.id,
            'sequence': 5,
        })
        cls.other_partner = cls.env['res.partner'].create({'name': 'other_partner'})

    @classmethod
    def _invoice(cls, partner, amount, post=True, **kwargs):
        return cls._create_invoice_one_line(
            price_unit=amount, tax_ids=cls.no_tax, partner_id=partner, post=post, **kwargs)


@tagged('post_install', '-at_install')
class TestCustomerRouteManagement(RouteTestCommon):
    """Routes, customers and their dues."""

    def test_route_line_keeps_route_customers_in_delivery_order(self):
        self.assertEqual(self.delivery_route.route_line_ids, self.route_line)
        self.assertEqual(self.route_line.cust_list_ids, self.partner_a | self.child_contact)
        self.assertEqual(self.route_line._get_customers(), self.child_contact | self.partner_a)
        self.assertEqual(self.route_line.display_name, 'North Zone')

    def test_partner_order_is_not_changed(self):
        """The delivery order of route customers does not reorder partners
        in the rest of Odoo."""
        self.assertEqual(self.env['res.partner']._order, 'complete_name ASC, id DESC')

    def test_get_all_dues_includes_parent_and_child_posted_invoices(self):
        parent_invoice = self._invoice(self.partner_a, 100.0)
        child_invoice = self._invoice(self.child_contact, 50.0)
        self._invoice(self.other_partner, 75.0)
        self._invoice(self.partner_a, 25.0, post=False)

        dues = self.partner_a.get_all_dues()

        self.assertEqual({due['name'] for due in dues}, {parent_invoice.name, child_invoice.name})
        self.assertEqual(sorted(due['amount_residual_signed'] for due in dues), [50.0, 100.0])
        self.assertTrue(all(due['invoice_date_due'] for due in dues))

    def test_get_all_dues_skips_paid_invoices(self):
        invoice = self._invoice(self.partner_a, 100.0)
        self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=invoice.ids,
        ).create({})._create_payments()
        self.assertFalse(self.partner_a.get_all_dues())

    def test_get_all_dues_counts_only_what_the_customer_owes(self):
        """Dues are the open items of the receivable account: invoices,
        credit notes and unmatched payments, but not vendor bills."""
        invoice = self._invoice(self.partner_a, 100.0)
        refund = self._invoice(self.partner_a, 30.0, move_type='out_refund')
        bill = self._invoice(self.partner_a, 70.0, move_type='in_invoice')
        payment = self.env['account.move'].create({
            'move_type': 'entry',
            'partner_id': self.partner_a.id,
            'line_ids': [
                Command.create({
                    'account_id': self.partner_a.property_account_receivable_id.id,
                    'partner_id': self.partner_a.id, 'credit': 20.0, 'name': 'Advance'}),
                Command.create({
                    'account_id': self.company_data['default_journal_bank'].default_account_id.id,
                    'debit': 20.0, 'name': 'Advance'}),
            ],
        })
        payment.action_post()

        dues = {due['name']: due['amount_residual_signed'] for due in self.partner_a.get_all_dues()}

        self.assertNotIn(bill.name, dues)
        self.assertEqual(dues, {invoice.name: 100.0, refund.name: -30.0, payment.name: -20.0})
        self.assertEqual(sum(dues.values()), 50.0)

    def test_get_all_dues_multi_company(self):
        other_company = self.setup_other_company()['company']
        self.env.user.company_ids |= other_company
        current_invoice = self._invoice(self.partner_a, 100.0)
        other_invoice = self._invoice(
            self.partner_a, 200.0,
            journal_id=self.env['account.journal'].search([
                ('company_id', '=', other_company.id), ('type', '=', 'sale')], limit=1),
            company_id=other_company)

        dues_current = {due['name'] for due in self.partner_a.get_all_dues(self.env.company.id)}
        dues_other = {due['name'] for due in self.partner_a.get_all_dues(other_company.id)}

        self.assertEqual(dues_current, {current_invoice.name})
        self.assertEqual(dues_other, {other_invoice.name})

    def test_route_user_reads_dues_without_accounting_access(self):
        route_user = new_test_user(
            self.env, login='route_user',
            groups='base.group_user,customer_route_management.group_delivery_route_user')
        invoice = self._invoice(self.partner_a, 100.0)
        dues = self.partner_a.with_user(route_user).get_all_dues()
        self.assertEqual([due['name'] for due in dues], [invoice.name])
        self.assertTrue(self.delivery_route.with_user(route_user).route_line_ids)


@tagged('post_install', '-at_install')
class TestRouteReports(RouteTestCommon):
    """PDF and XLSX reports printed from the route report wizard."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_a.write({'phone': '+32 470 00 00 00', 'city': 'Brussels'})
        # A company without document layout is first asked to configure one
        cls.env.company.external_report_layout_id = cls.env.ref('web.external_layout_standard')
        cls.invoice = cls._invoice(cls.partner_a, 100.0)
        cls.child_invoice = cls._invoice(cls.child_contact, 40.0)

    def _wizard(self, **values):
        return self.env['route.report'].create({
            'route_ids': [Command.set(self.delivery_route.ids)], **values})

    def _render_pdf_html(self, wizard):
        action = wizard.print_route_details()
        self.assertEqual(action['report_name'],
                         'customer_route_management.route_report_template')
        html, _format = self.env['ir.actions.report']._render_qweb_html(
            'customer_route_management.report_route_report', wizard.ids, data=action['data'])
        return html.decode()

    def _xlsx_sheet(self, wizard):
        action = wizard.print_xlsx_report_route()
        self.assertEqual(action['report_type'], 'xlsx')
        options = json.loads(action['data']['options'])
        response = type('Response', (), {'stream': io.BytesIO()})()
        self.env['route.report'].get_xlsx_report(options, response)
        return load_workbook(io.BytesIO(response.stream.getvalue())).active

    def _xlsx_cells(self, wizard):
        sheet = self._xlsx_sheet(wizard)
        return sheet.title, {cell.value for row in sheet.iter_rows() for cell in row
                             if cell.value}

    @staticmethod
    def _width(sheet, *columns):
        return sum(sheet.column_dimensions[col].width or 8.43 for col in columns)

    def test_pdf_report_lists_customers_and_dues(self):
        html = self._render_pdf_html(self._wizard(payment=True))
        self.assertIn('North Route', html)
        self.assertIn('North Zone', html)
        self.assertIn('Invoice Number', html)
        self.assertIn(self.invoice.name, html)
        self.assertIn('Brussels', html)
        self.assertLess(html.index('>Child Contact<'), html.index(f'>{self.partner_a.name}<'),
                        "customers are printed in their delivery order")
        self.assertRegex(html, r'<tr style="border-bottom:2px solid black;">\s*<td>Total</td>')

    def test_pdf_report_total_only(self):
        html = self._render_pdf_html(self._wizard(payment=True, consolidated=True))
        self.assertNotIn('Invoice Number', html)
        self.assertNotIn(self.invoice.name, html)
        self.assertRegex(html, r'<tr style="border:2px solid black;">\s*<td>Total</td>')

    def test_pdf_report_without_dues(self):
        html = self._render_pdf_html(self._wizard())
        self.assertIn(self.partner_a.name, html)
        self.assertNotIn(self.invoice.name, html)

    def test_total_only_needs_due_amounts(self):
        self.assertFalse(self._wizard(consolidated=True)._get_report_data()['consolidated'])

    def test_xlsx_report_with_dues(self):
        title, cells = self._xlsx_cells(self._wizard(payment=True))
        self.assertEqual(title, 'North Route')
        self.assertIn('NORTH ROUTE', cells)
        self.assertIn('NORTH ZONE:', cells)
        self.assertIn(self.invoice.name, cells)
        self.assertIn('Total', cells)

    def test_xlsx_report_total_only(self):
        _title, cells = self._xlsx_cells(self._wizard(payment=True, consolidated=True))
        self.assertNotIn(self.invoice.name, cells)
        self.assertIn('Total', cells)

    def test_xlsx_report_without_dues(self):
        _title, cells = self._xlsx_cells(self._wizard())
        self.assertIn(self.partner_a.name, cells)
        self.assertIn('+32 470 00 00 00', cells)
        self.assertNotIn('Total', cells)

    def test_xlsx_columns_fit_their_text(self):
        """Merged cells never overflow, so their columns are widened to show
        the whole text, in both layouts."""
        for payment in (True, False):
            sheet = self._xlsx_sheet(self._wizard(payment=payment))
            for cells in sheet.merged_cells.ranges:
                text = str(sheet.cell(cells.min_row, cells.min_col).value or '')
                columns = [get_column_letter(col)
                           for col in range(cells.min_col, cells.max_col + 1)]
                with self.subTest(payment=payment, cells=str(cells)):
                    self.assertGreaterEqual(self._width(sheet, *columns), len(text))

    def test_xlsx_total_row_when_dues_cancel_out(self):
        """Like the PDF report, the Excel report shows the total of a customer
        with open entries also when they add up to zero."""
        partner = self.env['res.partner'].create({
            'name': 'Zero Balance', 'location_id': self.route_line.id, 'sequence': 30})
        self._invoice(partner, 80.0)
        self._invoice(partner, 80.0, move_type='out_refund')
        for consolidated in (False, True):
            sheet = self._xlsx_sheet(self._wizard(payment=True, consolidated=consolidated))
            rows = [[cell.value for cell in row] for row in sheet.iter_rows()]
            start = next(i for i, row in enumerate(rows)
                         if any(str(v or '').startswith('Zero Balance') for v in row))
            total = next(row for row in rows[start + 1:] if 'Total' in row)
            with self.subTest(consolidated=consolidated):
                self.assertTrue(any('0.00' in str(v) for v in total if v and v != 'Total'))

    def test_xlsx_sheet_names_are_valid_and_unique(self):
        routes = self.env['delivery.route'].create([
            {'name': 'East/West: [A]'}, {'name': 'East/West: [A]'}])
        names = set()
        first = self.env['route.report']._sheet_name(routes[0], names)
        second = self.env['route.report']._sheet_name(routes[1], names)
        self.assertEqual(first, 'East West   A')
        self.assertNotEqual(first.lower(), second.lower())
        self.assertLessEqual(len(second), 31)


@tagged('post_install', '-at_install')
class TestXlsxReportController(HttpCase):
    """Download of the XLSX report through /xlsx_report."""

    def _post(self, model, options=None):
        self.authenticate('admin', 'admin')
        route = self.env['delivery.route'].create({'name': 'Download Route'})
        if options is None:
            options = {'route_ids': route.ids, 'payment': False, 'consolidated': False}
        return self.url_open('/xlsx_report', data={
            'model': model,
            'options': json.dumps(options),
            'output_format': 'xlsx',
            'report_name': 'Routes',
            'csrf_token': self.csrf_token(),
        })

    def test_download_xlsx(self):
        response = self._post('route.report')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Content-Type'], XLSX_MIMETYPE)
        self.assertIn('Routes.xlsx', response.headers['Content-Disposition'])
        self.assertTrue(response.content.startswith(b'PK'))

    def test_other_models_are_refused(self):
        self.assertEqual(self._post('res.partner').status_code, 404)

    @mute_logger('odoo.addons.customer_route_management.controllers.customer_route_management')
    def test_report_error_is_returned_to_the_client(self):
        """A failure while building the file returns the error the way the
        web client's download() expects it (as Odoo's report controller
        does): an HTML body holding the JSON error, without a file name."""
        response = self._post('route.report', options={'route_ids': []})
        self.assertTrue(response.headers['Content-Type'].startswith('text/html'))
        self.assertNotIn('Content-Disposition', response.headers)
        error = json.loads(html.unescape(response.text))
        self.assertEqual(error['message'], 'Odoo Server Error')
        self.assertEqual(error['data']['name'], 'builtins.KeyError')

    def test_route_and_excel_report_in_browser(self):
        self.start_tour('/odoo/action-customer_route_management.delivery_route_action',
                        'customer_route_management_tour', login='admin')
        self.assertTrue(self.env['delivery.route'].search([('name', '=', 'Tour Route')])
                        .route_line_ids.filtered(lambda line: line.route == 'Tour Area'))
