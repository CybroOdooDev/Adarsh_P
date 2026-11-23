## Module <advanced_tender_management>

#### 19.03.2026
#### Version 17.0.1.0.0
#### ADD
- Initial commit for Advanced Tender Management

#### 23.11.2026
#### Version 20.0.1.0.0
#### UPDT
- Migrated to Odoo 20.
- Website pages use the Odoo 20 interaction framework; the vendor
  registration form uses a standard multiple selection for categories.
- The product template is downloaded directly as an XLSX file, and the
  import reads XLSX files with openpyxl.
- Bids and edit requests require a logged-in vendor; vendors can only ask
  to edit their own bids, and a submitted bid changes only after an edit
  request is approved.
- Bid prices keep their decimals.
- Confirming product-wise bids only uses the lines selected for that tender.
- Tender documents of draft and cancelled tenders cannot be downloaded.
- Tender stages change only through buttons (Confirm, Bid Evaluation, Start
  Selection, Close, Cancel); each button checks the current stage. Confirming
  the purchase closes the tender.
- Bid stages change only through actions: confirming product-wise bids marks
  bids won or lost, and closing or cancelling a tender marks its open bids
  lost. Bids are qualified or disqualified during evaluation and selection
  only, edit requests are possible only while bidding is open, and a
  submitted bid cannot be changed in the backend.
- Section titles are shown again in the tender and bid product lines.
- Upload buttons and portal breadcrumbs follow Odoo 20 (Material Symbols
  icons, one breadcrumb); portal bid amounts show two decimals.
- The Tenders website block shows a heading and a placeholder in the website
  editor and its previews; submitted bid prices show two decimals.
- New screenshots taken on Odoo 20 Enterprise.
