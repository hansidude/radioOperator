# Radio Operator TODO

Current state and open work. Read Quackit's `DRY-CATALOG.md` and `DEVELOPMENT.md` first: they own
reuse, verification (`./verify`) and rollout. History lives in the commit log and
`quackit/WORKLOG-radio.md`; superseded notes are not kept here.

## Built (as of 2026-09-13)

### RadioLogs list (`/logons`)

- Named **RadioLogs**: Quackit navbar link, page title, browser tab (`Host.brand`), and the green
  `parent_link` button on a log on.
- One collection through Quackit's shared `record_grid`: compact aligned rows on desktop/tablet,
  labelled cards at phone width, paper-log column order, width capped at 1920px.
- Toolbar: status (All, Drafts, Logged on, Overdue, Closed; default All), call date (default today,
  untickable), sort (Newest first by default, Oldest first, **Due first**), search. It rides in Quackit's
  fixed navbar (`data-navbar-controls`), so it stays on screen while the log scrolls. Swapped in place by
  Quackit's htmx; state kept in the URL; 30s refresh.
- Due first: overdue, then by return time; drafts and closed after, newest call first. One rule,
  `logons.due_first`, also used by `queue()`.
- Status symbol after the daily number (emoji with accessible name). Member No. and Vessel Name are separate
  columns. Every column heading carries its symbol beside the word (📅 Date, 👤 Member No., 🛥️ Vessel Name,
  🔖 Rego …) so operators learn them; one-line cards show the symbol alone, the word in its tooltip.
