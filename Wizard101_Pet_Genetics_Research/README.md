# Wizard101 Pet Genetics Research

A Windows desktop research application built with Python, Tkinter, and SQLite.

## Included files

- `app.py` — application and database migration logic
- `talent_catalog_starter.csv` — complete bundled catalog (458 Combat + 107 Derby)
- `run_windows.bat` — Windows launcher
- `README.md` — installation, workflow, and data-safety notes
- `reference_sources/` — the source files used to assemble the bundled talent catalog

No third-party Python packages are required.

## Installation and launch (Windows)

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/).
2. During installation, enable **Add Python to PATH**. The standard Windows installer includes Tkinter.
3. Extract the downloaded ZIP to a normal writable folder.
4. Double-click `run_windows.bat`.

You can also open a terminal in the extracted application folder and run:

```bat
py -3 app.py
```

## Database and safe upgrades

The live database is stored at:

`%USERPROFILE%\Wizard101PetGenetics\pet_genetics.sqlite3`

The application creates missing Derby tables automatically at startup. Existing tables and research records are retained. Existing Derby tables are migrated in place to add a `manifested` flag, defaulting old records to unchecked. Derby observations use separate tables:

- `pet_derby_talents`
- `experiment_derby_talents`
- `hatch_derby_talents`

Combat and Derby each retain their own manifested flags in parent records, experiment snapshots, and offspring records. Foreign-key cascades remove an experiment's hatch records and snapshots when that experiment is deliberately deleted. A parent referenced by an experiment cannot be deleted; the app explains that it must first be unlinked by removing/editing the referencing experiment.

The bundled catalog is merged into the local catalog at startup. Existing research records are not cleared. The former starter-only `Couch Potato` row is retained as `Legacy` if it already exists in an older database; it is not counted as part of the authoritative 458-entry Combat catalog.

**Back up your database before moving it between computers or making manual changes.** Use **Import / Export → Backup SQLite database**.

## Research workflow

### 1. Parents

- Enter the pet name and notes.
- Enter the ten Combat talents in their recorded order and mark manifested talents with the checkboxes.
- Enter Derby talents in the separate ten-slot list. Derby slots also have Manifested checkboxes and default to `N/A`.
- You can mark up to five Combat talents and up to five Derby talents as manifested per pet. The two category limits are enforced independently.
- Leave a Derby slot as `N/A` when you do not want to track it.
- Select a saved parent to load it for editing. **Update selected** updates the existing record; **Save new parent** creates a new record.
- Deleting a parent is blocked while an experiment references it.

### 2. Experiments

- Select two distinct saved parents.
- Save the experiment to snapshot both parents' Combat and Derby pools.
- Selecting an experiment loads it for editing.
- Metadata-only edits preserve its original parent snapshots. If the parent pair itself is changed, the experiment snapshots are refreshed from the newly selected parents.
- Deleting an experiment requires confirmation and deletes its associated hatch records and experiment talent snapshots through database foreign-key cascades.

### 3. Hatch Records

- Select an item from the **Experiments** selector.
- Enter the offspring's ten Combat talents. Combat choices are restricted to the selected experiment's combined Combat parent pool.
- Enter any Derby talents you wish to track and mark manifested Derby talents. Derby choices are restricted to the experiment's combined Derby parent pool. `N/A` slots are ignored.
- Combat and Derby validation and five-manifested limits are independent.
- Select a saved hatch to load it for editing. Updating preserves the record ID. Deleting requires confirmation and removes both categories of offspring talent observations.

### 4. Family Tree

The **Family Tree** tab is centered on a selected parent pet. Choose a saved pet to see every experiment in which it was one of the parents, the other pet it was hatched with, and every offspring recorded for each experiment. Parent talent cards show the saved Combat and Derby snapshots, including manifested markers; offspring cards show their saved talents and manifested markers. Scrollbars support larger lineages.

The tree is a visualization only; use Parents, Experiments, and Hatch Records to edit data.

### 5. Analytics

Combat and Derby offspring talent frequencies are shown in separate tables. The experiment scope can be set to all experiments or one experiment. Derby statistics are not combined with Combat statistics. Manifested flags are stored and displayed for both categories; the current analytics tables summarize talent frequency rather than manifested rates.

### 6. Talent Catalog

The bundled catalog is based on the supplied `Abilities` worksheet and Derby category listing:

- **458 Combat talents**, retaining `school`, `rarity`, `status`, and `notes`
- **107 Derby talents**, with underscores converted to spaces and punctuation/capitalization retained

Combat and Derby selectors filter by category. CSV import accepts `name`, `category`, `school`, `rarity`, `status`, and `notes`.

## Import and export

- **Export complete database (JSON)** includes both catalogs, all research tables, both talent categories, and all parent snapshots.
- **Import research JSON** merges records by ID and preserves existing matching records. The importer also accepts older version-1 JSON exports that do not contain Derby tables.
- **Export all hatch talents (CSV)** writes both Combat and Derby observations, with `category` and `manifested` columns.
- **Export catalog CSV** writes the full catalog and all six catalog fields.
- **Backup SQLite database** creates a direct database backup.

The application does not silently omit Derby data from its JSON or hatch CSV exports.

## Catalog and research notes

The 458 Combat records and their metadata are taken from the supplied workbook's `Abilities` worksheet. The 107 Derby names are taken from the supplied HTML category listing's `title="PetAbility:..."` entries. Derby names are stored with spaces in place of underscores. No Derby entries are included in the Combat selector.

Talent pools preserve recorded slot order. Offspring validation confirms that each selected talent belongs to the corresponding category's parent pool for the selected experiment. The app does not infer which parent contributed a talent when both parents share it.

## Testing notes

The delivered build was syntax-checked and exercised with a temporary SQLite database and a virtual Tk display. The build checks covered the complete catalog counts, legacy Derby-schema migration and record preservation, independent five-manifested limits, parent/experiment/hatch save workflows, manifested Derby snapshots, and parent-centered Family Tree rendering. The Windows batch launcher was inspected but not executed on Windows.
