"""Real Flask routes and SQL on an isolated database with a test host; never uses a host's data."""
import re
import sys
import tempfile
from datetime import date
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask, g, session
from server import identity as ID
from server import logons as L
from server import watch as W
from server.host import Host
from server.routes import mount
from server.sqlite import Connection, create_schema
from fixtures import known_members


def test_app(path):
    create_schema(path)
    app = Flask(__name__)
    app.secret_key = 'isolated-test-fixture'
    app.add_url_rule('/login', 'login', lambda: 'test host login')

    class TestHost(Host):
        login_url = '/login'
        approaching_minutes = 30
        def connect(self):
            if 'db' not in g:
                g.db = Connection(path)
            return g.db
        def user(self):
            return session.get('user')
        def unit(self):
            return session.get('unit', '')
    mount(app, TestHost(), watch_every=0)      # the checker has its own tests; a timer here is noise

    @app.teardown_appcontext
    def close(_):
        if 'db' in g:
            g.db.conn.close()

    @app.route('/test-login/<user>/<unit>')
    def test_login(user, unit):
        session['user'] = user
        session['unit'] = unit
        return 'test login'
    return app


class Pages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = test_app(Path(self.tmp.name) / 'test.db')
        known_members(Connection(Path(self.tmp.name) / 'test.db'), 'unitA')
        self.app.testing = True
        self.a = self.app.test_client()
        self.a.get('/test-login/alice/unitA')
        self.b = self.app.test_client()
        self.b.get('/test-login/bob/unitB')
        self.new_count = 0

    def new(self, client=None):
        self.new_count += 1
        fields = {'callDay': date.today().isoformat(), 'callTime': '09:%02d' % self.new_count,
                  'mobile': '0400%06d' % self.new_count}
        r = (client or self.a).post('/logons/new', json={'fields': fields})
        self.assertEqual(r.status_code, 200, r.data)
        return r.json['id']

    def field(self, i, name, value, client=None):
        r = (client or self.a).post('/api/logon/%d' % i, json={'field': name, 'value': value})
        self.assertEqual(r.status_code, 200, r.data)
        return r.json

    def mandatory(self, i, rego='AB123Q', member='4471', day='today', time='1800'):
        """Everything ACC-1 asks for. Without it there is a draft, not a log on."""
        for name, value in (('registration', rego), ('memberNumber', member), ('pob', '3'),
                            ('departurePoint', 'Marina'), ('destination', 'Facing Island'),
                            ('etaDay', day), ('eta', time)):
            self.field(i, name, value)
        return i

    def save(self, i, **fields):
        """The form's Save: one batched write, which logs a complete draft on (ACC-3)."""
        r = self.a.post('/api/logon/%d' % i, json={'fields': fields})
        self.assertEqual(r.status_code, 200, r.data)
        return r.json

    def accepted(self, **kw):
        i = self.mandatory(self.new(), **kw)
        self.assertTrue(self.save(i)['accepted'])
        return i

    def test_not_logged_in_goes_to_the_hosts_login(self):
        c = self.app.test_client()
        r = c.get('/logons')
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.location.endswith('/login'))
        self.assertEqual(c.post('/api/logon/1', json={}).status_code, 302)

    def test_new_is_unsaved_until_the_minimum_is_explicitly_saved(self):
        page = self.a.get('/logons/new').get_data(as_text=True)
        self.assertIn('id="saveRecord"', page)
        self.assertIn('<div class="ro-primary-actions"><button type="button" class="btn btn-warning "', page)   # bottom Save on a new log on
        self.assertIn('>Not saved</span>', page)
        self.assertRegex(page, r'id="f-callDay"[^>]+value="[^"]+"')
        self.assertIn('id="f-callTime" class="form-control is-invalid" data-field="callTime" value=""', page)   # red from the first look
        self.assertNotIn("addEventListener('change', function () { save", page)
        self.assertIn('>0 drafts</div>', self.a.get('/logons?status=draft').get_data(as_text=True))

        missing = self.a.post('/logons/new', json={'fields': {'callDay': date.today().isoformat()}})
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(set(missing.json['fields']), {'callTime', 'memberNumber', 'registration', 'mobile'})
        self.assertIn('>0 drafts</div>', self.a.get('/logons?status=draft').get_data(as_text=True))

        saved = self.a.post('/logons/new', json={'fields': {
            'callDay': date.today().isoformat(), 'callTime': '08:15', 'registration': 'AB123Q'}})
        self.assertEqual(saved.status_code, 200, saved.data)
        row = self.a.get('/logons').get_data(as_text=True)
        self.assertIn('data-record="%d"' % saved.json['id'], row)
        self.assertIn('0815', row)                                    # listed 4-digit, whatever was typed

    def test_capture_page_shows_the_queue_and_saves_field_by_field(self):    # AC-1, AC-5, AC-6, CAP-7, CAP-19
        i = self.new()
        j = self.new()
        page = self.a.get('/logon/%d' % i).get_data(as_text=True)
        self.assertNotIn('id="queuePane"', page)
        self.assertNotIn('data-record="%d"' % j, page)         # other records belong only on /logons
        self.assertIn('data-field="eta"', page)
        self.assertIn('type="date" class="ro-native-picker" data-picker-target="callDay"', page)
        self.assertIn('data-now-for="callTime"', page)                 # the clock sets now: no browser time picker
        self.assertNotIn('type="time"', page)
        self.assertNotIn('Still to ask', page)                        # the Identity tab is gone for now
        self.assertNotIn('This is a draft, not a log on', page)       # what stops acceptance is shown red, not written
        self.assertIn('id="f-callTime" class="form-control" data-field="callTime" value="09', page)   # 09:0n reads back as 090n
        for name in ('pob', 'departurePoint', 'destination', 'etaDay', 'eta', 'memberNumber', 'vesselName', 'registration'):
            self.assertIn('id="f-%s" class="form-control is-invalid"' % name, page)
        self.assertIn('id="f-mobile" class="form-control" data-field', page)              # heard, so not red
        self.assertEqual(page.count(' data-save-record><i class="bi bi-floppy'), 2)         # navbar and the bottom row
        entry = page[page.index('id="ro-entry-pane"'):page.index('id="ro-history-pane"')]
        self.assertIn('action="/logon/%d/discard"' % i, entry)          # discard sits on the Log on tab's bottom row
        self.assertEqual(page.count('/discard"'), 1)
        self.assertIn('<label for="f-vesselName">Vessel Name</label>', page)
        self.assertNotIn('function minimum', page)                   # the rule lives on the server only
        # leaving a box asks the server which boxes are red; nothing is written
        red = self.a.post('/api/logon/%d' % i, json={'check': True, 'fields': {
            'callDay': date.today().isoformat(), 'callTime': 'soon', 'pob': 'abc', 'mobile': '0400000001'}})
        self.assertEqual(red.status_code, 200, red.data)
        self.assertTrue({'callTime', 'pob', 'departurePoint', 'etaDay', 'eta'} <= set(red.json['red']), red.json)
        self.assertNotIn('mobile', red.json['red'])
        # nothing written: the version-0 save below still succeeds
        new = self.a.post('/logons/new', json={'check': True, 'fields': {'callDay': date.today().isoformat()}})
        self.assertEqual(new.status_code, 200, new.data)
        self.assertTrue({'callTime', 'memberNumber', 'registration', 'mobile'} <= set(new.json['red']), new.json)
        r = self.a.post('/api/logon/%d' % i, json={'field': 'eta', 'value': '3pm', 'version': 0})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.json['version'], 1)
        self.assertIsNone(r.json['when'])                          # a time with no day is not a deadline
        self.assertFalse(r.json['invalid'])
        self.assertIsNone(r.json['warning'])
        r = self.a.post('/api/logon/%d' % i, json={'field': 'etaDay', 'value': 'today', 'version': 1})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.json['when'].endswith('T15:00:00'))
        self.assertEqual(r.json['display'][:3], date.today().strftime('%a'))   # the box now shows the date
        self.assertNotIn('eta', [g['field'] for g in r.json['gaps']])
        self.assertEqual(self.a.post('/api/logon/%d' % i, json={'field': 'eta', 'value': '4pm', 'version': 0}).status_code, 409)
        self.assertEqual(self.a.post('/api/logon/%d' % i, json={'field': 'nope', 'value': '1', 'version': 2}).status_code, 400)
        self.assertEqual(self.a.post('/api/logon/%d' % i, json={'field': 'vesselName', 'value': 'Sea Dog', 'version': 2}).status_code, 200)
        listing = self.a.get('/logons').get_data(as_text=True)
        self.assertIn('Sea Dog', listing)
        self.assertIn('hx-get="/logons/rows"', listing)
        rows = self.a.get('/logons/rows?partial=1&current=%d&f=1&status=draft&q=Sea+Dog' % i)
        self.assertIn('Sea Dog', rows.get_data(as_text=True))
        self.assertEqual(rows.headers['HX-Replace-Url'], '/logons?f=1&status=draft&q=Sea+Dog')

    def test_a_log_on_has_a_history_tab_and_no_summary_line(self):
        i = self.new()
        page = self.a.get('/logon/%d' % i).get_data(as_text=True)
        self.assertIn('data-ro-tab="history" aria-controls="ro-history-pane"', page)
        self.assertIn('This host keeps no change history.', page)             # this test host keeps none: said, not blank
        self.assertNotIn('<strong>This system</strong>', page)                  # the summary line is gone
        self.assertNotIn('data-ro-tab="history"', self.a.get('/logons/new').get_data(as_text=True))
        for column in ('etaRaw', 'callTimeRaw', 'watchStatus', 'acceptedBy', 'mobile', 'pob'):
            self.assertIn(column, L.HISTORY_LABELS)

    def test_capture_page_leads_with_the_five_operator_rows(self):
        page = self.a.get('/logon/%d' % self.new()).get_data(as_text=True)
        entry = page[page.index('id="ro-entry-pane"'):page.index('id="ro-history-pane"')]
        self.assertIn('data-ro-tab="entry"', page)
        self.assertIn('id="ro-history-pane" class="ro-workspace-pane d-none"', page)
        for tab in ('contact', 'vessel', 'identity', 'record'):                   # set aside until they are done properly
            self.assertNotIn('data-ro-tab="%s"' % tab, page)
            self.assertNotIn('id="ro-%s-pane"' % tab, page)
        self.assertIn('<span class="ro-status-now" data-status="draft">', page)     # the log's symbol and word, large
        self.assertIn('>Draft</span>', page)
        self.assertNotIn('data-ro-tab="watch"', page)
        self.assertNotIn('id="ro-watch-pane"', page)
        self.assertEqual(entry.count('class="capture-row row g-3"'), 5)
        rows = entry.split('class="capture-row row g-3"')[1:]
        for row, fields in zip(rows, (
                ('callDay', 'callTime'),
                ('memberNumber', 'vesselName', 'registration', 'mobile'),
                ('length', 'hullColour', 'make', 'model'),
                ('pob', 'departurePoint', 'destination'),
                ('etaDay', 'eta'))):
            for field in fields:
                self.assertIn('id="f-%s"' % field, row.split('capture-row row g-3', 1)[0])
        self.assertNotIn('id="queuePane"', page)
        self.assertIn('font-size:1.2rem', page)
        self.assertNotIn('<table', page)
        self.assertNotIn('placeholder=', page)                              # nothing written inside a box; labels go on top
        self.assertIn('<label for="discardReason">Reason</label><textarea id="discardReason" name="reason" form="discardForm" class="form-control" rows="3" data-auto-grow', entry)
        self.assertNotIn('class="ro-basis"', entry)
        self.assertNotIn('class="ro-warn"', entry)
        self.assertNotIn('max-width:72rem', page)

    def test_only_malformed_values_are_marked_invalid(self):
        i = self.new()
        self.assertFalse(self.field(i, 'callDay', '2026-09-11')['invalid'])
        self.assertFalse(self.field(i, 'callTime', '09:00')['invalid'])
        self.assertFalse(self.field(i, 'etaDay', '2026-09-13')['invalid'])
        self.assertFalse(self.field(i, 'eta', '15:00')['invalid'])
        self.assertTrue(self.field(i, 'eta', '25:70')['invalid'])
        self.assertTrue(self.field(i, 'etaDay', '2026-02-31')['invalid'])

    def test_one_filtered_list_replaces_the_per_status_tabs(self):
        draft = self.new()
        watching = self.accepted(rego='CD456Q', member='7788')
        page = self.a.get('/logons').get_data(as_text=True)

        # One toolbar, not a tab per status, and not a renderer per status either.
        self.assertNotIn('data-ro-tab="drafts"', page)
        self.assertNotIn('data-ro-tab="overdue"', page)
        self.assertIn('id="roStatus"', page)
        for value in ('all', 'draft', 'loggedon', 'overdue', 'closed'):
            self.assertIn('value="%s"' % value, page)
        self.assertIn('id="roDayOn"', page)
        self.assertIn('id="roSort"', page)
        self.assertIn('name="q"', page)

        # All by default, for today, newest first.
        self.assertIn('<option value="all" selected>📋 All</option>', page)
        self.assertIn('id="roDayOn" name="dayOn" checked', page)
        self.assertNotIn('id="roDayOn" name="dayOn" checked', self.a.get('/logons?status=all').get_data(as_text=True))  # a link for all: every day
        self.assertIn('<option value="newest" selected>Newest first</option>', page)
        self.assertIn('<option value="due">Due first</option>', page)
        self.assertIn('data-dc-record-view="cards" aria-controls="roRecordView"', page)          # shared view buttons
        self.assertIn('data-dc-record-view="paragraphs" data-rows="1" data-cards="0" aria-controls="roRecordView"', page)   # rows wrap by default
        for step in ('smaller', 'larger', 'reset'):                                               # shared text size buttons
            self.assertIn('data-dc-record-size="%s" aria-controls="roRecordView"' % step, page)
        self.assertIn('<div id="roRecordView"><div id="roLiveRecords">', page)
        self.assertIn('data-navbar-controls="RadioLogs filters"', page)                             # lives in the navbar                    # outside what refreshes replace
        self.assertIn('<option value="due" selected>Due first</option>', self.a.get('/logons?f=1&sort=due').get_data(as_text=True))
        self.assertEqual(self.a.get('/logons?f=1&sort=sideways').status_code, 400)
        self.assertIn('data-record="%d"' % draft, page)
        self.assertIn('data-record="%d"' % watching, page)      # All: the watch is listed too
        self.assertNotIn('data-record="%d"' % watching, self.a.get('/logons?status=draft').get_data(as_text=True))   # a watch is not a draft

        # The paper log's columns: the record number leads, Trip ID No. is last (figure 5).
        self.assertIn('class="dc-record-grid-head"', page)
        head = page[page.index('class="dc-record-grid-head"'):page.index('</div>', page.index('class="dc-record-grid-head"'))]
        self.assertEqual([h.split('</span> ')[-1].split('</span>')[0] for h in head.split('<span title=')[1:]],
                         ['No.', 'Date', 'Time', 'Member No.', 'Vessel Name', 'Rego', 'Mobile', 'Vessel details', 'POB',
                          'Departure', 'Going to', 'Return date', 'Time', 'Trip ID No.'])
        self.assertIn('<span title="Member No."><span class="dc-record-grid-symbol">👤</span> Member No.</span>', head)
        self.assertIn('class="dc-record-card dc-record-grid-row ro-record-card draft', page)
        self.assertNotIn('<table', page)
        self.assertNotIn('Still needed', page)
        draft_at = page.index('data-record="%d"' % draft)
        draft_row = page[page.rfind('<article', 0, draft_at):page.index('</article>', draft_at)]
        self.assertNotIn('Unverified', draft_row)
        self.assertNotIn(' old', draft_row)

        # The same rows, the same renderer, a different filter.
        on = self.a.get('/logons?f=1&status=loggedon').get_data(as_text=True)
        self.assertIn('data-record="%d"' % watching, on)
        self.assertNotIn('data-record="%d"' % draft, on)
        # Same card class as the draft above -- one renderer. The state word after it depends on
        # the clock (an 1800 return is overdue after 1800), so it is not pinned here.
        self.assertIn('class="dc-record-card dc-record-grid-row ro-record-card', on)
        self.assertIn('class="dc-record-grid-head"', on)

        # Counts do not sit beside the filters (a number on a filter nobody picked is noise).
        self.assertNotIn('class="ro-status-counts"', page)
        # The site's own record classes, not a second look invented for radio.
        self.assertIn('class="dc-record-toolbar ro-toolbar"', page)

    def test_a_draft_row_shows_what_it_still_needs_as_a_question_mark(self):
        def row_of(page, i):
            row = page[page.index('data-record="%d"' % i):]
            return row[:row.index('</article>')]
        mobile_only = self.new()                                   # one ID: the other three are still needed
        rego_only = self.new()
        self.field(rego_only, 'mobile', '')
        self.field(rego_only, 'registration', 'AB123Q')
        watch = self.accepted(rego='WW111Q', member='9001')
        page = self.a.get('/logons').get_data(as_text=True)
        needed = lambda i: set(re.findall(r'aria-label="([^"]+) still needed"', row_of(page, i)))
        self.assertEqual(needed(mobile_only), {'Member No.', 'Vessel Name', 'Rego', 'POB', 'Departure', 'Going to',
                                               'Return date', 'Time'})
        self.assertEqual(needed(rego_only), {'Member No.', 'Vessel Name', 'Mobile', 'POB', 'Departure', 'Going to',
                                             'Return date', 'Time'})   # together: every column logons.missing can name
        self.assertEqual(needed(watch), set())                     # drafts only
        self.assertIn('dc-record-grid-blank" data-column="vessel"', row_of(page, mobile_only))  # not needed: stays blank

    def test_shared_record_presentation_keeps_identity_and_escapes_input(self):
        i = self.new()
        self.field(i, 'memberNumber', '12345')
        self.field(i, 'vesselName', '<img src=x onerror=alert(1)>')
        page = self.a.get('/logons').get_data(as_text=True)
        row = page[page.index('data-record="%d"' % i):]
        row = row[:row.index('</article>')]
        self.assertLess(row.index('aria-label="Draft"'), row.index('data-column="day"'))
        self.assertIn('data-column="member"', row)
        self.assertIn('data-column="vesselName"', row)
        self.assertNotIn('Member / Vessel', page)
        self.assertIn('12345', row)
        self.assertIn('&lt;img', row)
        self.assertNotIn('<img', row)
        self.assertIn('id="roSearch"', page)
        self.assertIn('data-search-input1="roSearch"', page)

    def test_status_symbols_distinguish_every_closure_and_conflict(self):
        ui = self.app.jinja_env.get_template('radio/_ui.html').module
        for watch, reason, condition, label in [
                ('draft', '', '', 'Draft'), ('loggedOn', '', 'future', 'Logged on'),
                ('loggedOn', '', 'overdue', 'Overdue'), ('loggedOff', 'returned', '', 'Logged off'),
                ('loggedOff', 'notdeparted', '', 'Never departed'), ('discarded', '', '', 'Discarded')]:
            r = dict(watchStatus=watch, closeReason=reason, condition=condition,
                     verifyOutcome='conflict', verifyBasis='different registration')
            html = str(ui.state_label(r))
            self.assertIn('aria-label="%s"' % label, html)
            self.assertEqual('aria-label="CONFLICT"' in html, watch != 'draft')

    def test_the_date_filter_is_a_tick_you_can_turn_off(self):
        i = self.new()
        # Ticked and set to another day: today's record is not in that day.
        away = self.a.get('/logons?f=1&status=draft&dayOn=1&day=2020-01-01').get_data(as_text=True)
        self.assertNotIn('data-record="%d"' % i, away)
        self.assertIn('>0 drafts</div>', away)
        # Unticked: the date stops narrowing anything, whatever is in the box.
        every = self.a.get('/logons?f=1&status=draft&day=2020-01-01').get_data(as_text=True)
        self.assertIn('data-record="%d"' % i, every)
        # Overdue starts with the date off, because an overdue record is never today's.
        overdue = self.a.get('/logons?status=overdue').get_data(as_text=True)
        self.assertNotIn('id="roDayOn" name="dayOn" checked', overdue)
        self.assertIn('<option value="draft">📝 Drafts</option>', overdue)

    def test_search_finds_a_record_by_what_an_operator_says_out_loud(self):
        i = self.new()
        self.field(i, 'registration', 'ZZ999Q')
        found = self.a.get('/logons?f=1&status=draft&q=ZZ999Q').get_data(as_text=True)
        self.assertIn('data-record="%d"' % i, found)
        missing = self.a.get('/logons?f=1&status=draft&q=NOSUCHTHING').get_data(as_text=True)
        self.assertNotIn('data-record="%d"' % i, missing)
        self.assertIn('>0 drafts</div>', missing)

    def test_empty_results_say_exactly_what_is_empty(self):
        for status, words in (('draft', '0 drafts'), ('loggedon', '0 logged on'),
                              ('overdue', '0 overdue'), ('closed', '0 closed'), ('all', '0 records')):
            page = self.a.get('/logons?f=1&status=%s' % status).get_data(as_text=True)
            self.assertIn('>%s</div>' % words, page)
            self.assertNotIn('Nothing at sea', page)
            self.assertNotIn('btn-outline-danger', page)       # a zero is not an alarm
        self.assertNotIn('No delivery channel', page)
        self.assertNotIn('reached nobody', page)
        self.assertNotIn('roAlarmState', page)

    def test_a_draft_is_not_watched_and_says_what_it_needs(self):        # AC-27, AC-50, ACC-1, ACC-2
        i = self.new()
        for name, value in (('etaDay', 'today'), ('eta', '0001'), ('pob', '3'), ('destination', 'Facing Island')):
            self.field(i, name, value)
        self.assertFalse(self.save(i)['accepted'])                        # short of the mandatory set: still a draft
        page = self.a.get('/logon/%d' % i).get_data(as_text=True)
        self.assertIn('data-status="draft"', page)
        self.assertNotIn('NOT WATCHED', page)
        self.assertNotIn('ro-record-card overdue', page)                  # the return time passed hours ago
        listing = self.a.get('/logons').get_data(as_text=True)
        self.assertNotIn('ro-record-card overdue', listing)
        self.assertNotIn('not watched', listing.lower())
        self.assertEqual(self.a.get('/api/logons/queue').json['loggedOn'], [])
        self.assertEqual(len(self.a.get('/api/logons/queue').json['drafts']), 1)

    def test_saving_a_complete_draft_logs_it_on_at_once(self):           # AC-51, AC-52, ACC-3, ACC-4
        i = self.mandatory(self.new(), time='0001')                       # a return time already long past
        self.assertEqual(self.a.get('/api/logons/queue').json['loggedOn'], [])   # filled in, not saved: nothing accepted
        page = self.a.get('/logon/%d' % i).get_data(as_text=True)
        self.assertNotIn('/accept"', page)                                # there is no Accept button
        saved = self.save(i)
        self.assertTrue(saved['accepted'])
        page = self.a.get('/logon/%d' % i).get_data(as_text=True)
        self.assertNotIn('Logged on and watched', page)                   # no words and no reason dropdown
        self.assertNotIn('name="reason" form="logoffForm"', page)
        self.assertNotIn('placeholder=', page)
        self.assertIn('<label for="f-notes">Notes</label>\n  <textarea id="f-notes" class="form-control" rows="3" data-auto-grow data-field="notes" name="notes" form="logoffForm"', page)
        self.assertEqual(page.count('<textarea'), 1)                         # one notes box: Log off carries it
        self.assertIn('data-status="overdue"', page)                      # overdue from the moment of acceptance
        self.assertIn('>Overdue</span>', page)
        listing = self.a.get('/logons?f=1&status=overdue').get_data(as_text=True)
        self.assertIn('aria-label="Overdue"', listing)
        self.assertIn('data-record="%d"' % i, listing)
        self.assertNotIn('class="ro-status-counts"', listing)
        self.assertEqual(self.a.get('/api/logons/queue').json['loggedOn'][0]['condition'], 'overdue')
        self.assertEqual(self.a.post('/logon/%d/accept' % i).status_code, 404)  # no separate accept action
        self.assertFalse(self.save(i)['accepted'])                        # saving a log on again changes nothing
        refused = self.a.post('/api/logon/%d' % i, json={'fields': {'pob': ''}})
        self.assertEqual((refused.status_code, refused.json['fields']), (400, ['pob']))   # a log on keeps its mandatory set

    def test_one_vessel_one_log_on(self):                                 # AC-53, ACC-6
        first = self.accepted()
        second = self.mandatory(self.new())
        self.assertFalse(self.save(second)['accepted'])                  # the vessel is already out: stays a draft
        page = self.a.get('/logon/%d' % second).get_data(as_text=True)
        self.assertIn('One vessel has one log on', page)
        self.assertIn('AB123Q', page)                                     # nothing captured was discarded
        self.assertEqual(self.a.post('/logon/%d/logoff' % first, data={'notes': 'back'}).status_code, 302)
        self.assertTrue(self.save(second)['accepted'])                   # now the vessel is free

    def test_a_draft_is_discarded_and_a_log_on_is_logged_off(self):       # AC-54, ACC-7
        d = self.new()
        self.assertEqual(self.a.post('/logon/%d/discard' % d, data={'reason': ''}).status_code, 400)
        self.assertEqual(self.a.post('/logon/%d/discard' % d,
                                     data={'reason': 'hit New by mistake', 'back': '/logons'}).status_code, 302)
        page = self.a.get('/logon/%d' % d).get_data(as_text=True)
        self.assertIn('data-status="discarded"', page)
        self.assertEqual(L.get(Connection(Path(self.tmp.name) / 'test.db').cursor(), d)['discardReason'], 'hit New by mistake')
        self.assertIn('Discarded', self.a.get('/logons?f=1&status=closed').get_data(as_text=True))
        self.assertEqual(self.a.post('/api/logon/%d' % d, json={'field': 'pob', 'value': '1'}).status_code, 400)
        i = self.accepted(rego='CD456R', member='9001')
        r = self.a.post('/logon/%d/discard' % i, data={'reason': 'tidying'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('logged off, not discarded', r.get_data(as_text=True))

    def test_numbering_counts_from_one_each_day(self):                    # AC-56, REC-9
        first, second = self.new(), self.new()
        page = self.a.get('/logon/%d' % second).get_data(as_text=True)
        self.assertIn('Draft 2', page)
        page = self.a.get('/logons').get_data(as_text=True)
        self.assertIn('<span class="dc-record-index">1</span>', page)
        self.assertIn('<span class="dc-record-index">2</span>', page)

    def test_the_log_off_control_is_not_trapped_inside_the_capture_form(self):
        """A form inside a form is dropped by the browser, which left the Log off button owned by
        the capture form and its submit handler returning false: the button did nothing at all."""
        i = self.accepted()
        page = self.a.get('/logon/%d' % i).get_data(as_text=True)
        inside = page[page.index('<form id="capture"'):]
        inside = inside[inside.index('>') + 1:]                  # past the opening tag itself
        inside = inside[:inside.index('</form>')]
        self.assertNotIn('<form', inside)                        # nothing nested inside it
        self.assertIn('form="logoffForm"', page)                 # the button is bound to its own form
        self.assertIn('action="/logon/%d/logoff"' % i, page)

    def test_search_and_apply_through_the_routes(self):          # SRCH-1 to SRCH-6, IDV-4
        first = self.new()
        for f, v in [('registration', 'AB123Q'), ('memberNumber', '4471'), ('mobile', '0412 345 678'),
                     ('vesselDetails', '6m white Quintrex'), ('destination', 'Facing Island')]:
            self.assertEqual(self.a.post('/api/logon/%d' % first, json={'field': f, 'value': v}).status_code, 200)

        self.assertEqual(self.a.get('/api/logons/search?q=a').json['hits'], [])          # one letter is not a search
        hits = self.a.get('/api/logons/search?q=ab123').json['hits']
        self.assertEqual(hits[0]['kind'], 'vessel')
        for q in ('4471', '0412 345', 'facing', 'AB12'):                          # any identifier, partial, same box
            self.assertTrue(self.a.get('/api/logons/search?q=' + q).json['hits'], q)

        second = self.new()
        offered = self.a.get('/api/logons/search?q=ab123&for=%d' % second).json['hits'][0]
        self.assertIn('Member No.', offered['offers'])                            # says what it would fill
        r = self.a.post('/logon/%d/apply' % second, json={'key': offered['key']})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIn('Member No.', r.json['filled'])
        page = self.a.get('/logon/%d' % second).get_data(as_text=True)
        start = page.index('<form id="capture"')
        form = page[start:page.index('</form>', start)]
        self.assertIn('4471', form)
        self.assertNotIn('Facing Island', form)                                   # a past trip is not this trip
        cur = Connection(Path(self.tmp.name) / 'test.db').cursor()                    # IDV-1: the check says so plainly
        got = ID.verify(cur, L.get(cur, second), L.identifiers(cur, second))           # (not on the page while Identity is set aside)
        self.assertTrue([e for e in got['evidence'] if not e['independent']], got)     # applied, so it corroborates nothing
        self.assertEqual(got['outcome'], 'unverified')                                # applied values prove nothing
        self.assertEqual(self.a.post('/logon/%d/apply' % second, json={'key': 'rego:NOPE'}).status_code, 400)

    def test_a_conflict_is_visible_on_the_record_and_the_queue(self):             # IDV-2, IDV-3, IDV-4
        for rego, member in (('AB123Q', '4471'), ('ZZ999X', '8802')):
            i = self.new()
            self.a.post('/api/logon/%d' % i, json={'field': 'registration', 'value': rego})
            self.a.post('/api/logon/%d' % i, json={'field': 'memberNumber', 'value': member})
        mixed = self.new()
        self.a.post('/api/logon/%d' % mixed, json={'field': 'registration', 'value': 'AB123Q'})
        r = self.a.post('/api/logon/%d' % mixed, json={'field': 'memberNumber', 'value': '8802'})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('CONFLICT', self.a.get('/logons?status=draft').get_data(as_text=True))  # draft rows are paper fields only
        for name, value in (('pob', '2'), ('departurePoint', 'Marina'), ('destination', 'Bay'),
                            ('etaDay', 'today'), ('eta', '2300')):
            self.field(mixed, name, value)
        self.assertTrue(self.save(mixed)['accepted'])                                  # IDV-5: a conflict blocks nothing
        self.assertIn('CONFLICT', self.a.get('/logons?f=1&status=loggedon').get_data(as_text=True))




    def test_a_closure_made_in_error_is_corrected_not_erased(self):       # §3.3 Correct mistaken closure
        i = self.accepted(time='0001')                                                # a return time long past
        self.assertEqual(self.a.post('/logon/%d/logoff' % i, data={'notes': 'thought it was back'}).status_code, 302)
        self.assertEqual(self.a.post('/logon/%d/reopen' % i, data={'reason': ''}).status_code, 400)
        self.assertEqual(self.a.post('/logon/%d/reopen' % i, data={'reason': 'wrong boat'}).status_code, 302)
        row = L.get(Connection(Path(self.tmp.name) / 'test.db').cursor(), i)          # History shows these on quackit
        self.assertEqual(row['reopenReason'], 'wrong boat')
        self.assertEqual(row['notes'], 'thought it was back')                         # the closure event is kept
        reopened = self.a.get('/logons?f=1&status=all').get_data(as_text=True)
        self.assertIn('data-record="%d"' % i, reopened)
        self.assertIn('OVERDUE', reopened)                                            # time did not stop
        self.assertEqual(self.a.post('/logon/%d/reopen' % i, data={'reason': 'again'}).status_code, 400)
        self.assertEqual(self.a.post('/api/logon/%d' % i, json={'field': 'pob', 'value': '2'}).status_code, 200)
        self.assertEqual(self.a.post('/logon/%d/logoff' % i,
                                     data={'reason': 'notdeparted', 'notes': 'never sailed'}).status_code, 302)

    def test_an_overdue_notice_goes_with_its_log_off_and_the_strip_refreshes(self):
        i = self.accepted(time='0001')                                                # a return time long past
        conn = Connection(Path(self.tmp.name) / 'test.db')
        W.sweep(conn.cursor(), L._dt(date.today().isoformat() + ' 23:59:00'), 15)       # the checker raises it
        conn.commit()
        page = self.a.get('/logons').get_data(as_text=True)
        self.assertRegex(page, r'<div id="roLiveAlerts">\s*<div class="ro-alerts">')
        self.assertIn('<a href="/logon/%d" class="fw-semibold">' % i, page)
        self.assertIn('hx-select-oob="#roLiveAlerts"', page)                          # the 30 s refresh brings the strip too
        self.assertEqual(page.count("querySelectorAll('#roLiveAlerts .ro-alert.unseen')"), 1)   # one alarm, reading the strip
        rows = self.a.get('/logons/rows?partial=1').get_data(as_text=True)
        self.assertIn('<a href="/logon/%d" class="fw-semibold">' % i, rows)
        self.assertEqual(self.a.post('/logon/%d/logoff' % i, data={'notes': 'back'}).status_code, 302)
        self.assertNotIn('href="/logon/%d" class="fw-semibold"' % i, self.a.get('/logons').get_data(as_text=True))   # gone at once
        self.assertNotIn('href="/logon/%d" class="fw-semibold"' % i, self.a.get('/logons/rows?partial=1').get_data(as_text=True))

    def test_units_do_not_see_each_others_records(self):
        i = self.new()
        self.assertEqual(self.b.get('/logon/%d' % i).status_code, 403)
        self.assertEqual(self.b.post('/api/logon/%d' % i, json={'field': 'pob', 'value': '1'}).status_code, 403)
        self.assertNotIn('data-record="%d"' % i, self.b.get('/logons').get_data(as_text=True))
        self.assertEqual(self.a.get('/logon/999').status_code, 404)


if __name__ == '__main__':
    unittest.main()
