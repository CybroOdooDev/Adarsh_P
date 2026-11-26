.. |license| image:: https://img.shields.io/badge/license-LGPL--3-blue.svg
    :target: http://www.gnu.org/licenses/lgpl-3.0-standalone.html
    :alt: License: LGPL-3

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

Odoo Jira Connector
===================

Odoo Jira Connector synchronizes projects, tasks, comments, attachments and
users between Odoo and Jira Cloud, so teams that use both tools work on the
same data.

Key Features
------------

* Bi-directional synchronization of projects, tasks, comments, and attachments
  between Odoo and Jira Cloud.
* Export Odoo projects, tasks, comments, attachments, and internal users to
  Jira, or import Jira projects, issues, comments, attachments, and users into
  Odoo.
* Real-time synchronization in Automatic mode for projects, tasks, comments,
  attachments, and users.
* Incoming Jira webhook endpoint (``/jira_webhook``) authenticated with an
  HMAC-SHA256 webhook secret.
* Sprint tracking in Odoo with dedicated smart buttons for tasks, backlogs,
  and all project tasks.

Installation
------------
No external dependencies. Uses Python ``requests`` which is installed with Odoo.

Configuration
-------------
* Go to Project > Configuration > Settings and fill in the Jira URL, the email
  address of your Atlassian account (User Name), and an API token, then click
  Test Connection.
* To receive Jira changes in real time, enable Automatic and create a Jira
  webhook pointing to your Odoo address followed by ``/jira_webhook``
  (HTTPS only). Enter a secret on the Jira webhook and enter the same value in
  Webhook Secret. Webhook calls without a configured secret and valid HMAC
  signature are rejected.

Company
-------
* `Cybrosys Techno Solutions <https://cybrosys.com/>`__

License
-------
GNU Lesser General Public License, Version 3 (LGPL v3).
(http://www.gnu.org/licenses/lgpl-3.0-standalone.html)

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
