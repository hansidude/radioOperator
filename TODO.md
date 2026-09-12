# Radio Operator TODO

This is the authoritative handoff for the next radio log-on implementation pass.

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
the established pattern while keeping `server/` independent of the Quackit host.

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
- Warn before leaving a form with unsaved changes. **(not verified -- no browser check yet)**
- After its first successful save, the draft receives its daily sequence number and
  appears in the unified list.
- Later saves must use optimistic version checking once per batch. A stale version
  must fail visibly; do not silently overwrite or fall back. **(unit-tested: a stale version
  returns 409; not exercised through the browser)**
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
