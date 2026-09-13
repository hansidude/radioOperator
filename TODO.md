# Radio Operator TODO

This is the authoritative handoff for the next radio log-on implementation pass.

## Procedure work authorised on 2026-09-13

The owner approved fixing the procedures, the DRY catalog and the existing checks.
Quackit's `DRY-CATALOG.md` now owns the reuse guide, and `DEVELOPMENT.md` owns the
single development/testing/rollout path. Read both before work. Develop in the
`quackit/radio/` submodule that Docker builds. Use the host's verification entry
point; no personalDB test targets, borrowed venvs or scratch standalone servers.

- [x] Create the host catalog covering UI, backend helpers, integration and procedures.
- [x] Add host/submodule agent instructions linking to the authoritative documents.
- [x] Add one Docker verification entry point and pinned browser/DOM dependencies.
- [x] Repair the dated standalone fixture and rewrite the existing browser check for
      explicit save, real host integration, stale-edit rejection and responsive views.
- [x] `./verify` passed on 2026-09-13: 63 Quackit Python tests, four JavaScript
      suites, 78 radio Python tests, and the browser flow through port 80 / MariaDB.
      Browser evidence: host `artifacts/verify/` (1920/900/390px screenshots and trace).
      The browser check also exposed two login-page errors in optional authenticated
      navigation; the existing initialisers now skip controls absent on that page.
- [ ] Consolidate the UI duplicates listed in the catalog as the next UI task; the
      catalog documents current ownership and gaps, it does not claim extraction is done.

The remaining UI/operational decisions below stay open. Historical verification
notes describe earlier snapshots; they are not alternative procedures or current
test results. The procedure authorisation supersedes C1, E1 and F1 below.

## Open work and decisions (2026-09-13)

Everything raised on 2026-09-13, with the owner's concerns in their own words and every question
still waiting for an answer. UI decisions remain open unless marked resolved below;
routine implementation within the approved procedure work does not need another go.

### A. New log on would not save on :8080, and nothing said why

Concern: *"it doesnt let me save. like - why? which field is it not happy about? i thought there was
supposed to be red highlighting on field if there is an issue? not user friendly at all."*
(screenshot `~/Downloads/260913_092039.png`)

Found: no field was wrong. The :8080 container logged `pymysql.err.OperationalError: (1054,
"Unknown column 'tripRef' in 'SELECT'")` from `logons.py:352 _next_trip_ref`. The personal database
has not had the `tripRef` migration (see **Still to do** at the bottom). The same values saved with a
200 on the same code against SQLite.

Why the page gave no clue: `logon.html:190-193` turns a non-JSON error (a 500) into `{}` and marks
no fields, so the only sign is a red "Not saved". That is a silent fallback.

- [ ] **Decision A1.** Show the server's reason beside "Not saved" when a save fails for a reason
      that is not a field (e.g. "Save failed: server error, see logs")?
      1. Yes
      2. No
- [ ] **Decision A2.** The personal DB migration, following Quackit's DEVELOPMENT.md.
      This unblocks saving there. The previously proposed personal-record wipe is a separate,
      irreversible operation; a missing column does not itself require deleting records.
      1. Owner runs it
      2. Claude runs it
      3. Later

### B. Live red highlighting on the draft minimum -- built, not rolled out

Asked for: *"highlight which field is bad. even before i hit save"*. Chosen: red from the moment the
form opens (not only after typing starts).

Built (uncommitted, `server/templates/radio/logon.html`, +2 lines): `mark(minimum())` now also runs
when a draft form opens and on every input, so call day, call time and member no. / rego / mobile go
red while missing and clear as they are typed. Vessel name alone does not clear them (the server
minimum).

Earlier standalone verification in Chromium: blank form marks exactly those
four; each clears correctly, including via the date picker; the screenshot's values show no red and
save; a saved draft opens with nothing red; no JS errors. The current host verification
now runs through Quackit's own layout and rebuilt Docker image, including initial
call-time highlighting, clearing the minimum errors and saving successfully.

- [ ] **Decision B1.** Roll out:
      1. Verify the working submodule through Quackit's documented command, then publish the
         tested radio commit and host pointer; personal rollout is a separate requested step
      2. Leave uncommitted for now
- [ ] Check on :80 after rollout: Log on -> New log on; call time and the three identity fields are
      red before typing.
