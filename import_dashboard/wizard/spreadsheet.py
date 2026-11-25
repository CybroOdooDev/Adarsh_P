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
"""Read uploaded Excel files in both the .xlsx and the legacy .xls format.

On Python 3.12+ Odoo 18 ships xlrd 2.x, which only reads .xls files, so .xlsx
files are read with openpyxl instead. The .xlsx reader returns cell values the
way xlrd does (numbers as floats, empty cells as '', dates as Excel serial
numbers with datemode 0), so callers handle both formats the same way.
"""
import datetime
import io

import pytz
import xlrd
from openpyxl import load_workbook
from openpyxl.utils.datetime import to_excel

XLSX_SIGNATURE = b'PK\x03\x04'


def _xlrd_value(value):
    """Convert an openpyxl cell value to the value xlrd would return."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return to_excel(value)
    if isinstance(value, int):
        return float(value)
    return value


class XlsxSheet:
    """The subset of the xlrd sheet API used by the import wizards."""

    def __init__(self, worksheet):
        rows = [[_xlrd_value(value) for value in row]
                for row in worksheet.iter_rows(values_only=True)]
        while rows and all(value == '' for value in rows[-1]):
            rows.pop()
        width = max((len(row) for row in rows), default=0)
        self._rows = [row + [''] * (width - len(row)) for row in rows]
        self.nrows = len(self._rows)

    def row_values(self, row_index):
        return list(self._rows[row_index])


class XlsxWorkbook:
    """The subset of the xlrd workbook API used by the import wizards."""

    datemode = 0

    def __init__(self, file_contents):
        workbook = load_workbook(io.BytesIO(file_contents), read_only=True,
                                 data_only=True)
        try:
            self._sheets = [XlsxSheet(sheet) for sheet in workbook.worksheets]
        finally:
            workbook.close()

    def sheet_by_index(self, index):
        return self._sheets[index]


def cell_text(value):
    """Return a cell value as stripped text, for codes such as barcodes.

    Excel stores numeric codes as floats, so 5824693 is read as 5824693.0;
    whole numbers are turned back into their integer text.
    """
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def parse_date(value, datemode=0, formats=()):
    """Return a date cell as a naive datetime, or None for an empty cell.

    Accepts Excel date cells (serial numbers, read with the workbook's
    ``datemode``: 1904-based workbooks are 4 years apart from 1900-based
    ones), date/datetime values, ISO text ('YYYY-MM-DD[ HH:MM:SS]') and text
    in one of ``formats`` (strptime formats). Raises ValueError otherwise.
    """
    if value is None or value == '':
        return None
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time())
    if isinstance(value, (int, float)):
        return xlrd.xldate_as_datetime(value, datemode)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        pass
    for date_format in formats:
        try:
            return datetime.datetime.strptime(text, date_format)
        except ValueError:
            continue
    raise ValueError("'%s' is not a valid date" % text)


def invalid_numbers(item, columns):
    """Return the columns of ``item`` whose value is not a number.

    Empty cells are fine. Values are only checked, not converted: Odoo
    converts valid number text itself. Text such as '1,000' or 'abc' would
    otherwise stop the whole import with a bare ValueError.
    """
    invalid = []
    for column in columns:
        value = item.get(column)
        if value is None or isinstance(value, (int, float)):
            continue
        text = str(value).strip()
        if not text:
            continue
        try:
            float(text)
        except ValueError:
            invalid.append(column)
    return invalid


def number_error(item, columns):
    """Describe the invalid numbers of ``item`` (see invalid_numbers), or
    return '' when all are valid."""
    return ", ".join("'%s' is not a valid number in column %s"
                     % (item.get(column), column)
                     for column in invalid_numbers(item, columns))


def to_utc_datetime(value, tz_name, datemode=0):
    """Return the date/time of a cell as a naive UTC datetime, the way Odoo
    stores Datetime fields.

    A value with a UTC offset ('2026-11-20 09:00:00+01:00') is converted
    using that offset. A value without one, including Excel date cells, is
    the local time of ``tz_name`` (the importing user's timezone), or UTC
    when no valid timezone is given. Raises ValueError for text that is not
    an ISO date/time ('YYYY-MM-DD HH:MM:SS').
    """
    if isinstance(value, float):
        value = xlrd.xldate_as_datetime(value, datemode)
    elif isinstance(value, str):
        value = datetime.datetime.fromisoformat(value.strip())
    elif isinstance(value, datetime.date) and not isinstance(
            value, datetime.datetime):
        value = datetime.datetime.combine(value, datetime.time())
    if value.tzinfo is None:
        try:
            timezone = pytz.timezone(tz_name) if tz_name else pytz.utc
        except pytz.UnknownTimeZoneError:
            timezone = pytz.utc
        value = timezone.localize(value, is_dst=False)
    return value.astimezone(pytz.utc).replace(tzinfo=None)


def open_workbook(file_contents):
    """Open an .xlsx or .xls file given as bytes."""
    if file_contents[:4] == XLSX_SIGNATURE:
        return XlsxWorkbook(file_contents)
    return xlrd.open_workbook(file_contents=file_contents)
