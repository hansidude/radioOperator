# Vessel log on

The radio operator's log on: a vessel departs under the unit's watch, the operator captures what the
caller says in any order while the open watch queue stays on screen, a passed ETA shows as overdue
without anyone pressing anything, and the vessel is logged off when it is back.

The specification is `vessel-logon-spec.md` (index: `INDEX.md`). Requirement ids (CAP-n, WAT-n, ...)
are cited in code comments where code exists because of them. Slice 1 was capture and the open queue, laid out as the paper radio log's row under its headings in
its order (DAT-6). Slice 2 is section 7: cross-verification, tolerant matching and one search box.
Slice 3 is the v1.0 acceptance model and the checker. Transfer, handover, escalation procedure and
long-trip reporting are later slices.

**What is watching.** `server/watch.py` runs on a timer in whichever web worker holds a database
lease, with no browser involved. It raises a draft that has gone unaccepted past the unit's interval
and a log on whose return time has passed, records each as a row that survives a restart, keeps
raising it until its cause is resolved, and reports whether it is alive so a dead checker does not
look like a quiet night. **Where alerts go** is configuration, because the spec leaves the channel to the unit. Set any of
these and an alert reaches someone who is not looking at the screen:

```
RADIO_ALERT_WEBHOOK=https://...     an HTTP POST of the alert as JSON: a phone-notification
                                    service, a chat room, an SMS gateway, a siren on the bench
RADIO_ALERT_SMTP_HOST / _PORT / _FROM / _TO / _STARTTLS / _SSL / _USER / _PASSWORD
```

With neither set, an alert reaches whoever has the site open and nobody else. The page says so
rather than looking calm, a failed delivery is recorded against the alert and shown, and "Test the
alert channel" on the log ons page sends a real one so the unit can prove it works before trusting
it. While a page is open it also sounds an alarm and flashes the tab title, which is delivery to
somebody in the room and to nobody else.

Until a channel is configured and proved, ACC-5 is not met.

**Identity comes from the unit's own trip history**, not a membership register: the unit's vessel and
member records live in a system this app cannot reach, and §3.1 allows a conceptual model rather than
tables per entity. A vessel is every past trip carrying the same registration; a person is every past
trip carrying the same member number, or the same mobile without one; an association is the two on one
trip. That is weaker than a register in one way worth stating: a value misheard the same way twice
looks corroborated, so every match says how many earlier trips it rests on. Putting a real register
behind it changes two functions in `server/identity.py` and nothing else.

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
  identity.py      who is this: resolution, Appendix B tolerant matching, the IDV-2 outcome, search
  watch.py         the only thing that runs without a browser: due deadlines, alerts, health
  logons.py        the data layer: pure SQL over LogOns / Identifiers
  routes.py        the blueprint: /logons, /logon/<id>, /api/logon/<id>, /api/search
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