- [ ] Small: on the identity fields the `.mandatory .form-control{background:...}` rule
      (`_ui.html:13,87`) hides Bootstrap's invalid icon, so they show a red border only. Call time
      shows border + icon. Left as is.
- [ ] Duplication: client `minimum()` (`logon.html:154-163`) repeats the server rule
      (`logons.py:440-447`). Needs one source of truth.

### C. DRY catalog -- first thing, before any more UI

Concern: *"i want to reuse the quackit stuff - link to the macros, etc. somewhat smartly. i dont want
you to reinvent fucking everything. because then its different right... dry is king. no one off
things. because later. it is not modular and everything starts looking like everything. even this
smart table to card view. this should be dry. and live on quackit. so can be reused at some stage. we
need a dry catalog library... first thing is always to check the dry catalog library!"*

Resolved C1: broad host catalog, including procedures, not just the logons list.
Created `quackit/DRY-CATALOG.md`. It identifies preferred owners, symbols/inputs,
dependencies, consumers, verification and unresolved duplicates. Complete signatures
remain in source so the catalog does not become a second implementation contract.

The catalog's duplication list is authoritative; consolidate those owners during the
UI work instead of copying that backlog here. Catalog completeness does not imply
that the listed duplicates have already been removed.

### D. Logons list: status symbols, smart columns, column selector, split Vessel Details

Asked for, in the owner's words:

- *"i want each row to have a status symbol emoji, and the drop down, will have emoji and name - so
  after a while - the operators can tell just by looking at the symbol (i.e. the rows will not have
  the status name - just the symbol). which is showed after the No."*
- *"i also want the column widths to be smart. like. i dont want to waste horizontal space. like i
  want it to be smart how it resizes the columns."*
- *"i want an really clever column selector."*
- *"i dont like the Vessel Details column. like. this should be like lots of different columns - if
  it is condensed of these columns. is ok. but needs to be done thoughtfully."*
- *"quackit has existing search/filtering/emoji stuff right? like on myTimes, or editList, etc. this
  is very standard functionality"*

Current state: status is a text badge after the member/vessel link (`_ui.html` `state_label`); the
dropdown is text only (`logons.html:23`); the grid has fixed `fr` widths
(`_ui.html:36`); `Vessel details` is one cell built by `vessel_summary` (length · hull colour · make ·
model · other, `_ui.html:248-251`).

Existing quackit pieces to reuse (not copy):

| Need | Quackit piece | Covers it? |
|---|---|---|
| Emoji-only on the row, emoji + name in the dropdown | Context emoji: dropdown `myMacro_listitems.html:553`, `myMacro_times.html:174`; emoji-only inline `myMacro_listitems.html:174-176, 638`; show/hide names toggle `myMacro_times.html:940` | Yes as a pattern, but contexts only -- needs generalising into a status macro |
| Search / filter | `myMacro_filters.html` `search_controls` | Shared presentation yes; radio filters in SQL via URL state. Do not add a second DOM filtering engine |
| Column show/hide | myTimes "Hide: Hub/Prog/Act" `myTimes.html:413-435`, saved in localStorage at `myMacro_times.html:1906-1913` | Closest; hides card types, not columns |
| Resize / hide / collapse columns | Tabulator 6.2 in `static/vendor/`, used by `datasets/dataset_edit.html:9-10, 94` | Has it all, but a different look |
| Table on wide screens, cards when narrow | none on quackit; radio's own grid `_ui.html:32-52, 107-123` | No -- move it to quackit |
| Compact rows | the two compact toggles in C | Yes, duplicated |

- [ ] **Decision D1.** UI work after the approved procedure/catalog work:
      1. Shared status-symbol macro (context-emoji presentation generalised) -> shared table/card
         list macro with smart widths and a column picker, on quackit -> radio's logons page uses
         both, Vessel Details split into Length, Hull colour, Make, Model, Other
      2. Review the completed catalog before authorising the remaining UI changes
- [ ] **Decision D2.** Column picker basis:
      1. Extend radio's grid into a shared quackit macro (keeps the card-based markup this TODO requires)
      2. Build on the Tabulator quackit already ships
- [ ] **Decision D3.** The emoji per status. Statuses the list shows today: Draft, Logged on (watching),
      Overdue, Logged off, Never departed, Discarded, plus the CONFLICT flag. Red stays reserved for a
      real abnormal record (see **Responsive record layout**).
