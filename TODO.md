# Radio Operator TODO

Current state and open work. Read Quackit's `DRY-CATALOG.md` and `DEVELOPMENT.md` first: they own
reuse, verification (`./verify`) and rollout. History lives in the commit log and
`quackit/WORKLOG-radio.md`; superseded notes are not kept here.

## Built (as of 2026-09-14)

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
  line; **Paragraphs**, a line per field (or wrapped row values). The table opens with Paragraphs on
  (values wrap in full); cards open with it off (one line). Each view keeps its own choice. Kept across refreshes, not across
  page loads. Text size buttons (A−, 100–200%, A+, reset) grow the list's text, symbols and icons;
  remembered in this browser.
- Draft rows show what still blocks Accept as an orange `?` (after its symbol on cards, in the cell on rows);
  other empty fields stay blank. Logged-on and closed rows show no `?`.
- Rows tinted faintly by status: draft orange, logged on green, overdue red, closed near-black.
- Dates always carry a 2-digit year (`Sun 13/9/26`); times always 4-digit 24-hour (`1400`).
- Daily `No.` counts from 1 per call date; `Trip ID No.` (`T-00042`) is the record's key.
- Overdue alerts on the page: pulse, count in the blinking tab title and beep until **Seen** is
  pressed. The owner decided this stays (Seen stops it). An alert goes the moment its cause does: a log off, discard or save resolves
  that log on's alerts (`watch.settle`, the checker's own rule), and the 30 s refresh swaps the alert strip too, so a
  raised or cleared alert shows without a reload; the beep and title flash follow the strip (fixed 2026-09-14).

### Log on form (`/logon/<id>`, `/logons/new`)

- The page shows the record's status large, with the log's symbol and word (📝 Draft, 👀 Logged on,
  🚨 Overdue, ✅ Logged off, 🏠 Never departed, 🗑️ Discarded). Tabs: Log on and History only.
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

- Reached from the RadioLogs navbar (Members, Public vessels); neither list links to the other. Lists through
  Quackit's `record_grid`, server search swapped in by htmx like the log.
- A member: Member No. issued automatically as `m00001`, first name and last name (both required), Mobile Phone
  Number (the log on's rule: 10 digits, shown `0412 345 678`), email, address. Listed by last name. Tabs (Quackit's
  shared `entity_nav.tabs`): Details, Emergency contacts, Vessels, Trailers, Cars, History. Any number of
  each. Each of those four tabs is a list like the log (Quackit's `record_grid`: one row each, Cards / Paragraphs /
  text size, search over the rows) with an Add button; a row opens its own page to edit or Remove it. Remove
  makes a row inactive, never deletes it. The Members and Public vessels lists have the same view buttons.
- A public vessel is the record for a public user: the boat plus its owner's name and phone (both required)
  and email. A vessel needs a name or a rego.
- Emergency contact and owner phones follow the same mobile rule (10 digits, written `0412 345 678`); email needs an @. A refused save
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
  320–2560px, accept, log off; members with vessel and contact, public vessel, a Member No. that is not a member
  kept in Notes, Member or public user picks and new vessels saved from the log on page).

## Open

### Decisions waiting on the owner


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
      state names, ACC-1, CAP-24, ACC-9); the Markdown is current. README "Updating the documents" has the steps.
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

### Members follow-ups (not built)

- [ ] Identity check and one-box search (`identity.py`) still read trip history only, not the member and vessel records.
- [ ] Values filled from a picked member or vessel are recorded as heard on the call (`Identifiers.source = 'call'`).
      IDV-1 says a value applied from a record does not corroborate; they should be `profile`. Hidden while the
      identity check is set aside.
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
      (still computed, shown nowhere); Still to ask; the Heard list; reopening a closed record (route kept,
      no button); the log off reason (always "returned"). `_ui.html` find, find_script and verification
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
- [ ] The RadioLogs toolbar search uses Quackit's `search_controls`, which still writes "Search.." inside the box.
      The owner's rule is a label on top (DRY-CATALOG.md "Owner's standing UI rules"); fix it on Quackit's owner.
