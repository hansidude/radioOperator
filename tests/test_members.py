"""Members, their contacts, vessels, trailers and cars, public vessels, and a log on tied to them: real routes
and SQL on an isolated database."""
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import logons as L
from server import members as M
from server.sqlite import Connection
from test_pages import test_app


class Members(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'test.db'
        self.app = test_app(self.path)
        self.app.testing = True
        self.a = self.app.test_client()
        self.a.get('/test-login/alice/unitA')
        self.b = self.app.test_client()
        self.b.get('/test-login/bob/unitB')

    def db(self):
        return Connection(self.path).cursor()

    def member(self, **fields):
        values = dict({'name': 'Jane Smith', 'address': '1 Wharf St', 'phone': '0412345678', 'email': 'jane@example.com'}, **fields)
        r = self.a.post('/members/new', data=values)
        self.assertEqual(r.status_code, 302, r.data)
        return int(re.search(r'/member/(\d+)$', r.location).group(1))

    def vessel(self, member_id, **fields):
        values = dict({'vesselName': 'Sea Dog', 'registration': 'AB123Q', 'length': '6'}, **fields)
        self.assertEqual(self.a.post('/member/%d/vessels' % member_id, data=values).status_code, 302)

    def logon(self, **fields):
        values = dict({'callDay': date.today().isoformat(), 'callTime': '0915', 'mobile': '0400000001'}, **fields)
        return self.a.post('/logons/new', json={'fields': values})

    # ---- members ----

    def test_a_member_gets_the_next_member_number(self):
        first, second = self.member(), self.member(name='Bob Jones', email='bob@example.com')
        cur = self.db()
        self.assertEqual(M.get(cur, 'member', first)['memberNumber'], 'm00001')
        self.assertEqual(M.get(cur, 'member', second)['memberNumber'], 'm00002')
        self.assertEqual(M.get(cur, 'member', first)['phone'], '0412 345 678')          # written like the log on's mobile
        page = self.a.get('/members').get_data(as_text=True)
        self.assertIn('m00001', page)
        self.assertIn('Bob Jones', page)
        self.assertIn('href="/members/new"', page)
        self.assertIn('href="/vessels"', page)
        self.assertNotIn('Bob Jones', self.a.get('/members?q=jane').get_data(as_text=True))
        self.assertIn('Jane Smith', self.a.get('/members?q=0412345678').get_data(as_text=True))
        logons = self.a.get('/logons').get_data(as_text=True)
        self.assertIn('href="/members"', logons)                                    # reached from the log's navbar
        self.assertIn('href="/vessels"', logons)

    def test_a_refused_member_save_writes_nothing_and_turns_its_boxes_red(self):
        r = self.a.post('/members/new', data={'name': '', 'phone': '12345', 'email': 'not-an-email', 'address': 'kept'})
        self.assertEqual(r.status_code, 400)
        page = r.get_data(as_text=True)
        for name in ('name', 'phone', 'email'):
            self.assertIn('id="member-%s" name="%s" class="form-control is-invalid"' % (name, name), page)
        self.assertIn('>kept</textarea>', page)                                     # what was typed stays
        self.assertNotIn('placeholder=', page.split('id="ro-member-details"')[1])   # labels on top, nothing inside a box
        self.assertIn('0 members', self.a.get('/members').get_data(as_text=True))

    def test_a_member_page_has_tabs_for_contacts_vessels_trailers_and_cars(self):
        i = self.member()
        page = self.a.get('/member/%d' % i).get_data(as_text=True)
        for tab in ('details', 'contacts', 'vessels', 'trailers', 'cars', 'history'):
            self.assertIn('data-entity-tab="%s"' % tab, page)                        # Quackit's shared tabs
            self.assertIn('id="ro-member-%s"' % tab, page)
        self.assertIn('action="/member/%d/vessels#vessels"' % i, page)               # each form comes back to its tab

    def test_a_member_holds_many_of_each_and_removes_them_without_deleting(self):
        i = self.member()
        for kind, values in (('contacts', {'name': 'Sam Smith', 'relationship': 'Partner', 'phone': '0499888777'}),
                             ('contacts', {'name': 'Pat Smith', 'phone': '0499888666'}),
                             ('vessels', {'vesselName': 'Sea Dog', 'registration': 'AB123Q'}),
                             ('vessels', {'registration': 'CD456R'}),
                             ('trailers', {'registration': 'TR001', 'make': 'Dunbier'}),
                             ('trailers', {'registration': 'TR002'}),
                             ('cars', {'registration': 'CAR01', 'make': 'Toyota', 'model': 'Hilux'}),
                             ('cars', {'registration': 'CAR02'})):
            self.assertEqual(self.a.post('/member/%d/%s' % (i, kind), data=values).status_code, 302, (kind, values))
        cur = self.db()
        for kind in M.CHILDREN:
            self.assertEqual(len(M.children(cur, kind, i)), 2, kind)
        page = self.a.get('/member/%d' % i).get_data(as_text=True)
        for text in ('Sam Smith', 'Pat Smith', 'Sea Dog', 'CD456R', 'Dunbier', 'TR002', 'Hilux', 'CAR02'):
            self.assertIn(text, page)
        self.assertIn('Sea Dog, CD456R', self.a.get('/members').get_data(as_text=True))

        car = M.children(cur, 'cars', i)[0]
        r = self.a.post('/member/%d/cars/%d' % (i, car['id']), data={'registration': 'CAR01', 'make': 'Ford', 'version': car['version']})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.a.post('/member/%d/cars/%d' % (i, car['id']), data={'registration': 'CAR01', 'version': car['version']}).status_code, 409)
        self.assertEqual(self.a.post('/member/%d/cars/%d/remove' % (i, car['id']), data={'version': car['version'] + 1}).status_code, 302)
        cur = self.db()
        self.assertEqual([c['registration'] for c in M.children(cur, 'cars', i)], ['CAR02'])
        cur.execute('SELECT isActive, make FROM Cars WHERE id = %s', (car['id'],))
        self.assertEqual(dict(cur.fetchone()), {'isActive': 0, 'make': 'Ford'})       # kept, inactive

    def test_child_records_refuse_what_they_cannot_be_without(self):
        i = self.member()
        for kind, values, red in (('contacts', {'name': 'Sam'}, ['phone']),
                                  ('vessels', {'length': 'six'}, ['vesselName', 'registration', 'length']),
                                  ('trailers', {'make': 'Dunbier'}, ['registration']),
                                  ('cars', {'colour': 'red'}, ['registration'])):
            r = self.a.post('/member/%d/%s' % (i, kind), data=values)
            self.assertEqual(r.status_code, 400, kind)
            page = r.get_data(as_text=True)
            for name in red:
                self.assertIn('id="%s-new-%s" name="%s" class="form-control is-invalid"' % (kind, name, name), page)
        cur = self.db()
        self.assertEqual([M.children(cur, kind, i) for kind in M.CHILDREN], [[], [], [], []])

    def test_units_do_not_see_each_others_members(self):
        i = self.member()
        self.assertEqual(self.b.get('/member/%d' % i).status_code, 403)
        self.assertEqual(self.b.post('/member/%d/cars' % i, data={'registration': 'X'}).status_code, 403)
        self.assertNotIn('Jane Smith', self.b.get('/members').get_data(as_text=True))
        self.assertEqual(self.b.post('/logons/new', json={'fields': {'callDay': date.today().isoformat(), 'callTime': '0900',
                                                                    'memberNumber': 'm00001'}}).status_code, 400)

    # ---- public vessels ----

    def test_a_public_vessel_is_the_record_for_a_public_user(self):
        r = self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'registration': 'PUB01', 'ownerName': '', 'ownerPhone': ''})
        self.assertEqual(r.status_code, 400)
        for name in ('ownerName', 'ownerPhone'):
            self.assertIn('id="public-%s" name="%s" class="form-control is-invalid"' % (name, name), r.get_data(as_text=True))
        r = self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'registration': 'PUB01', 'ownerName': 'Alex Public',
                                              'ownerPhone': '0411222333', 'hullColour': 'blue'})
        self.assertEqual(r.status_code, 302, r.data)
        v = int(r.location.rsplit('/', 1)[1])
        listed = self.a.get('/vessels').get_data(as_text=True)
        self.assertIn('Blue Duck', listed)
        self.assertIn('Alex Public', listed)
        page = self.a.get('/vessel/%d' % v).get_data(as_text=True)
        self.assertIn('value="0411 222 333"', page)
        self.assertEqual(self.a.post('/vessel/%d' % v, data={'vesselName': 'Blue Duck II', 'ownerName': 'Alex Public',
                                                             'ownerPhone': '0411222333', 'version': '0'}).status_code, 302)
        self.assertIn('Blue Duck II', self.a.get('/vessels').get_data(as_text=True))
        self.assertEqual(self.b.get('/vessel/%d' % v).status_code, 403)
        m = self.member()
        self.vessel(m)
        cur = self.db()
        own = M.children(cur, 'vessels', m)[0]
        self.assertNotIn('Sea Dog', self.a.get('/vessels').get_data(as_text=True))           # a member's vessel is not public
        self.assertTrue(self.a.get('/vessel/%d' % own['id']).location.endswith('/member/%d#vessels' % m))

    # ---- a log on is a member's or a public user's ----

    def test_a_member_number_that_is_a_member_ties_the_log_on_to_that_member(self):
        m = self.member()
        self.vessel(m)
        r = self.logon(memberNumber='M 00001', registration='ab123q')              # formatting is not a different number
        self.assertEqual(r.status_code, 200, r.data)
        row = L.get(self.db(), r.json['id'])
        vessel = M.children(self.db(), 'vessels', m)[0]
        self.assertEqual((row['memberNumber'], row['memberId'], row['vesselId']), ('m00001', m, vessel['id']))
        page = self.a.get('/logon/%d' % row['id']).get_data(as_text=True)
        self.assertIn('href="/member/%d" data-who="member"' % m, page)
        self.assertIn('m00001 Jane Smith', page)
        self.assertIn('<datalist id="roMembers"><option value="m00001">Jane Smith · Sea Dog</option>', page)
        self.assertIn('list="roMembers"', page)
        log = self.a.get('/logons').get_data(as_text=True)
        cell = log[log.index('data-record="%d"' % row['id']):]
        cell = cell[cell.index('data-column="member"'):cell.index('data-column="vesselName"')]
        self.assertIn('aria-label="Member"', cell)
        self.assertIn('m00001', cell)

    def test_a_member_number_that_is_not_a_member_is_left_blank_and_it_is_a_public_log_on(self):
        self.member()
        check = self.a.post('/logons/new', json={'check': True, 'fields': {'callDay': date.today().isoformat(), 'callTime': '0915',
                                                                           'memberNumber': 'm09999', 'registration': 'PUB01'}})
        self.assertEqual(check.status_code, 200)
        self.assertEqual(check.json['notMember'], 'm09999')                           # the form empties the box
        refused = self.logon(memberNumber='m09999', registration='PUB01')
        self.assertEqual(refused.status_code, 400)                                   # never stored as typed
        self.assertEqual(refused.json['fields'], ['memberNumber'])
        self.assertIn('not a member', refused.json['error'])
        self.assertIn('0 records', self.a.get('/logons').get_data(as_text=True))

        self.assertEqual(self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'registration': 'PUB01', 'ownerName': 'Alex',
                                                           'ownerPhone': '0411222333'}).status_code, 302)
        saved = self.logon(memberNumber='', registration='pub01')
        self.assertEqual(saved.status_code, 200, saved.data)
        row = L.get(self.db(), saved.json['id'])
        self.assertIsNone(row['memberId'])
        self.assertIsNotNone(row['vesselId'])                                        # tied to the public vessel
        page = self.a.get('/logon/%d' % row['id']).get_data(as_text=True)
        self.assertIn('href="/vessel/%d" data-who="public"' % row['vesselId'], page)
        self.assertIn('Public · Blue Duck', page)
        self.assertEqual(self.a.post('/api/logon/%d' % row['id'], json={'field': 'memberNumber', 'value': 'm09999'}).status_code, 400)
        log = self.a.get('/logons').get_data(as_text=True)
        cell = log[log.index('data-record="%d"' % row['id']):]
        cell = cell[cell.index('data-column="member"'):cell.index('data-column="vesselName"')]
        self.assertIn('aria-label="Public user"', cell)

    def test_a_rego_names_a_vessel_only_when_it_names_exactly_one(self):
        for owner in ('Alex', 'Chris'):
            self.a.post('/vessels/new', data={'registration': 'SAME1', 'ownerName': owner, 'ownerPhone': '0411222333'})
        r = self.logon(registration='SAME1')
        self.assertIsNone(L.get(self.db(), r.json['id'])['vesselId'])                # two public vessels: not a guess

    def test_a_number_saved_before_members_existed_stays_until_it_is_changed(self):
        r = self.logon(registration='OLD01')
        cur = Connection(self.path)
        c = cur.cursor()
        c.execute("UPDATE LogOns SET memberNumber = 'OLD-77' WHERE id = %s", (r.json['id'],))
        cur.commit()
        i = r.json['id']
        self.assertEqual(self.a.post('/api/logon/%d' % i, json={'fields': {'memberNumber': 'OLD-77', 'pob': '2'}}).status_code, 200)
        self.assertEqual(L.get(self.db(), i)['memberNumber'], 'OLD-77')
        log = self.a.get('/logons').get_data(as_text=True)
        self.assertIn('Public OLD-77', log)


if __name__ == '__main__':
    unittest.main()
