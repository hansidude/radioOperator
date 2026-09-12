# Vessel log on

The radio operator's log on: a vessel departs under the unit's watch, the operator captures what the
caller says in any order while the open watch queue stays on screen, a passed ETA shows as overdue
without anyone pressing anything, and the vessel is logged off when it is back.

The specification is `vessel-logon-spec.md` (index: `INDEX.md`). Requirement ids (CAP-n, WAT-n, ...)
are cited in code comments where code exists because of them. This is slice 1: capture and the open
queue, laid out as the paper radio log's row under its headings in its order (DAT-6), with what the
system adds after it. Vessels, people, cross-verification, search and obligations are later slices.

## Its own app, mounted by quackit

Same shape as garageSim: `server/` is the app (no idea quackit exists), quackit mounts it as the
submodule `radio/` through `dflask/radio_host.py`, and the tables live in quackit's database, created
by quackit's Database management from the symlinked `server/schema/schemaInput_Radio.sql` (history
tables and triggers included).

```
server/
  __init__.py      mount(app, host) — the only public entry point
  host.py          Host, NullHost: connect(), user(), unit(), approaching_minutes
  db.py            cursor with @user_id for the host's history triggers
  sqlite.py        the SQLite adapter standalone and the tests use
  times.py         1500 · 3pm · +2h, read against the call time; never guessed
  logons.py        the data layer: pure SQL over LogOns / Identifiers
  routes.py        the blueprint: /logons, /logon/<id>, /api/logon/<id>
  schema/schemaInput_Radio.sql
  templates/radio/ logons.html · logon.html · _queue.html · _ui.html · _base.html
standalone/        the app on its own (SQLite by default, MariaDB with RADIO_DB=mysql://...)
tests/             unittest over real routes and SQL, plus browser_check.py against a running site
```

## Run it on its own

```
python3 standalone/app.py                                    # http://localhost:8091
docker compose -f standalone/docker-compose.yml up --build   # MariaDB + the app on quackit's Python/Flask versions
python3 -m unittest discover -s tests
RADIO_URL=http://localhost:8091 python3 tests/browser_check.py    # needs a running site + playwright
```

The browser check is not optional cleverness: form nesting and autosave races are invisible to a
test client that posts straight to an endpoint, and two defects reached the running site that way.

## Inside quackit (after `myUpdate`)

Admin → Database → Generate → move the migration into Migrations → Execute, then navbar → Log on.
