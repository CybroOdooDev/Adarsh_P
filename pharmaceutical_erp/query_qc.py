lots = env['stock.lot'].search([('name', 'in', ['ms', 'purt', 'mgs'])])
print("Lots found:", lots)
for l in lots:
    tests = env['pharma.qc.test.order'].search([('lot_id', '=', l.id)])
    print("Tests for", l.name, tests, [t.status for t in tests])