- [ ] **Decision D4.** How the split vessel columns condense when space is short (e.g. one "Vessel"
      column showing `6m · white · Quintrex 610` until there is room for each), and which columns
      the picker shows by default.
- [ ] Define "smart" widths concretely before building: e.g. each column sized to its content up to a
      cap, blank columns shrink, long text truncates with the full value on hover.

### E. The radio/quackit boundary

Concern: *"it should use the macros/code. i think it was trying to say - dont tie into the existing
tables directly."*

Done: `CLAUDE.md` now says data goes through `Host` and never straight into quackit's tables or
session; UI uses quackit's shared macros via the DRY catalog.

- [x] E1: README and instructions now distinguish data independence from shared UI.
- [ ] E2: retain standalone compatibility for now; before new shared UI dependencies,
      make its loader consume the same shared files. Do not copy macros/CSS or expand
      standalone into another development/test target. Dropping support is not part of
      the approved procedure changes.

### F. Stale or broken things found along the way

- [x] `tests/test_standalone.py`: select the fixed fixture date instead of today's list.
      The old failure was reproduced in Quackit's Python 3.9 container.
- [x] F1: update `tests/browser_check.py` in place for explicit save and current selectors.
      The host verification entry point runs it with fixed Docker dependencies and
      the port 80 sample account. It rejects personal/standalone target URLs.

## Next task: one unified radio log list

Status: **done** (2026-09-12). One `records()` query in `server/logons.py`, one `record_list`
macro in `server/templates/radio/_ui.html`, one status/date/sort/search toolbar in
`server/templates/radio/logons.html`. The per-status tabs, `queue`/`closed_list`/`status_counts`
macros and the separate draft date filter are gone. Verified on the port 80 Docker stack,
including the 1920px, 900px and 390px browser checks (Playwright, `.venv-render`).

Replace the separate Drafts, Logged on, Overdue, and Closed list tabs with one
filterable collection. These records have the same data shape; status is a record
property and filter, not a reason to maintain separate renderers.

### List controls and behaviour

- Use one `Status` dropdown with: All, Drafts, Logged on, Overdue, and Closed.
- Default the status filter to Drafts.
- Use one date picker, defaulted to today, with the ability to select another day.
- Use one sort selector and one search field, following the existing Quackit action
  register/list-page pattern rather than creating another filtering system.
- Default sort is **newest first**.
- Search must cover the useful identifying fields: daily number, member number,
  vessel name, vessel registration, mobile number, and destination.
- Preserve selected status, date, sort, and search values across refreshes.
- Empty results must say exactly what is empty, for example `0 drafts`,
  `0 logged on`, `0 overdue`, or `0 closed`. Do not show generic messages such as
  `Nothing at sea` or text implying that the page failed to load.
- Do not show the status counters on every filter/view. If an overview is retained,
  summary numbers belong only on that overview.

### Numbering and order

- Number records chronologically within the selected call date.
- The oldest call on that date is number 1.
- The default display order is newest first, so number 1 appears at the bottom of
  the list.
- The number is a stable daily record sequence, not the visible row index. Filtering,
  searching, or reversing the sort must not renumber records.
- Base the number on the entered call date/time, not the time the operator entered
  it into the computer. This supports entering delayed paper records oldest to newest.
- Define deterministic handling for equal call times before implementation.

### Responsive record layout

- This remains card-based markup, not an HTML `<table>`.
- On wide screens, use aligned CSS-grid card rows so the collection reads like a
  compact table and all records are easy to compare.
- On narrow screens, each row must change into a labelled card layout. Do not force
  horizontal scrolling, clip fields, overlap text, or nest cards inside cards.
- Use the full available width with an exact maximum content width of `1920px`.
- Keep rows compact like the Quackit `myTimes` list and the paper radio log. Do not
  waste vertical or horizontal space with oversized cards, headings, or padding.
- Use one renderer for every status. Status may alter a label or restrained state
  treatment, but not the data layout.
- Keep the status selector neutral. Red is reserved for an actual overdue record or
  abnormal condition, not the Overdue filter itself and not a zero count.

### Existing references to extend

- Quackit action controls and one-card collection:
  `/home/hansi/z_git/quackit/dflask/templates/myMacro_actions.html`
- Quackit list controls, search, and card collection:
  `/home/hansi/z_git/quackit/dflask/templates/myMacro_lists.html`
