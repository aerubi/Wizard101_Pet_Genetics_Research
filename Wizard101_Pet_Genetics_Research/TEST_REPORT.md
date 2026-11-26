# Build and Test Report

Build: Wizard101 Pet Genetics Research — Derby manifestation and parent-centered Family Tree update

## Catalog verification

- Combat talents: **458** entries from the supplied workbook's `Abilities` worksheet.
- Derby talents: **107** unique names from the supplied Derby category listing.
- Total bundled catalog: **565** entries.

## Tests performed

| Test | Result |
|---|---|
| Python syntax compilation (`py_compile`) | PASS |
| Tkinter application startup under Xvfb | PASS |
| Fresh database creates Derby `manifested` columns | PASS |
| Existing Derby schema migrates in place and preserves an existing talent row | PASS |
| Catalog seeds 458 Combat and 107 Derby entries | PASS |
| Combat manifested limit (five) enforced | PASS |
| Derby manifested limit (five) enforced independently | PASS |
| Parent save stores Derby manifested flags | PASS |
| Experiment snapshot stores Derby manifested flags for both parents | PASS |
| Hatch save stores Derby manifested flags | PASS |
| Parent-centered Family Tree renders selected parent, other parent, experiment, multiple offspring, and manifested markers | PASS |
| JSON export/import round-trip preserves Derby manifested flags | PASS |
| Hatch CSV export includes manifested flags for both categories | PASS |

## Scope and limitations

- The GUI workflow was exercised under a virtual X display. The Windows batch launcher was not executed on a Windows desktop.
- Full edit/delete regression testing was not repeated as part of this focused change. JSON import/export and hatch CSV export were checked for the new Derby manifested values.
- Existing Derby records migrate with `manifested = 0` (unchecked), preserving their saved talent slots.
