"""Real Flask routes and SQL on an isolated database with a test host; never uses a host's data."""
import sys
import tempfile
from datetime import date
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask, g, session
from server.host import Host
from server.routes import mount
from server.sqlite import Connection, create_schema


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
        self.app.testing = True
        self.a = self.app.test_client()
        self.a.get('/test-login/alice/unitA')
        self.b = self.app.test_client()
        self.b.get('/test-login/bob/unitB')

    def new(self, client=None):
        r = (client or self.a).post('/logons/new')
        self.assertEqual(r.status_code, 302)
        return int(r.location.rsplit('/', 1)[-1])

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

    def accepted(self, **kw):
        i = self.mandatory(self.new(), **kw)
        self.assertEqual(self.a.post('/logon/%d/accept' % i).status_code, 302)
        return i

    def test_not_logged_in_goes_to_the_hosts_login(self):
        c = self.app.test_client()
        r = c.get('/logons')
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.location.endswith('/login'))
        self.assertEqual(c.post('/api/logon/1', json={}).status_code, 302)

    def test_capture_page_shows_the_queue_and_saves_field_by_field(self):    # AC-1, AC-5, AC-6, CAP-7, CAP-19
        i = self.new()
        j = self.new()
        page = self.a.get('/logon/%d' % i).get_data(as_text=True)
        self.assertIn('id="queuePane"', page)
        self.assertIn('data-draft="%d"' % j, page)             # the other draft is visible while this one is captured
        self.assertIn('data-field="eta"', page)
        self.assertIn('type="date" class="ro-native-picker" data-picker-target="callDay"', page)
        self.assertIn('type="time" class="ro-native-picker" data-picker-target="callTime"', page)
        self.assertIn('Still to ask', page)
        self.assertIn('This is a draft, not a log on', page)
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
        self.assertIn('data-ro-count="drafts">2</span>', listing)
        self.assertIn('Sea Dog', self.a.get('/logons/rows?partial=1&current=%d' % i).get_data(as_text=True))

    def test_capture_page_leads_with_the_five_operator_rows(self):
        page = self.a.get('/logon/%d' % self.new()).get_data(as_text=True)
        entry = page[page.index('id="ro-entry-pane"'):page.index('id="ro-contact-pane"')]
        self.assertIn('data-ro-tab="entry"', page)
        for tab in ('contact', 'vessel', 'identity', 'watch', 'record'):
            self.assertIn('data-ro-tab="%s"' % tab, page)
            self.assertIn('id="ro-%s-pane" class="ro-workspace-pane d-none"' % tab, page)
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
        self.assertNotIn('id="queuePane"', entry)
        self.assertIn('id="queuePane"', page)
        self.assertIn('font-size:1.2rem', page)
        self.assertNotIn('<table', page)
        self.assertNotIn('placeholder=', entry)
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

    def test_queue_uses_tabs_and_cards_not_tables(self):
        draft = self.new()
        watching = self.accepted(rego='CD456Q', member='7788')
        page = self.a.get('/logons').get_data(as_text=True)
        for tab in ('overview', 'loggedon', 'overdue', 'drafts', 'closed', 'find'):
            self.assertIn('data-ro-tab="%s"' % tab, page)
        self.assertIn('id="ro-overview-pane" class="ro-workspace-pane"', page)
        self.assertIn('id="ro-loggedon-pane" class="ro-workspace-pane d-none"', page)
        self.assertIn('data-id="%d"' % watching, page)
        self.assertIn('data-draft="%d"' % draft, page)
        self.assertIn('class="ro-record-card', page)
        self.assertIn('class="ro-status-counts"', page)
        self.assertIn('data-ro-count="loggedon">1</span><span class="label">Logged on</span>', page)
        self.assertNotIn('<table', page)

    def test_empty_tabs_confirm_zero_without_false_alarm_colour(self):
        page = self.a.get('/logons').get_data(as_text=True)
        self.assertIn('>0 logged on</div>', page)
        self.assertIn('>0 overdue</div>', page)
        self.assertIn('>0 drafts</div>', page)
        self.assertIn('data-ro-tab="overdue"', page)
        self.assertNotIn('btn-outline-danger', page)
        self.assertNotIn('class="ro-status-count overdue"', page)

    def test_a_draft_is_not_watched_and_says_what_it_needs(self):        # AC-27, AC-50, ACC-1, ACC-2
        i = self.new()
        for name, value in (('etaDay', 'today'), ('eta', '0001'), ('pob', '3'), ('destination', 'Facing Island')):
            self.field(i, name, value)
        r = self.a.post('/logon/%d/accept' % i)                           # short of the mandatory set
        self.assertEqual(r.status_code, 400)
        body = r.get_data(as_text=True)
        self.assertIn('Still needed', body)
        self.assertIn('Member No.', body)
        page = self.a.get('/logon/%d' % i).get_data(as_text=True)
        self.assertIn('DRAFT', page)
        self.assertNotIn('NOT WATCHED', page)
        self.assertNotIn('ro-record-card overdue', page)                  # the return time passed hours ago
        listing = self.a.get('/logons').get_data(as_text=True)
        self.assertNotIn('ro-record-card overdue', listing)
        self.assertNotIn('not watched', listing.lower())
        self.assertEqual(self.a.get('/api/logons/queue').json['watching'], [])
        self.assertEqual(len(self.a.get('/api/logons/queue').json['drafts']), 1)

    def test_accepting_takes_the_watch_and_starts_it_at_once(self):       # AC-51, AC-52, ACC-3, ACC-4
        i = self.mandatory(self.new(), time='0001')                       # a return time already long past
        self.assertEqual(self.a.post('/logon/%d/accept' % i).status_code, 302)
        page = self.a.get('/logon/%d' % i).get_data(as_text=True)
        self.assertIn('Logged on and watched', page)
        self.assertIn('OVERDUE', page)                                    # overdue from the moment of acceptance
        listing = self.a.get('/logons').get_data(as_text=True)
        self.assertIn('OVERDUE', listing)
        self.assertIn('class="ro-status-count overdue"', listing)
        self.assertEqual(self.a.get('/api/logons/queue').json['watching'][0]['condition'], 'overdue')
        self.assertEqual(self.a.post('/logon/%d/accept' % i).status_code, 400)

    def test_one_vessel_one_log_on(self):                                 # AC-53, ACC-6
        first = self.accepted()
        second = self.mandatory(self.new())
        r = self.a.post('/logon/%d/accept' % second)
        self.assertEqual(r.status_code, 400)
        self.assertIn('already logged on', r.get_data(as_text=True))
        page = self.a.get('/logon/%d' % second).get_data(as_text=True)
        self.assertIn('One vessel has one log on', page)
        self.assertIn('AB123Q', page)                                     # nothing captured was discarded
        self.assertEqual(self.a.post('/logon/%d/logoff' % first, data={'note': 'back'}).status_code, 302)
        self.assertEqual(self.a.post('/logon/%d/accept' % second).status_code, 302)

    def test_a_draft_is_discarded_and_a_log_on_is_logged_off(self):       # AC-54, ACC-7
        d = self.new()
        self.assertEqual(self.a.post('/logon/%d/discard' % d, data={'reason': ''}).status_code, 400)
        self.assertEqual(self.a.post('/logon/%d/discard' % d,
                                     data={'reason': 'hit New by mistake', 'back': '/logons'}).status_code, 302)
        page = self.a.get('/logon/%d' % d).get_data(as_text=True)
        self.assertIn('This was never a log on', page)
        self.assertIn('hit New by mistake', page)
        self.assertIn('Discarded', self.a.get('/logons').get_data(as_text=True))
        self.assertEqual(self.a.post('/api/logon/%d' % d, json={'field': 'pob', 'value': '1'}).status_code, 400)
        i = self.accepted(rego='CD456R', member='9001')
        r = self.a.post('/logon/%d/discard' % i, data={'reason': 'tidying'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('logged off, not discarded', r.get_data(as_text=True))

    def test_numbering_counts_from_one_each_day(self):                    # AC-56, REC-9
        first, second = self.new(), self.new()
        page = self.a.get('/logon/%d' % second).get_data(as_text=True)
        self.assertIn('Draft 2', page)
        self.assertIn('draft 2 of', page)
        self.assertIn('>Draft 1</a>', self.a.get('/logons').get_data(as_text=True))

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
        self.assertIn('Mobile Phone Number', r.json['filled'])
        page = self.a.get('/logon/%d' % second).get_data(as_text=True)
        form = page[page.index('<form id="capture"'):page.index('</form>')]
        self.assertIn('0412 345 678', form)
        self.assertNotIn('Facing Island', form)                                   # a past trip is not this trip
        self.assertIn('does not corroborate', page)                               # IDV-1, said plainly
        self.assertIn('Unverified', page)                                         # applied values prove nothing
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
        page = self.a.get('/logon/%d' % mixed).get_data(as_text=True)
        self.assertIn('CONFLICT', page)
        self.assertIn('different boats or people', page)
        self.assertIn('CONFLICT', self.a.get('/logons').get_data(as_text=True))   # and on the queue
        for name, value in (('pob', '2'), ('departurePoint', 'Marina'), ('destination', 'Bay'),
                            ('etaDay', 'today'), ('eta', '2300')):
            self.field(mixed, name, value)
        self.assertEqual(self.a.post('/logon/%d/accept' % mixed).status_code, 302)     # IDV-5: a conflict blocks nothing
        self.assertIn('CONFLICT', self.a.get('/logons').get_data(as_text=True))




    def test_a_closure_made_in_error_is_corrected_not_erased(self):       # §3.3 Correct mistaken closure
        i = self.accepted(time='0001')                                                # a return time long past
        self.assertEqual(self.a.post('/logon/%d/logoff' % i, data={'note': 'thought it was back'}).status_code, 302)
        self.assertEqual(self.a.post('/logon/%d/reopen' % i, data={'reason': ''}).status_code, 400)
        self.assertEqual(self.a.post('/logon/%d/reopen' % i, data={'reason': 'wrong boat'}).status_code, 302)
        page = self.a.get('/logon/%d' % i).get_data(as_text=True)
        self.assertIn('wrong boat', page)
        self.assertIn('thought it was back', page)                                    # the closure event is kept
        self.assertIn('data-id="%d"' % i, self.a.get('/logons').get_data(as_text=True))
        self.assertIn('OVERDUE', self.a.get('/logons').get_data(as_text=True))         # time did not stop
        self.assertEqual(self.a.post('/logon/%d/reopen' % i, data={'reason': 'again'}).status_code, 400)
        self.assertEqual(self.a.post('/api/logon/%d' % i, json={'field': 'pob', 'value': '2'}).status_code, 200)
        self.assertEqual(self.a.post('/logon/%d/logoff' % i,
                                     data={'reason': 'notdeparted', 'note': 'never sailed'}).status_code, 302)

    def test_units_do_not_see_each_others_records(self):
        i = self.new()
        self.assertEqual(self.b.get('/logon/%d' % i).status_code, 403)
        self.assertEqual(self.b.post('/api/logon/%d' % i, json={'field': 'pob', 'value': '1'}).status_code, 403)
        self.assertNotIn('data-id="%d"' % i, self.b.get('/logons').get_data(as_text=True))
        self.assertEqual(self.a.get('/logon/999').status_code, 404)


if __name__ == '__main__':
    unittest.main()
