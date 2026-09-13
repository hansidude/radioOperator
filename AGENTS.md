# Radio inside Quackit

The canonical development checkout is Quackit's `radio/` submodule. Read the host's
`DRY-CATALOG.md` and `DEVELOPMENT.md` before implementation. In this checkout they
are [../DRY-CATALOG.md](../DRY-CATALOG.md) and [../DEVELOPMENT.md](../DEVELOPMENT.md).
For a separate clone, locate the Quackit checkout and continue in its `radio/` directory.
Do not create a second procedure to make the separate clone a development server.

Radio data access goes through `server/host.py`; generic UI consumes Quackit's shared
macros, CSS and JavaScript. Keep radio business rules in radio. Verification and rollout
follow the host procedure, including source revisions, test data and target selection.
`CLAUDE.md` contains the domain conventions; the host procedure governs the workflow.
