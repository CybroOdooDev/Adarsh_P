.. image:: https://img.shields.io/badge/license-OPL--1-blue.svg
    :target: https://www.odoo.com/documentation/20.0/legal/licenses.html
    :alt: License: OPL-1

===========================
Waste Management Driver App
===========================
Offline-first Progressive Web App (PWA) that lets drivers log the status of each collection stop from a mobile device.

* One-tap status updates per stop: En Route, Arrived, Started, Lifted, Weighed, Completed or Flagged.
* REST API secured with the native Odoo API keys of the driver's user.
* Client UUID de-duplication, so updates retried after a network failure are never logged twice.
* GPS coordinates captured with every status update.
* IndexedDB offline queue that is sent automatically when the connection returns.
* Installable on the home screen of a phone as a standalone application.

Configuration
=============
* Generate an API key for the driver under ``Settings > Users > (the driver) > API Keys > New Key``.
* Open ``/driver/app`` on the mobile device, paste the API key and install the app.

Company
=======
* `Cybrosys Techno Solutions <https://cybrosys.com/>`__

License
=======
Odoo Proprietary License v1.0 (OPL-1).
(https://www.odoo.com/documentation/20.0/legal/licenses.html)

Credits
=======
* Developers: (V19) Cybrosys Techno Solutions
  Contact: odoo@cybrosys.com

Contacts
========
* Mail Contact : odoo@cybrosys.com
* Website : https://www.cybrosys.com
