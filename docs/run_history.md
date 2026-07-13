# Run History

Phase 3A stores local run metadata in SQLite:

`runs/pgg_run_history.sqlite`

The run directory remains the authoritative artifact store.

## Stored Metadata

- run ID
- timestamp
- structure family
- domain shape
- dimensions
- requested porosity
- achieved porosity
- profile
- final status
- runtime
- output folder

Large geometry is not stored in SQLite. The history table stores paths only.

## Supported Actions

- refresh run history from `runs/`
- open run details
- inspect validation report
- load available STL artifact into the preview viewer
- duplicate the approved specification as the current editable specification
