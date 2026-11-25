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
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <https://www.gnu.org/licenses/>.
#
#############################################################################
import datetime
from unittest.mock import MagicMock, patch

import xlrd

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import TestImportCommon

WIZARD_MODULE = 'odoo.addons.import_dashboard.wizard.import_attendance'
CSV_HEADER = "Employee,Check In,Check Out\n"


@tagged('post_install', '-at_install')
class TestImportAttendance(TestImportCommon):

    def setUp(self):
        super().setUp()
        self.employee = self.env['hr.employee'].create(
            {'name': 'Test Employee'})

    def _attendance(self):
        return self.env['hr.attendance'].search(
            [('employee_id', '=', self.employee.id)])

    def _import(self, file_upload, tz='UTC', file_type='csv'):
        """Import as a user whose timezone is ``tz``."""
        self.env.user.tz = tz
        wizard = self.env['import.attendance'].with_context(tz=tz).create({
            'file_type': file_type,
            'file_upload': file_upload,
        })
        return wizard.action_import_attendance()

    def _import_csv(self, check_in, check_out, tz='UTC'):
        return self._import(self.encode_file(
            CSV_HEADER + "Test Employee,%s,%s" % (check_in, check_out)), tz)

    def test_import_attendance_csv(self):
        self._import_csv('2026-05-16 08:00:00', '2026-05-16 17:00:00')

        attendance = self._attendance()
        self.assertTrue(attendance, "Attendance should be created")
        self.assertEqual(attendance.check_in,
                         datetime.datetime(2026, 5, 16, 8, 0))
        self.assertEqual(attendance.check_out,
                         datetime.datetime(2026, 5, 16, 17, 0))

    def test_times_are_in_the_user_timezone(self):
        """09:00 in the file is 09:00 for the importing user: stored in UTC
        as 03:30 for a user in India (UTC+5:30)."""
        self._import_csv('2026-11-20 09:00:00', '2026-11-20 17:00:00',
                         tz='Asia/Kolkata')

        attendance = self._attendance()
        self.assertEqual(attendance.check_in,
                         datetime.datetime(2026, 11, 20, 3, 30))
        self.assertEqual(attendance.check_out,
                         datetime.datetime(2026, 11, 20, 11, 30))

    def test_times_use_daylight_saving_time(self):
        """The offset of the date itself is used: Brussels is UTC+1 in
        winter and UTC+2 in summer."""
        self._import_csv('2026-07-20 09:00:00', '2026-07-20 17:00:00',
                         tz='Europe/Brussels')
        self._import_csv('2026-11-20 09:00:00', '2026-11-20 17:00:00',
                         tz='Europe/Brussels')

        self.assertEqual(
            self._attendance().sorted('check_in').mapped('check_in'),
            [datetime.datetime(2026, 7, 20, 7, 0),
             datetime.datetime(2026, 11, 20, 8, 0)])

    def test_explicit_offset_wins_over_user_timezone(self):
        self._import_csv('2026-11-20 09:00:00+01:00',
                         '2026-11-20 17:00:00+01:00', tz='Asia/Kolkata')

        self.assertEqual(self._attendance().check_in,
                         datetime.datetime(2026, 11, 20, 8, 0))

    def test_user_without_timezone_imports_utc(self):
        self._import_csv('2026-11-20 09:00:00', '2026-11-20 17:00:00',
                         tz=False)

        self.assertEqual(self._attendance().check_in,
                         datetime.datetime(2026, 11, 20, 9, 0))

    def test_invalid_time_is_reported(self):
        with self.assertRaisesRegex(ValidationError, 'Row 1'):
            self._import_csv('20/11/2026 09:00', '20/11/2026 17:00')

    def test_import_attendance_xlsx(self):
        """Real .xlsx files are read; date cells are the user's local
        time."""
        self._import(self.encode_xlsx([
            ['Employee', 'Check In', 'Check Out'],
            ['Test Employee', datetime.datetime(2026, 11, 20, 9, 0),
             datetime.datetime(2026, 11, 20, 17, 30)],
        ]), tz='Asia/Kolkata', file_type='xls')

        attendance = self._attendance()
        self.assertEqual(attendance.check_in,
                         datetime.datetime(2026, 11, 20, 3, 30))
        self.assertEqual(attendance.check_out,
                         datetime.datetime(2026, 11, 20, 12, 0))

    def test_import_attendance_uses_workbook_datemode(self):
        """Dates of an .xls file using the 1904 date system are converted
        with that system, not the default 1900 one."""
        sheet = MagicMock(nrows=2)
        sheet.row_values.side_effect = [
            ['Employee', 'Check In', 'Check Out'],
            ['Test Employee', 44000.25, 44000.5],
        ]
        workbook = MagicMock(datemode=1)
        workbook.sheet_by_index.return_value = sheet
        with patch(WIZARD_MODULE + '.open_workbook', return_value=workbook):
            self._import(self.encode_file('dummy'), file_type='xls')

        expected = xlrd.xldate_as_datetime(44000.25, 1)
        self.assertNotEqual(expected, xlrd.xldate_as_datetime(44000.25, 0))
        self.assertEqual(self._attendance().check_in, expected)
