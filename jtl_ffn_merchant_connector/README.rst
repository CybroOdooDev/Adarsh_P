.. |license| image:: https://img.shields.io/badge/license-AGPL--3-blue.svg
    :target: https://www.gnu.org/licenses/agpl-3.0-standalone.html
    :alt: License: AGPL-3

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

JTL FFN Merchant Connector
==========================

Connect Odoo to the JTL Fulfillment Network (FFN): push your products and sale
orders to JTL FFN, and bring stock levels, shipment tracking and returns back
into Odoo, automatically or on demand.

Key Features
------------

* Connection profiles for one or more JTL FFN accounts, in sandbox or
  production, connected with OAuth (Connect to JTL); tokens are refreshed
  automatically.
* Push products that have an internal reference and a weight to JTL FFN.
* Pull the stock of each mapped fulfillment warehouse into Odoo.
* Push confirmed sale orders to JTL FFN, routed to a fulfillment warehouse by
  delivery country; failed orders are retried up to 5 times.
* Pull shipment tracking: the carrier and tracking number are written on the
  delivery, which is then validated.
* Pull returns: a return receipt is created in Odoo and validated when JTL FFN
  reports the return as arrived.
* Scheduled actions for every sync, and a webhook endpoint
  (``POST /jtl_ffn/webhook/<profile id>``) that triggers a stock, tracking or
  returns pull.
* User and Manager access levels; credentials are visible to managers only.

Installation
------------
Requires the Python library ``requests``, which is installed with Odoo.

Configuration
-------------
* Give users the JTL FFN User or Manager level in Settings > Users & Companies
  > Users. The administrator is a Manager by default.
* Go to Inventory > JTL FFN > Connection Profiles and create a profile with the
  Client ID and Client Secret of your OAuth client in the JTL Customer Center
  (https://kundencenter.jtl-software.de/oauth).
* The Redirect URI defaults to your Odoo base URL; register exactly the same URI
  for your client in the JTL Customer Center, or edit the field to the one you
  registered.
* Click Connect to JTL and authorize the connection; you are sent back to the
  profile with the tokens saved. Alternatively, paste an authorization code in
  the Authentication State tab and click Exchange Code Manually.
* Map your warehouses in Inventory > JTL FFN > Fulfillment Warehouses, then click
  Test Connection and choose the sync options.

Company
-------
* `Cybrosys Techno Solutions <https://cybrosys.com/>`__

License
-------
GNU Affero General Public License, Version 3 (AGPL v3).
(https://www.gnu.org/licenses/agpl-3.0-standalone.html)

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