- View buttons (Quackit's shared `record_grid` `view_controls`): **Cards** at any width, fields on one
  line; **Paragraphs**, a line per field (or wrapped row values). Kept across refreshes, not across
  page loads. Text size buttons (A−, 100–200%, A+, reset) grow the list's text, symbols and icons;
  remembered in this browser.
- Draft rows show what still blocks Accept as an orange `?` (after its symbol on cards, in the cell on rows);
  other empty fields stay blank. Logged-on and closed rows show no `?`.
- Rows tinted faintly by status: draft orange, logged on green, overdue red, closed near-black.
- Dates always carry a 2-digit year (`Sun 13/9/26`); times always 4-digit 24-hour (`1400`).
- Daily `No.` counts from 1 per call date; `Trip ID No.` (`T-00042`) is the record's key.
- Overdue alerts on the page: pulse, count in the blinking tab title and beep until **Seen** is
  pressed. The owner decided this stays (Seen stops it).

### Log on form (`/logon/<id>`, `/logons/new`)

- Five paper rows on the Log on tab: Date | Time; Member No. | Vessel Name | Rego | Mobile;
  Length | Hull colour | Make | Model; POB | Departure | Going to; Return day | Time.
  Contact, Vessel, Identity and Record tabs hold the rest.
- Explicit save only: nothing is written until Save, one save is one update and one history event,
  a stale version is refused visibly (409), leaving with unsaved changes warns.
- Yellow Save (Quackit's "changes data" colour) in the navbar and first in the bottom row of every
  editable pane. A draft's bottom row: Save · reason · Discard draft.
- **Saving a complete draft logs it on** (spec v1.1 ACC-3): no Accept button. A save that leaves the
  mandatory set short keeps a draft; so does one refused because the vessel already has an open log on.
- Discard keeps the record, marked never a log on, with its required reason (ACC-7).
- Mobile: exactly 10 digits, saved and shown as `0412 345 678` (spaces while typing are fine); anything else
  is kept as typed and red. Search finds it with or without spaces.
- Orange boxes: with Member No. or Vessel Name heard, the other empty one turns orange (worth asking for,
  blocks nothing). Red wins. Same server check as red.
- Red boxes only, no messages. The server decides (`logons.check_fields`): the draft minimum, values
  that cannot be read, and on a draft everything that blocks Accept. Shown when the page opens and
  re-checked as focus leaves a box (a `{check: true}` post that writes nothing). No client copy of the rule.
- Settled days show as dates with the year; times as 4 digits, including a time understood before its
  day is given. What cannot be read stays as typed (CAP-23).
- Date buttons open the calendar. The call Time clock sets now (desktop Firefox has no time picker);
  other time boxes are typed.
- The "already logged on as T-…" clash line, with its link, is the one text line under the form.

### Behind it

- One record table, `LogOns`, with one status column (`watchStatus`: draft, loggedOn, loggedOff,
  discarded; renamed from watching / loggedoff on 2026-09-13, converted by the checker's first pass). quackit's migration generator gives it `LogOns_history` and triggers. The **History** tab
  shows that history in quackit's shared viewer (through `Host.history`), statuses with their emoji
  and fields with the log's symbols; the old summary line is gone.
- Side tables: `Identifiers` (every ID value heard), `Alerts` (what the checker raised), `WatchHealth`
  (the checker's heartbeat and lease).

- Deadline checker runs without a browser, raises and clears alerts, records delivery.
- Radio data only through `Host`; the standalone shell loads Quackit's real shared templates and assets.
- `./verify` covers Quackit and radio: Python tests, DOM tests, and the browser check on port 80 /
  MariaDB in Chromium and Firefox (save, red boxes, conflicts, search, sort, layout 320–2560px,
  accept, log off).

## Open

### Decisions waiting on the owner

- [ ] **"Due soon".** Owner, 2026-09-13: *"i dont want due soon"*. A logged-on record within 30 minutes
      of its return still shows a yellow `Due in n min` badge (`_ui.html` `cond`), and the watcher still
      has an approaching window (`RADIO_APPROACHING_MINUTES`).
      1. Remove the approaching state: the badge reads the same until overdue
      2. Keep the badge, only no row colour of its own (as now)
- [ ] **Failed save gives no reason.** A save refused for something other than a field (server error,
      too long, bad channel) shows only "Not saved"; `logon.html` save turns a non-JSON reply into `{}`.
      That is a silent fallback. Owner, earlier: *"which field is it not happy about?"*
      1. Show the server's reason beside "Not saved"
      2. Leave it
- [ ] **CAP-19 spec conflict.** `vessel-logon-spec.md` CAP-19 requires immediate durable creation; the
      owner chose explicit Save. Update CAP-19 and audit the ACC/WAT requirements that lean on it.
- [ ] **Trip ID collisions.** `tripRef` is issued state-wide in the real system; this branch allocates its
      own, so two branches will collide. Needs a branch prefix or a range split (`VARCHAR(16)` has room).
- [ ] **Alert delivery (ACC-5).** Alerts reach only whoever has a page open. Set and prove
      `RADIO_ALERT_WEBHOOK` or the `RADIO_ALERT_SMTP_*` settings; spec Appendix D question 17.

### Future list work (marked FUTURE in `~/Downloads/todo.png`)

Owner: *"i want an really clever column selector"*, *"i want the column widths to be smart"*,
*"i dont like the Vessel Details column ... needs to be done thoughtfully."*

- [ ] Column picker and named presets, built on Quackit's shared `record_grid` (no second grid).
- [ ] Split Vessel details into Length, Hull colour, Make, Model, Other, and decide how they condense
      when space is short and which columns show by default.
- [ ] Define "smart" widths before building (content-sized up to a cap, blank columns shrink).

### Clean-up

- [ ] Remove `logons.rename_statuses` and `STATUS_RENAMES` once 8080 and every other database has been
      converted (the checker logs `renamed N stored statuses` when it converts any).

- [ ] **`Identifiers` overlaps `LogOns_history`.** Every change to Member No., Rego, Mobile and Vessel
      Name is already in history; `Identifiers` adds the normalised copy the identity check matches
      earlier trips on. Owner, 2026-09-13: leave it for now; replacing it is a separate decision.
- [ ] A closed log on shows the yellow DRAFT badge beside the RadioLogs button (`ui.cond` treats every
      not-watched record as a draft). Seen on the History screenshot.
- [ ] Logged on by / Entered by store the quackit user id (history shows `4`); the event's own person
      is named. Name them through `Host` if wanted.

- [ ] Consolidate the Quackit UI duplicates listed in `DRY-CATALOG.md` (compact toggles, context combo
      enhancement, old attachment macros). The catalog lists them; none is extracted yet.