- Action Project Overview consumer:
  `/home/hansi/z_git/quackit/dflask/templates/actionRegister/actionProjectOverview.html`
- Existing radio record/paper-row macro:
  `server/templates/radio/_ui.html`
- Paper log reference:
  `figures/figure-5-paper-radio-log-blank-form.jpeg`
- Current compact-draft screenshot:
  `/home/hansi/Downloads/260912_radio_drafts_after.png`

Do not copy the Quackit implementation into radio-specific code. Extend or consume
the shared UI implementation while keeping radio data access behind `Host`.

## New log-on entry

The main entry point is the operator's most important screen. It must be large,
clear, fast to scan, and use the full page width rather than sitting inside a narrow
decorative container.

### Main entry tab field order

1. Row 1: call date | call time
2. Row 2: member number or vessel name | vessel registration number | mobile phone
3. Row 3: vessel length | colour | make | model, each as a separate field
4. Row 4: persons on board | departure point | going to
5. Row 5: return day/date | return time

- Keep the remaining secondary fields on one other tab. Do not create a separate
  Watch tab or duplicate the same fields/actions in multiple places.
- Date fields must support both typing and a calendar picker.
- Time fields must support both typing and a time picker.
- Prefill today's call date only. Leave call time and all factual vessel/trip fields
  blank; never invent a trip fact.
- A future or delayed call time is not inherently invalid. Do not reject it merely
  because it is later than the computer's current time.
- Mark invalid fields clearly and quietly. Do not lecture the operator with messages
  such as `A day without a time is not a deadline` or display debug/radio warnings.

## Explicit draft saving

Status: **built and verified**, except the two items marked below. Nothing is written until the
operator saves, and a save that fails the minimum writes nothing.

- Opening New Log On must show an unsaved form. It must not insert a draft row or a
  history event.
- Never autosave on input, change, tab navigation, or navigation between fields.
- The operator must press `Save draft` explicitly.
- A draft cannot be saved without both a call date and call time.
- A draft also requires at least one of: member number, vessel registration number,
  or mobile phone number. Vessel name alone does not satisfy this minimum.
- One Save action must batch all changed fields into one insert/update and create at
  most one corresponding LogOns history event.
- A failed validation must create or update nothing.
- Warn before leaving a form with unsaved changes. The maintained browser check now covers this.
- After its first successful save, the draft receives its daily sequence number and
  appears in the unified list.
- Later saves must use optimistic version checking once per batch. A stale version
  must fail visibly; do not silently overwrite or fall back. The maintained browser check
  now exercises two operators and the visible 409 rejection.
- Accept/Log on remains a separate deliberate action. It cannot silently save and
  accept incomplete or unsaved changes.

## UI constraints already decided

- Use `layout.html` and the normal Quackit navbar/layout integration, not a standalone
  `_ui.html` page shell. `_ui.html` may remain a source of shared radio macros only.
- Do not show `not watched`; Draft status already communicates that state.
- Do not blink or animate draft state.
- Remove `Approaching` status/labels; it is not required.
- Do not show `Test alert channel`, debug controls, development diagnostics, or radio
  warning copy in the operator interface.
- Avoid frightening colour on normal filters and zero counts. Follow abnormal
  situation management: strong warning treatment is only for a real abnormal record.
- Keep actual record state visible and specific without decorative dashboard clutter.

## Record numbering as built

Two numbers, because the paper log has two (figure 5):

- `dayNumber` -- the left-hand `No.` column. Counts from 1 for each call date, allocated against
  the entered call date so a delayed paper record numbers against the day it was called in. This is
  what an operator says out loud. It repeats every day; it is not a key.
- `tripRef` -- the right-hand `Trip ID No.` column, `T-00042`. One running sequence, never reused,
  allocated on the first save that passes the draft minimum. This is the record's key.

Both are allocated under `FOR UPDATE` with an insert retry, because quackit's migration generator
emits `CREATE UNIQUE INDEX` as a plain `CREATE INDEX` and the constraint may not exist on the host.

Open: `tripRef` is issued state-wide in the real system and this branch allocates its own, so two
branches will eventually collide. Needs a branch prefix or a range split. `VARCHAR(16)` leaves room.

## What is built (was: working-tree handoff)

