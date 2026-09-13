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
        values = dict({'firstName': 'Jane', 'lastName': 'Smith', 'address': '1 Wharf St', 'mobile': '0412345678', 'email': 'jane@example.com'}, **fields)
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
        first, second = self.member(), self.member(firstName='Bob', lastName='Jones', email='bob@example.com')
        cur = self.db()
        self.assertEqual(M.get(cur, 'member', first)['memberNumber'], 'm00001')
        self.assertEqual(M.get(cur, 'member', second)['memberNumber'], 'm00002')
        self.assertEqual(M.get(cur, 'member', first)['mobile'], '0412 345 678')         # written like the log on's mobile
        page = self.a.get('/members').get_data(as_text=True)
        self.assertIn('m00001', page)
        self.assertIn('>Jones</span>', page)
        self.assertIn('First name', page)
        self.assertIn('href="/members/new"', page)
        self.assertNotIn('href="/vessels"', page)                                   # no Public vessels button on Members
        self.assertNotIn('href="/members"', self.a.get('/vessels').get_data(as_text=True))   # nor Members on Public vessels
        self.assertNotIn('Jones', self.a.get('/members?q=jane').get_data(as_text=True))
        self.assertIn('Smith', self.a.get('/members?q=0412345678').get_data(as_text=True))
        logons = self.a.get('/logons').get_data(as_text=True)
        self.assertIn('href="/members"', logons)                                    # reached from the log's navbar
        self.assertIn('href="/vessels"', logons)

    def test_a_refused_member_save_writes_nothing_and_turns_its_boxes_red(self):
        r = self.a.post('/members/new', data={'firstName': 'Jane', 'lastName': '', 'mobile': '04123456789', 'email': 'not-an-email', 'address': 'kept'})
        self.assertEqual(r.status_code, 400)
        page = r.get_data(as_text=True)
        self.assertIn('<label for="member-mobile">Mobile Phone Number</label>', page)    # the log on's label and rule
        for name in ('lastName', 'mobile', 'email'):
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
        self.assertNotIn('Smith', self.b.get('/members').get_data(as_text=True))
        other = self.b.post('/logons/new', json={'fields': {'callDay': date.today().isoformat(), 'callTime': '0900',
                                                            'memberNumber': 'm00001', 'mobile': '0400000002'}})
        self.assertEqual(other.status_code, 200, other.data)
        self.assertEqual(other.json['notMember'], 'm00001')                           # another unit's member is not one here
        self.assertIsNone(L.get(self.db(), other.json['id'])['memberId'])

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

    def test_a_member_number_that_is_not_a_member_is_kept_in_notes_and_it_is_a_public_log_on(self):   # CAP-24
        self.member()
        self.assertEqual(self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'registration': 'PUB01', 'ownerName': 'Alex',
                                                           'ownerPhone': '0411222333'}).status_code, 302)
        check = self.a.post('/logons/new', json={'check': True, 'fields': {'callDay': date.today().isoformat(), 'callTime': '0915',
                                                                           'memberNumber': 'm09999', 'registration': 'PUB01'}})
        self.assertEqual(check.status_code, 200)
        self.assertEqual((check.json['notMember'], check.json['notMemberNote']),
                         ('m09999', 'Member No. heard: m09999 (no such member)'))    # the form empties the box and adds this
        saved = self.logon(memberNumber='m09999', registration='pub01', notes='Two aboard, one child')
        self.assertEqual(saved.status_code, 200, saved.data)                          # nothing refused (ACC-8)
        self.assertEqual(saved.json['notMember'], 'm09999')
        row = L.get(self.db(), saved.json['id'])
        self.assertIsNone(row['memberNumber'])                                        # never stored as a Member No.
        self.assertIsNone(row['memberId'])
        self.assertEqual(row['notes'], 'Two aboard, one child\nMember No. heard: m09999 (no such member)')
        self.assertIsNotNone(row['vesselId'])                                        # tied to the public vessel
        page = self.a.get('/logon/%d' % row['id']).get_data(as_text=True)
        self.assertIn('href="/vessel/%d" data-who="public"' % row['vesselId'], page)
        self.assertIn('Public · Blue Duck', page)
        self.assertIn('<label for="f-notes">Notes</label>', page)
        self.assertIn('Member No. heard: m09999 (no such member)</textarea>', page)
        again = self.a.post('/api/logon/%d' % row['id'], json={'fields': {'memberNumber': 'm09999',
                                                                          'notes': row['notes']}, 'version': row['version']})
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(L.get(self.db(), row['id'])['notes'].count('m09999'), 1)       # said twice, noted once
        one = self.a.post('/api/logon/%d' % row['id'], json={'field': 'memberNumber', 'value': 'm08888'})
        self.assertEqual((one.status_code, one.json['notMember'], one.json['value']), (200, 'm08888', None))
        self.assertIn('Member No. heard: m08888', L.get(self.db(), row['id'])['notes'])
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

    # ---- the log on's Member or public user question, through Quackit's shared search picker ----

    def test_the_log_on_asks_member_or_public_user_through_the_shared_picker(self):
        page = self.a.get('/logons/new').get_data(as_text=True)
        self.assertIn('<label>Member or public user</label>', page)
        self.assertIn('id="roPickMember"', page)
        self.assertIn('id="roPickPublic"', page)
        self.assertIn('id="searchPicker"', page)                                     # Quackit's shared picker, rendered once
        self.assertEqual(page.count('id="searchPicker"'), 1)
        self.assertIn("endpoint: '/api/logons/members'", page)
        self.assertIn('id="roNewVesselPanel" hidden', page)
        self.assertIn('id="roNewPublicPanel" hidden', page)
        self.assertIn('data-ro-json', page)
        self.assertNotIn('placeholder=', page)
        self.assertIn('data-field="vesselId"', page)

    def test_the_picker_endpoints_answer_in_its_shape(self):
        m = self.member()
        self.vessel(m)
        self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'registration': 'PUB01', 'ownerName': 'Alex Public', 'ownerPhone': '0411222333'})
        members = self.a.get('/api/logons/members?q=smith').json['items']
        self.assertEqual([(i['id'], i['primary'], i['memberNumber']) for i in members], [(m, 'm00001 Jane Smith', 'm00001')])
        self.assertEqual(members[0]['secondary'], '0412 345 678 · Sea Dog')
        self.assertEqual(self.a.get('/api/logons/members?q=nobody').json['items'], [])
        boats = self.a.get('/api/logons/vessels?member=%d' % m).json['items']
        self.assertEqual([(b['primary'], b['fields']['registration']) for b in boats], [('Sea Dog', 'AB123Q')])
        self.assertEqual(self.a.get('/api/logons/vessels?member=%d&q=zzz' % m).json['items'], [])
        self.assertEqual(self.a.get('/api/logons/vessels').status_code, 400)
        public = self.a.get('/api/logons/public-vessels?q=alex').json['items']
        self.assertEqual([(p['primary'], p['fields']['ownerPhone']) for p in public], [('Blue Duck', '0411 222 333')])
        self.assertIn('Alex Public', public[0]['secondary'])
        self.assertEqual(self.b.get('/api/logons/vessels?member=%d' % m).status_code, 403)   # another unit's member
        self.assertEqual(self.b.get('/api/logons/members').json['items'], [])

    def test_new_vessels_save_from_the_log_on_page_and_come_back_as_a_pick(self):
        m = self.member()
        json = {'Accept': 'application/json'}
        bad = self.a.post('/member/%d/vessels' % m, data={'length': 'six'}, headers=json)
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(set(bad.json['fields']), {'vesselName', 'registration', 'length'})
        good = self.a.post('/member/%d/vessels' % m, data={'vesselName': 'Sea Dog', 'registration': 'AB123Q'}, headers=json)
        self.assertEqual(good.status_code, 200, good.data)
        self.assertEqual((good.json['item']['id'], good.json['item']['primary']), (good.json['id'], 'Sea Dog'))
        bad = self.a.post('/vessels/new', data={'vesselName': 'Blue Duck'}, headers=json)
        self.assertEqual((bad.status_code, set(bad.json['fields'])), (400, {'ownerName', 'ownerPhone'}))
        good = self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'ownerName': 'Alex', 'ownerPhone': '0411222333'}, headers=json)
        self.assertEqual(good.json['item']['fields']['ownerPhone'], '0411 222 333')

    def test_a_picked_vessel_is_linked_and_must_belong_to_the_answer(self):
        m, other = self.member(), self.member(firstName='Bob', lastName='Jones')
        self.vessel(m, registration='')                                              # a name and no rego: only a pick can link it
        self.vessel(other, vesselName='Other Boat', registration='OTH1')
        cur = self.db()
        own, theirs = M.children(cur, 'vessels', m)[0], M.children(cur, 'vessels', other)[0]
        public = self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'ownerName': 'Alex', 'ownerPhone': '0411222333'},
                             headers={'Accept': 'application/json'}).json['id']
        r = self.logon(memberNumber='m00001', vesselName='Sea Dog', vesselId=str(own['id']))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(L.get(self.db(), r.json['id'])['vesselId'], own['id'])
        for member, vessel in (('m00001', theirs['id']), ('m00001', public), ('', own['id']), ('', 'x')):
            r = self.logon(memberNumber=member, vesselId=str(vessel))
            self.assertEqual(r.status_code, 400, (member, vessel))                   # never linked to the wrong record
        r = self.logon(memberNumber='', vesselName='Blue Duck', vesselId=str(public))
        self.assertEqual(L.get(self.db(), r.json['id'])['vesselId'], public)
        page = self.a.get('/logon/%d' % r.json['id']).get_data(as_text=True)
        self.assertIn('id="f-vesselId" data-field="vesselId" value="%d"' % public, page)
        check = self.a.post('/api/logon/%d' % r.json['id'], json={'check': True, 'fields': {'vesselId': str(theirs['id'])}})
        self.assertEqual(check.status_code, 400)


if __name__ == '__main__':
    unittest.main()
