# Radio Operator TODO

Current state and open work. Read Quackit's `DRY-CATALOG.md` and `DEVELOPMENT.md` first: they own
reuse, verification (`./verify`) and rollout. History lives in the commit log and
`quackit/WORKLOG-radio.md`; superseded notes are not kept here.

## Built (as of 2026-09-14)

### Radio Logs as its own program

- Quackit's menu keeps its **RadioLogs** link; every radio page then uses `radio/_layout.html` (Quackit's page shell
  with the Radio Logs menu: the brand, with Quackit's 🏠 home icon, is the log; New log on, Members, Public vessels,
  Search, Help, Log out). A page title never repeats that icon.
  Browser tab and brand "Radio Logs" (`Host.brand`). No link back to Quackit (owner). The standalone shell draws the
  same menu (`_ui.radio_menu`). Page links the menu covers are gone.
- **Help** (`/radio/help`): the menu, the log, every view button (the real controls on sample rows), status symbols,
  a log on, members and public vessels, Search and every field emoji.
- Every field is named with its emoji, the same wherever it appears (form labels, list headings and cards, History,
  pickers): one map, `_ui.FIELD_SYMBOLS`.

### Shared list views (every table/card list: the log, Members, Public vessels, Search, member tabs)

- Quackit's `record_grid` with `view_controls`: **Cards** (at any width), **Paragraphs** (row values wrap), text size
  A− / A+ / reset (remembered), **width** (usual ~1200px container or full width, remembered per page) and, where a
  page has one, the **panel** button (remembered per page). No Lines button (owner, 2026-09-14): cards, however they
  come, are always a line per field, its name on one line and its value ending in ….
- **Words never split** (owner: *"never ever break something mid-word"*): text wraps only between words (record_grid's
  `words`, no `overflow-wrap: anywhere`), a badge is one piece, column names (headings and card labels) are one line.