The explicit-save work is no longer uncommitted. Everything below is on `main` at `79b6121`
(quackit's submodule pointer `044e25a`), working tree clean, pushed.

That review is done. Resolved:

- the status tabs and the four renderers are replaced by one filtered collection;
- the sort is newest first, with number 1 at the bottom;
- the paper grid becomes labelled cards under 576px, in CSS alone, off `data-l` attributes;
- the unified toolbar is built and the separate draft date filter is gone;
- the page tests were rewritten against the new markup (78 pass, Python 3.9 container).

Content width: **done**. `logons.html` overrides `body_wrap_class`, the block both base templates
already expose, so the log opts out of quackit's 120ch reading-width cap (`layout.html:47`) without
touching host CSS; `.ro-wide` then caps it at 1920px. Measured: 1920px wrapper at a 2560 viewport
(centred), full width below that, no horizontal page scroll.

The New Log On page (`logon.html`) still sits inside the 120ch cap -- the same one-line block
override would widen it, but its layout has not been reviewed at full width.

Browser checks done at 1920/900/390px: no horizontal page scroll at any width; rows are 35px in
table mode and 245px labelled cards under 576px; empty cells drop out of the card (a sparse record
shows 9 of 14). Between 576px and ~900px the table scrolls inside its own box, which is the
existing `.ro-paper-log{overflow-x:auto}` behaviour, not the page scrolling.

Existing records: the decision is to delete them all and start fresh, because the current rows
predate the draft minimum and do not satisfy it. Done on the port 80 stack. **Not yet done on the
personal database** -- that wipe is irreversible and is the last step of the rollout.

## Specification conflict

`vessel-logon-spec.md` CAP-19 currently requires immediate durable draft creation and
automatic retention without a final Save button. That directly conflicts with the
explicit-save decision above. Update CAP-19 and audit related ACC/WAT requirements
before treating the implementation as complete. Keep requirement IDs in code comments
after the specification is corrected.

## Acceptance checks before commit/deploy

Checked on the **port 80** stack (same MariaDB image, same generated history triggers as personal):

- [x] Opening New Log On creates no database or history row.
- [x] Call date defaults to today; call time remains blank.
- [x] Saving without date/time is rejected and writes nothing.
- [x] Saving with date/time plus member number succeeds.
- [x] Saving with date/time plus vessel registration succeeds.
- [x] Saving with date/time plus mobile phone succeeds.
- [x] Vessel name without one of those three identifiers is rejected.
- [x] One Save creates exactly one database change and one history event -- measured on the live
      stack: `LogOns_history` 6 -> 7 and `LogOns` 6 -> 7 for one save.
- [x] Multiple records on one date receive stable chronological numbers; oldest is 1. Observed
      across a date rollover: 12/9 numbered 1,2,3 and 13/9 restarted at 1,2,3 while `tripRef` ran
      on T-00001..T-00006.
- [x] The default view is Drafts for today, sorted newest first, with number 1 at bottom.
- [x] Every status uses the same record renderer and filter controls.
- [x] Desktop checks include a wide `1920px` layout and an intermediate viewport (2560/1920/1548/900).
- [x] Mobile checks at 390px: labelled cards, no overlap, no horizontal page scroll; empty cells
      drop out (a sparse record shows 9 of 14).
- [x] Empty states use the exact selected status count wording (`0 drafts`, `0 logged on`,
      `0 overdue`, `0 closed`, `0 records`).
- [x] Filter, date, search, and sort state survive refresh -- driven through the UI, then reloaded:
      all four controls and the result count identical.
- [x] `python3 -m unittest discover -s tests` in the Python 3.9 container: **78 pass**.
- [x] Commit and push both repositories.

Still to do:

- [ ] Run the browser/runtime checks against the **personal** Quackit Docker stack.
- [ ] Run `/home/hansi/personalDb/myUpdate`, apply Admin -> Database -> Generate -> Execute for
      `LogOns.tripRef` and its index, then verify the updated personal site.
- [ ] Delete the existing personal records (irreversible; backup at
      `~/personalDb/backup_2026_09_12-132334.zip` and the website's own DB backup).
- [ ] Warn-before-leaving and the stale-version 409, exercised through a browser rather than
      only in unit tests.
- [ ] Resolve the CAP-19 specification conflict above.
- [ ] The New Log On page: field order (see **Main entry tab field order**) and the 120ch width cap.
