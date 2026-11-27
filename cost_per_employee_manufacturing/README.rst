.. |license| image:: https://img.shields.io/badge/license-OPL--1-red.svg
    :target: https://www.odoo.com/documentation/20.0/legal/licenses.html#odoo-apps
    :alt: License: OPL-1

.. |odoo| image:: https://img.shields.io/badge/Odoo-20.0-875A7B.svg
    :target: https://www.odoo.com
    :alt: Odoo 20.0

.. |edition| image:: https://img.shields.io/badge/edition-Community%20%7C%20Enterprise-875A7B.svg
    :target: https://www.odoo.com/page/editions
    :alt: Edition: Community and Enterprise

.. |maintainer| image:: https://img.shields.io/badge/maintainer-Cybrosys-875A7B.svg
    :target: https://cybrosys.com
    :alt: Maintainer: Cybrosys Techno Solutions

|license| |odoo| |edition| |maintainer|

Cost per Employees in Manufacturing
===================================

Calculate employee hourly costs in manufacturing orders and work centers, tracking
individual labor expenses and displaying employee cost breakdowns in the MO Overview report.

Key Features
------------

* Configure custom hourly labor costs per employee in Employee profiles.
* Assign employees with their hourly rates to specific Work Centers.
* Automatically compute employee labor costs on Manufacturing Orders based on work order duration.
* Display total employee labor costs seamlessly in both interactive and PDF MO Overview reports.
* Compatible with both Community and Enterprise editions of Odoo 20.0.

Installation
------------

No external dependencies required. Ensure the core ``mrp`` and ``hr`` modules are installed.

Configuration
-------------

1. Go to Employees > Employees, open an employee profile, and under the Work Information tab set the **Hourly Cost**.
2. Go to Manufacturing > Configuration > Work Centers, open a work center, and under the **Cost Per Employees** tab assign employees.
3. When creating and progressing Manufacturing Orders with work orders, employee labor costs are calculated and reflected in the MO Overview report.

Company
-------
* `Cybrosys Techno Solutions <https://cybrosys.com/>`__

License
-------
Odoo Proprietary License v1.0 (OPL-1).
(https://www.odoo.com/documentation/20.0/legal/licenses.html#odoo-apps)

Contacts
--------
* Mail Contact : odoo@cybrosys.com
* Website : https://cybrosys.com

Maintainer
==========
.. image:: https://cybrosys.com/images/logo.png
   :target: https://cybrosys.com


This module is maintained by Cybrosys Technologies.

For support and more information, please visit `Our Website <https://cybrosys.com/>`__