- **Columns fit what they hold**: the heading and every row share one set of columns (subgrid); a column is as wide as
  its values need and the room goes to the long ones (Status is just its symbol). The pages set no widths (only the
  open button's 2.5rem). With Paragraphs a column is never narrower than its longest word; when the columns cannot
  fit, the list shows the phone cards instead (`dc-record-grid-stacked`). The operator's normal screen is 1920px
  wide (owner, 2026-09-14): the log must be rows there; narrower, with Paragraphs, it may be cards.
- Every list numbers its records from 1 (# column, or the card's corner), numbered again after a row search.
- The side **panel** sits left of the list, in the page margin when there is room (the list does not move), and shows
  what the search matched in which field as badges with counts. On Search it starts open and a badge filters the
  results (yellow **Filter applied** bar, Clear filter); on the log, Members and Public vessels it starts closed and
  the badges are plain (`_ui.matched_panel`, `members.matched` / `list_matched` / `narrow`, `logons.matched_fields` /
  `matched_rows`).
- **🔎 Search** (`/radio/search`): one box over log ons, members, emergency contacts, vessels, trailers and cars, any
  field including notes, each kind a collapsible group (collapse / expand all; remembered), usual ~1200px width; rows
  open their record (`members.find`, `logons.records`).
- The member, public vessel and contact / vessel / trailer / car pages (new and edit) are at the usual ~1200px width.

### The log (`/logons`)

- One collection through Quackit's shared `record_grid`: compact aligned rows on desktop/tablet,
  labelled cards at phone width, paper-log column order, width capped at 1920px.
- Toolbar: status (All, Drafts, Logged on, Overdue, Closed; default All), call date (default today,
  untickable; ◀ / ▶ move a day, **Today** shows only on another day: Quackit's `date_filter`, owner issue n), sort (Newest first by default, Oldest first, **Due first**), search. It rides in Quackit's
  fixed navbar (`data-navbar-controls`), so it stays on screen while the log scrolls. Swapped in place by
  Quackit's htmx; state kept in the URL; 30s refresh.
- Due first: overdue, then by return time; drafts and closed after, newest call first. One rule,
  `logons.due_first`, also used by `queue()`.
- Columns: #, 🚦 Status (the status symbol, with its accessible name), the call's details, 🎫 Trip ID No. last.
  Member No. and Vessel Name are separate columns. Every column heading carries its symbol beside the word (📅 Date, 👤 Member No., 🛥️ Vessel Name,
  🔖 Rego …) so operators learn them; cards show the symbol and the word on each field's line.
- The table opens with Paragraphs on (values wrap in full). View choices survive the 30 s refresh.
- Draft rows show what still blocks Accept as an orange `?` (after its symbol on cards, in the cell on rows);
  other empty fields stay blank. Logged-on and closed rows show no `?`.
- Rows tinted faintly by status: draft orange, logged on green, overdue red, closed near-black.
- Dates always carry a 2-digit year (`Sun 13/9/26`); times always 4-digit 24-hour (`1400`).
- **No daily number** (spec 1.1 REC-9, owner 2026-09-14): a log on is named by its `Trip ID No.` (`T-00042`)
  everywhere (titles, alerts, links). `dayNumber` / `dayDate` are gone from the schema, dropped on port 80.
- Overdue alerts on the page: pulse, count in the blinking tab title and beep until **Seen** is
  pressed. The owner decided this stays (Seen stops it). An alert goes the moment its cause does: a log off, discard or save resolves
  that log on's alerts (`watch.settle`, the checker's own rule), and the 30 s refresh swaps the alert strip too, so a
  raised or cleared alert shows without a reload; the beep and title flash follow the strip (fixed 2026-09-14).

### Log on form (`/logon/<id>`, `/logons/new`)

- The page shows the record's status large, with the log's symbol and word (📝 Draft, 👀 Logged on,
  🚨 Overdue, ✅ Logged off, 🏠 Never departed, 🗑️ Discarded). Tabs: Log on, the 👤 Member / 🌐 Public vessel tab once
  one is picked, History.
- Five paper rows on the Log on tab: Date | Time; Member No. | Vessel Name | Rego | Mobile;
  Length | Hull colour | Make | Model; POB | Departure | Going to; Return day | Time. Then Notes (three lines,
  grows), back on the form since 2026-09-14: the only notes box. Log off saves what is in it; the separate
  log off Note is gone (old rows keep their `loggedOffNote`, shown in History).
- Explicit save only: nothing is written until Save, one save is one update and one history event,
  a stale version is refused visibly (409), leaving with unsaved changes warns.
- Yellow Save (Quackit's "changes data" colour) in the navbar and first in the bottom row of every
  editable pane. A draft's bottom row: Save · reason · Discard draft.
- **Saving a complete draft logs it on** (spec v1.1 ACC-3): no Accept button. A save that leaves the
  mandatory set short keeps a draft; so does one refused because the vessel already has an open log on.
- A log on cannot lose its mandatory set: a save that would empty or make unreadable POB, departure,
  going to, the return day/time or the second ID is refused, nothing written, those boxes red (ACC-1, WAT-10).
- Discard keeps the record, marked never a log on, with its required reason (ACC-7).
- **Log off** and **Discard draft** ask first in Quackit's confirm box, naming the log on and vessel (Cancel focused).
  A logged-off log on or discarded draft has **Reopen** with a reason (§3.3, AC-36; `logons.reopen`), also confirmed
  ("Are you sure you want to Reopen this log on?", nothing more; owner, issue C): back on the watch (deadline checked at once) or back to a draft; the closure stays in History.
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

### Members and public vessels (`/members`, `/member/<id>`, `/vessels`, `/vessel/<id>`)

- Reached from the Radio Logs menu. Lists through
  Quackit's `record_grid`, server search swapped in by htmx like the log.
- A member: Member No. issued automatically as `m00001`, first name and last name (both required), Mobile Phone
  Number (the log on's rule: 10 digits, shown `0412 345 678`), email, address, notes (a text box that grows). Listed by last name. Tabs (Quackit's
  shared `entity_nav.tabs`): Details, Emergency contacts, Vessels, Trailers, Cars, History. Any number of
  each. Each of those four tabs is a list like the log (Quackit's `record_grid`: one row each, Cards / Paragraphs /
  text size, search over the rows) with an Add button; a row opens its own page to edit or Remove it. Remove
  makes a row inactive, never deletes it. The Members and Public vessels lists have the same view buttons.
- **Removed stays visible** (owner, issue i, 2026-09-15): a removed contact, vessel, trailer or car stays on its tab after the
  current ones, shown by each tab's **Status** choice (Current, the start; 🚫 Removed; All — Quackit's row filter `choices`,
  owner issue p), faded and dashed like a Discarded log on, with 🚫 Removed and the day, and no open button. History names
  which record each event is about ("Vessel · Sea Dog · AB123Q", by its latest values) and shows Remove as Status:
  Current → 🚫 Removed.
- **Not current on old log ons** (owner, issues h and i): a log on keeps what it was given. When its vessel has since been
  removed, its Vessel Name and Rego show ⚠️ and fade (tooltip "Vessel removed from m00001 on Tue 15/9/26"); when its
  member (or public vessel) now has another number, its Mobile does ("m00001's mobile is now 0499 000 111"). The log, its
  refresh and Search (`members.not_current` from `logons.records`); the log on page shows the removed vessel's badge and a
  note under Vessel Name and Mobile, and saving that log on keeps its vessel. A removed vessel cannot be picked anew.
- A public vessel is the record for a public user: the boat plus its owner's name and phone (both required),
  email and **notes** (a text box that grows), with an **Emergency contacts** tab like a member's and a History that
  includes its contacts' changes. A vessel needs a name or a rego. Contacts, vessels, trailers and cars share one set
  of pages whichever holds them (`/<member|vessel>/<id>/<kind>/…`, `members.OWNERS`).
- Emergency contact and public vessel contact phones follow the same mobile rule (10 digits, written `0412 345 678`); email needs an @. A refused save
  writes nothing, keeps what was typed and turns its boxes red; each form comes back to its own tab.
- **A log on is a member's or a public user's** (owner, 2026-09-14; spec CAP-24). The Member No. box offers the
  unit's members; a number that is not a member is emptied as focus leaves the box and written into **Notes**
  as `Member No. heard: m00128 (no such member)`. A save does the same if it gets there first; nothing is
  refused. No member = public user log on.
  The rego ties the log on to a vessel record when it names exactly one (the member's own vessels, else the
  public vessels). The log shows 👤 Member No. or 🌐 Public in the Member No. column; the log on page shows
  the member or public vessel it is tied to, linked. A number saved before members existed stays until changed.
- Once a member or public vessel is picked (or the record has one), the log on page gets a **👤 Member** or
  **🌐 Public vessel** tab beside Log on: that record's own page content (Details, the four lists, History),
  loaded in place and fully usable. Picking someone else reloads it.
- A member's **History** holds every change they hold: their details and each emergency contact, vessel, trailer
  and car, each event marked with what it changed, filterable by that.
- **Member or public user** is the first row of the log on form (2026-09-14). Member: Quackit's shared search
  picker finds the member, then one of their vessels (or No vessel, or New vessel for this member). Public user:
  a public vessel, or New public vessel. Picks fill Member No., the vessel boxes and an empty mobile, and link the
  record by `vesselId`; new vessels are saved from the page and picked at once. Typing over Member No., Vessel
  Name or Rego drops the pick, and the rego decides again. **✕ Remove** beside the choice undoes it: Member No., the
  vessel boxes and the vessel link are emptied and the tab goes; Mobile stays.
- Superseded the same day (owner): the choice shows as badges, **👤 member** and **🛥️ vessel** (or 🌐 public), each with
  its own ✕; ✕ on the vessel keeps the member, and **🛥️ Vessel** picks one of theirs. What a pick fills is the
  record's: Member No. is set only by picking (a heard number that is not a member: "Not a member: note it" in the
  member search puts it in Notes), and with a member or public vessel picked the vessel boxes are read only;
  Mobile stays typeable. A member with no vessel has none. The server takes those values from the records on a
  form save (`logons._record_values`). Corrections are made on the Member / Public vessel tab, which saves in place
  (records open inside it) and refreshes the boxes and badges.
- **How they logged on** (Radio / Phone / In person) is in the first row, beside Date and Time.
- The "Member or public user" row also has **🛥️ Vessel** (every vessel, a member's or public: a member's vessel brings its
  member), **📱 Mobile** (members' mobiles, public vessel owners' phones and emergency contacts' phones; picks the member or
  public vessel the number belongs to and fills an empty Mobile) and **🔎 Search** (the Search page in a new tab).
  The log's own search matches departure point and notes too.
- The log on's pickers are Quackit's SearchPicker, rebuilt 2026-09-14 on the shared pieces (owner: *"reusable
  components … numbered index … how many have been found"*): the search box is `search_controls` with its label on top,
  and the results are the same `record_grid` lists the pages use, under "N found", numbered, rows or cards, a row
  picked by click or arrow keys + Enter. Member: the Members list; a member's vessel: their Vessels tab list; Vessel
  and Public user: the Public vessels list with 🤲 Held by (👤 member or 🌐 public); Mobile: 📱 Mobile and one Whose
  column, never blank (👤 member; 🧑 contact · 🌐 the vessel; 🆘 emergency contact · 👤 / 🌐 who holds it; owner, issue D,
  `_ui.mobiles_grid`). Every row value has its field's emoji before it and headings are words only (owner, issues A and E: record_grid
  `symbol`); rows tight from the left; a public vessel's person is 🧑 Contact / 📱 Phone / ✉️ Email, never
  Owner (owner, issue F: the caller need not own it); Search's Clear filter is at the top of its side panel, above the
  kinds (issue G); an Emoji only view button hides column names; Discarded is its own status filter, never Closed; the log's status column has no heading word, Date is Logon date, Return date 🏁. Emoji in the title, step and label
  (👤 Member, 🌐 Public user, 🛥️ Vessel, 📱 Mobile). The box is a contained page wide (120ch) and 80% of the screen tall.
- Tables `Members`, `EmergencyContacts`, `Vessels`, `Trailers`, `Cars` (with history); `LogOns.memberId`,
  `LogOns.vesselId`; `Members.firstName`, `lastName`, `mobile` (replacing `name`, `phone`). Migrated on port 80.
  8080 is the owner's to migrate (the first set done 2026-09-14; the name/mobile change is in the generator's
  output, its drops in the destructive file).

