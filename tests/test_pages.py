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
    mount(app, TestHost())

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
        self.assertIn('data-id="%d"' % j, page)                # the other Draft is on the queue while this one is captured
        self.assertIn('data-field="eta"', page)
        self.assertIn('Still to ask', page)
        r = self.a.post('/api/logon/%d' % i, json={'field': 'eta', 'value': '3pm', 'version': 0})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.json['version'], 1)
        self.assertIsNone(r.json['when'])                          # a time with no day is not a deadline
        self.assertIn('No day', r.json['warning'])
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
        self.assertIn('15:00', listing)
        self.assertIn('Sea Dog', self.a.get('/logons/rows?partial=1&current=%d' % i).get_data(as_text=True))

    def test_the_log_off_control_is_not_trapped_inside_the_capture_form(self):
        """A form inside a form is dropped by the browser, which left the Log off button owned by
        the capture form and its submit handler returning false: the button did nothing at all."""
        i = self.new()
        page = self.a.get('/logon/%d' % i).get_data(as_text=True)
        inside = page[page.index('<form id="capture"'):]
        inside = inside[inside.index('>') + 1:]                  # past the opening tag itself
        inside = inside[:inside.index('</form>')]
        self.assertNotIn('<form', inside)                        # nothing nested inside it
        self.assertIn('form="logoffForm"', page)                 # the button is bound to its own form
        self.assertIn('action="/logon/%d/logoff"' % i, page)

    def test_units_do_not_see_each_others_records(self):
        i = self.new()
        self.assertEqual(self.b.get('/logon/%d' % i).status_code, 403)
        self.assertEqual(self.b.post('/api/logon/%d' % i, json={'field': 'pob', 'value': '1'}).status_code, 403)
        self.assertNotIn('data-id="%d"' % i, self.b.get('/logons').get_data(as_text=True))
        self.assertEqual(self.a.get('/logon/999').status_code, 404)

    def test_overdue_shows_on_the_queue_without_operator_action(self):    # AC-21, AC-27
        i = self.new()
        self.a.post('/api/logon/%d' % i, json={'field': 'etaDay', 'value': 'today'})
        r = self.a.post('/api/logon/%d' % i, json={'field': 'eta', 'value': '0001'})    # long past: overdue at once (§3.3)
        self.assertEqual(r.status_code, 200)
        self.assertIn('Already past', r.json['warning'])
        self.assertIn('OVERDUE', self.a.get('/logons').get_data(as_text=True))
        self.assertEqual(self.a.get('/api/logons/queue').json['logons'][0]['condition'], 'overdue')

    def test_accept_complete_and_log_off_are_explicit_actions(self):      # AC-36 (log off part), §3.3
        i = self.new()
        self.assertEqual(self.a.post('/logon/%d/accept' % i, data={'back': '/logon/%d' % i}).status_code, 302)
        self.assertEqual(self.a.post('/logon/%d/accept' % i).status_code, 400)
        self.assertEqual(self.a.post('/logon/%d/capture' % i, data={'complete': '1'}).status_code, 302)
        page = self.a.get('/logon/%d' % i).get_data(as_text=True)
        self.assertIn('Watching', page); self.assertIn('Reopen capture', page)
        self.assertEqual(self.a.post('/logon/%d/logoff' % i, data={'note': 'alongside', 'back': '/logons'}).status_code, 302)
        page = self.a.get('/logon/%d' % i).get_data(as_text=True)
        self.assertIn('Logged off', page); self.assertIn('alongside', page); self.assertIn('disabled', page)
        self.assertEqual(self.a.post('/api/logon/%d' % i, json={'field': 'pob', 'value': '1'}).status_code, 400)
        self.assertIn('Recently logged off', self.a.get('/logons').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