### Behind it

- One record table, `LogOns`, with one status column (`watchStatus`: draft, loggedOn, loggedOff,
  discarded; renamed from watching / loggedoff on 2026-09-13, converted by the checker's first pass). quackit's migration generator gives it `LogOns_history` and triggers. The **History** tab
  shows that history in quackit's shared viewer (through `Host.history`), statuses with their emoji
  and fields with the log's symbols; the old summary line is gone.
- Side tables: `Identifiers` (every ID value heard), `Alerts` (what the checker raised), `WatchHealth`
  (the checker's heartbeat and lease).

- Deadline checker runs without a browser, raises and clears alerts, records delivery.
- Radio data only through `Host`; the standalone shell loads Quackit's real shared templates and assets.
- `./verify` covers Quackit and radio: Python tests, DOM tests (including the shared search picker), and the
  browser check on port 80 / MariaDB in Chromium and Firefox (save, red boxes, conflicts, search, sort, layout
  320–2560px with no split word, one-line column names and cards only when rows do not fit, accept, log off; members
  with vessel and contact, public vessel, a Member No. that is not a member kept in Notes, Member or public user picks
  by click and keys, the picker's size and lists, and new vessels saved from the log on page).

## Open

### Decisions waiting on the owner

- [ ] **8080 is behind.** Its web container last started 2026-09-15 12:04, before quackit `22c38d0` / radio `5778f12`
      (12:19): the log's date arrows and Today (issue n), the tabs' Status choice (issue p) and Quackit issues o, q, r are
      not on it. Needs another `. myUpdate` in `~/personalDb` (owner's call). 8080's own migrations are the owner's: members' name/mobile, notes, emergency
      contacts on public vessels, and dropping `dayNumber` / `dayDate`. Read 8080's generated destructive file before
      executing: on port 80 it also dropped old leftovers (tables `DocumentAttachments`, `AttachmentsNP`; columns
      `LogOns.captureStatus`, `Members_history.name` / `phone`, six `Attachments` columns) and made five columns NOT NULL.
- [ ] **Leftover index.** `uniq_logons_daynumber` stays on `LogOns`, now on `unit` only: the migration manager never
      drops an index a schema stops declaring.
      1. Extend the migration manager to propose dropping such indexes (destructive file)
      2. Leave it (harmless)

- [ ] **"Due soon".** Owner, 2026-09-13: *"i dont want due soon"*. A logged-on record within 30 minutes
      of its return still shows a yellow `Due in n min` badge (`_ui.html` `cond`), and the watcher still
      has an approaching window (`RADIO_APPROACHING_MINUTES`).
      1. Remove the approaching state: the badge reads the same until overdue
      2. Keep the badge, only no row colour of its own (as now)
- [ ] **Failed save gives no reason.** A save refused for something other than a field (server error,
      too long, bad channel) shows only "Not saved"; `logon.html` save turns a non-JSON reply into `{}`.
      That is a silent fallback. Owner, earlier: *"which field is it not happy about?"* Also hit by a picked
      vessel the server refuses ("That vessel is not one of this member's vessels").
      1. Show the server's reason beside "Not saved"
      2. Leave it
- [ ] **Spec PDF is behind.** `vessel-logon-spec.pdf` has not been regenerated since the v1.1 changes (ACC-3,
      state names, ACC-1, CAP-24, ACC-9, REC-9 Trip ID No.); the Markdown is current. README "Updating the documents" has the steps.
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
- [x] Smart widths, first cut (2026-09-14): columns sized by content, never narrower than a word with Paragraphs,
      cards when they cannot fit. Still open: a cap per column, and phone numbers / dates wrapping at their spaces
      in narrow rows ("0412 / 345 / 678").
      1. Keep phone numbers, dates and times as one piece (a `record_grid` column option)
      2. Leave it

### Pickers and views follow-ups (2026-09-14)

- [ ] **Radio picker searches have no limit**: "04" lists 587 numbers, an empty Vessel search 592 vessels (Quackit's stop
      at 40–60 and say "N shown, more found").
      1. Cap them the same way (e.g. 60)
      2. Leave them
- [ ] The Mobile picker's **Whose** heading has no emoji (its badges do). Pick one, or leave it.
- [ ] **Paragraphs does nothing on cards** now that cards are always a line per field.
      1. Hide it while cards show
      2. Make it wrap card values under their one-line names
- [ ] The log's `COLUMNS` (`_ui.html`) still writes its own open-button column instead of `OPEN_COLUMN`.

### Members follow-ups (not built)

- [ ] Identity check and one-box search (`identity.py`) still read trip history only, not the member and vessel records.
- [ ] Values filled from a picked member or vessel are recorded as heard on the call (`Identifiers.source = 'call'`).
      IDV-1 says a value applied from a record does not corroborate; they should be `profile`. Hidden while the
      identity check is set aside.
- [ ] Removing a contact / vessel / trailer / car still asks with the browser's own "Remove this?" box, not Quackit's
      confirm box (`logon.html` / member tabs, `data-ro-remove`).
- [ ] Members and public vessels cannot be removed (only a member's contacts, vessels, trailers and cars can).
      The browser check therefore leaves per run on port 80: one `Verify Member …` with vessels `VERIFY-…` and
      `NEWBOAT-…`, and public vessels `PUBLIC-…` and `NEWPUB-…`.

### Clean-up

- [ ] The log on page has its own tab script (`logon.html`, `data-ro-tab`); member and vessel pages use Quackit's
      `entity_nav.tabs`. Move the log on page onto the shared tabs.

- [ ] **Set aside on 2026-09-13, to be redone properly:** the log on page's Contact, Vessel, Identity and Record
      tabs (owner: *"all these fields are shit"*). Out of sight until then: departure, radio
      channel, contact, AIS, vessel type/details (values kept, not editable); Find and apply an
      earlier trip; the identity check's evidence, including IDV-1's "applied, so it does not corroborate"
      (still computed, shown nowhere); Still to ask; the Heard list; the log off reason (always "returned").
      (Reopening a closed record is back, with its own button, since 2026-09-14.) `_ui.html` find, find_script and verification
      macros and the page route's gaps/identifiers/verified values are unused until then.

- [ ] Remove `logons.rename_statuses` and `STATUS_RENAMES` once 8080 and every other database has been
      converted (the checker logs `renamed N stored statuses` when it converts any).

- [ ] **`Identifiers` overlaps `LogOns_history`.** Every change to Member No., Rego, Mobile and Vessel
      Name is already in history; `Identifiers` adds the normalised copy the identity check matches
      earlier trips on. Owner, 2026-09-13: leave it for now; replacing it is a separate decision.
- [ ] Logged on by / Entered by store the quackit user id (history shows `4`); the event's own person
      is named. Name them through `Host` if wanted.

- [ ] Consolidate the Quackit UI duplicates listed in `DRY-CATALOG.md` (compact toggles, context combo
      enhancement, old attachment macros). The catalog lists them; none is extracted yet.
- [ ] Move the hand-copied collapse / expand all toggles (`myMacro_listitems.html` days and weeks, the Assets timeline)
      onto `myMacro_groups.collapseAllButton`, and Listboard's own sidebar onto `record_panel` (Quackit).
- [ ] The log's toolbar search (and every list's) uses Quackit's `search_controls`, which still writes "Search.." inside the box.
      The owner's rule is a label on top (DRY-CATALOG.md "Owner's standing UI rules"). `search_controls(label=…)` exists
      now (the picker uses it); move each caller onto it.
- [ ] Quackit's history viewer (`history_changes.css`) still has `overflow-wrap: anywhere` for values, so a long word can
      split there.
- [ ] Listboard at 390px is ~44px too wide: its own toolbar icons (`bi-calendar-range`, `bi-text-paragraph`), Quackit.
