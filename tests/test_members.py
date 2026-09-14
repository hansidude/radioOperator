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
        self.assertIsNone(M.get(cur, 'member', first)['notes'])
        noted = self.a.post('/member/%d' % first, data={'firstName': 'Jane', 'lastName': 'Smith', 'mobile': '0412345678', 'email': 'jane@example.com', 'notes': 'Prefers channel 16\nHas a PLB',
                                                         'version': '0'})
        self.assertEqual(noted.status_code, 302, noted.data)
        page = self.a.get('/member/%d' % first).get_data(as_text=True)
        self.assertIn('<label for="member-notes"><span class="ro-field-symbol" aria-hidden="true">🗒️</span> Notes</label>', page)
        self.assertIn('>Prefers channel 16\nHas a PLB</textarea>', page)
        page = self.a.get('/members').get_data(as_text=True)
        self.assertIn('m00001', page)
        self.assertIn('>Jones</span>', page)
        self.assertIn('First name', page)
        self.assertIn('href="/members/new"', page)
        nav = lambda html: html[html.index('<div class="entity-nav"'):html.index('</nav>', html.index('<div class="entity-nav"'))]
        self.assertNotIn('href="/vessels"', nav(page))                              # Public vessels is on the menu, not the page
        self.assertNotIn('href="/members"', nav(self.a.get('/vessels').get_data(as_text=True)))   # nor Members
        self.assertNotIn('Jones', self.a.get('/members?q=jane').get_data(as_text=True))
        self.assertIn('Smith', self.a.get('/members?q=0412345678').get_data(as_text=True))
        logons = self.a.get('/logons').get_data(as_text=True)
        self.assertIn('href="/members"', logons)                                    # reached from the log's navbar
        self.assertIn('href="/vessels"', logons)

    def test_a_refused_member_save_writes_nothing_and_turns_its_boxes_red(self):
        r = self.a.post('/members/new', data={'firstName': 'Jane', 'lastName': '', 'mobile': '04123456789', 'email': 'not-an-email', 'address': 'kept'})
        self.assertEqual(r.status_code, 400)
        page = r.get_data(as_text=True)
        self.assertIn('<label for="member-mobile"><span class="ro-field-symbol" aria-hidden="true">📱</span> Mobile Phone Number</label>', page)    # the log on's label and rule
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
        self.assertIn('href="/member/%d/vessels/new"' % i, page)                    # Add opens its own page
        self.assertNotIn('<form id="vessels-new"', page)                            # no stack of forms on the tab
        self.assertIn('id="radioMemberVessels" class="dc-record-view dc-record-grid"', page)   # Quackit's shared grid
        self.assertIn('aria-controls="radioMemberVesselsView"', page)               # its view buttons
        self.assertIn('id="mf-member-%d-vessels-i1"' % i, page)                     # and its row search
        self.assertIn('>0 vessels</div>', page)
        new = self.a.get('/member/%d/vessels/new' % i).get_data(as_text=True)
        self.assertIn('<form id="vessels-new" method="post" action="/member/%d/vessels"' % i, new)
        self.assertNotIn('placeholder=', new)
        for form in ('/members/new', '/member/%d' % i, '/vessels/new', '/member/%d/vessels/new' % i):
            self.assertIn('<div class="container-fluid mySpacing">', self.a.get(form).get_data(as_text=True))   # usual page width

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

        self.assertIn('href="/member/%d/cars/%d"' % (i, M.children(cur, 'cars', i)[0]['id']), page)   # each row opens its page
        car = M.children(cur, 'cars', i)[0]
        self.assertIn('value="Hilux"', self.a.get('/member/%d/cars/%d' % (i, car['id'])).get_data(as_text=True))
        r = self.a.post('/member/%d/cars/%d' % (i, car['id']), data={'registration': 'CAR01', 'make': 'Ford', 'version': car['version']})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.location.endswith('/member/%d#cars' % i))                  # back to the tab it came from
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
        self.assertIn('<span title="Contact"><span class="dc-record-word">Contact</span></span><span title="Phone">', listed)   # not Owner (issue F)
        self.assertNotIn('Owner', listed)
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
        self.assertIn('<span class="ro-who-badge" data-who="member">', page)            # badges with their symbols
        self.assertIn('<span class="dc-record-badge-value">m00001 Jane Smith</span>', page)
        self.assertIn('<span class="dc-record-badge-value">Sea Dog · AB123Q</span>', page)
        self.assertIn('data-ro-clear="member"', page)
        self.assertIn('data-ro-clear="vessel"', page)                                  # a wrong vessel goes on its own
        self.assertRegex(page, r'id="f-memberNumber"[^>]* readonly')                  # set only by picking
        self.assertRegex(page, r'id="f-registration"[^>]* readonly')                  # the record's, while picked
        self.assertNotRegex(page, r'id="f-mobile"[^>]* readonly')                     # the caller's number stays typeable
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
        self.assertIn('<span class="ro-who-badge" data-who="public">', page)
        self.assertIn('<span class="dc-record-badge-value">Blue Duck · PUB01</span>', page)
        self.assertIn('<label for="f-notes"><span class="ro-field-symbol" aria-hidden="true">🗒️</span> Notes</label>', page)
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
        answer = self.a.get('/api/logons/members?q=smith').json
        members = answer['items']
        self.assertEqual([(i['id'], i['primary'], i['memberNumber']) for i in members], [(m, 'm00001 Jane Smith', 'm00001')])
        html = answer['html']                                                          # the Members page's list, under a count
        self.assertIn('<div class="dc-record-found small text-muted mb-1" data-sp-count>1 found</div>', html)
        self.assertIn('data-record="%d"' % m, html)
        self.assertIn('<span class="dc-record-grid-value-symbol" aria-hidden="true">📱</span>', html)   # emoji, field in the cells
        self.assertIn('<span class="dc-record-grid-value-symbol" aria-hidden="true">🛥️</span>', html)
        self.assertNotIn('<span class="dc-record-grid-value-symbol" aria-hidden="true">👤</span>', html)   # the 👤 badge is its own
        self.assertNotIn('href="/member/%d"' % m, html)                                   # no open button: a click picks
        self.assertEqual(self.a.get('/api/logons/members?q=nobody').json['items'], [])
        boats = self.a.get('/api/logons/vessels?member=%d' % m).json['items']
        self.assertEqual([(b['primary'], b['fields']['registration']) for b in boats], [('Sea Dog', 'AB123Q')])
        self.assertEqual(self.a.get('/api/logons/vessels?member=%d&q=zzz' % m).json['items'], [])
        self.assertEqual(self.a.get('/api/logons/vessels').status_code, 400)
        public = self.a.get('/api/logons/public-vessels?q=alex').json['items']
        self.assertEqual([(p['primary'], p['fields']['ownerPhone']) for p in public], [('Blue Duck', '0411 222 333')])
        self.assertIn('Alex Public', self.a.get('/api/logons/public-vessels?q=alex').json['html'])
        self.assertIn('AB123Q', self.a.get('/api/logons/vessels?member=%d' % m).json['html'])
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

    # ---- the log on page's Member / Public vessel tab ----

    def test_a_picked_member_or_public_vessel_gets_its_own_tab_on_the_log_on_page(self):
        new = self.a.get('/logons/new').get_data(as_text=True)
        self.assertIn('id="roWhoTab" hidden', new)                                  # nothing picked: no tab
        self.assertNotIn('data-ro-clear=', new)                                       # and nothing to remove
        self.assertNotRegex(new, r'id="f-registration"[^>]* readonly')                # nothing picked: typed freely
        self.assertIn('<option value="person" >In person</option>', new)              # how they logged on
        self.assertIn('<div id="roWhoPanel" data-navbar-local></div>', new)
        m = self.member()
        self.vessel(m)
        r = self.logon(memberNumber='m00001', registration='AB123Q')
        page = self.a.get('/logon/%d' % r.json['id']).get_data(as_text=True)
        self.assertIn('id="roWhoTab"><span data-ro-who-label>👤 Member</span>', page)
        self.assertIn('data-ro-clear="member"', page)                                 # shown: something to remove
        self.assertIn('hx-get="/member/%d/panel" hx-trigger="load" hx-swap="innerHTML"' % m, page)
        panel = self.a.get('/member/%d/panel' % m).get_data(as_text=True)
        self.assertNotIn('<html', panel)                                            # content only, for swapping in
        for tab in ('details', 'contacts', 'vessels', 'trailers', 'cars', 'history'):
            self.assertIn('data-entity-tab="%s"' % tab, panel)                     # the member page's own tabs and panes
            self.assertIn('id="ro-member-%s"' % tab, panel)
        self.assertIn('id="radioMemberVessels"', panel)
        self.assertIn('Sea Dog', panel)
        self.assertIn('href="/member/%d/vessels/new"' % m, panel)
        self.assertEqual(self.b.get('/member/%d/panel' % m).status_code, 403)
        pub = self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'registration': 'PUB01', 'ownerName': 'Alex Public',
                                               'ownerPhone': '0411222333'}, headers={'Accept': 'application/json'}).json['id']
        r = self.logon(registration='PUB01')
        page = self.a.get('/logon/%d' % r.json['id']).get_data(as_text=True)
        self.assertIn('<span data-ro-who-label>🌐 Public vessel</span>', page)
        self.assertIn('hx-get="/vessel/%d/panel"' % pub, page)
        vpanel = self.a.get('/vessel/%d/panel' % pub).get_data(as_text=True)
        self.assertIn('value="Alex Public"', vpanel)
        self.assertIn('data-entity-tab="history"', vpanel)
        own = M.children(self.db(), 'vessels', m)[0]
        self.assertEqual(self.a.get('/vessel/%d/panel' % own['id']).status_code, 404)   # a member's vessel is on the member

    def test_removing_the_pick_and_saving_leaves_no_member_and_no_vessel(self):
        m = self.member()
        self.vessel(m)
        vessel = M.children(self.db(), 'vessels', m)[0]
        r = self.logon(memberNumber='m00001', vesselName='Sea Dog', registration='AB123Q', vesselId=str(vessel['id']))
        row = L.get(self.db(), r.json['id'])
        self.assertEqual((row['memberId'], row['vesselId']), (m, vessel['id']))
        removed = {'memberNumber': '', 'vesselName': '', 'registration': '', 'vesselId': '', 'mobile': '0400000001'}
        saved = self.a.post('/api/logon/%d' % row['id'], json={'fields': removed, 'version': row['version']})
        self.assertEqual(saved.status_code, 200, saved.data)
        row = L.get(self.db(), row['id'])
        self.assertEqual((row['memberNumber'], row['memberId'], row['vesselId'], row['registration']), (None, None, None, None))
        page = self.a.get('/logon/%d' % row['id']).get_data(as_text=True)
        self.assertIn('id="roWhoTab" hidden', page)

    def test_what_a_pick_fills_comes_from_the_records(self):
        m = self.member()
        self.vessel(m, hullColour='blue', make='Quintrex')
        vessel = M.children(self.db(), 'vessels', m)[0]
        # a picked vessel: its details are the record's, whatever the form sent
        r = self.logon(memberNumber='m00001', vesselName='Typo Dog', registration='XX1', hullColour='red', vesselId=str(vessel['id']))
        self.assertEqual(r.status_code, 200, r.data)
        row = L.get(self.db(), r.json['id'])
        self.assertEqual((row['vesselName'], row['registration'], row['hullColour'], row['make']), ('Sea Dog', 'AB123Q', 'blue', 'Quintrex'))
        # a member picked with no vessel has none: vessel details typed anyway are refused, the boxes named
        r = self.logon(memberNumber='m00001', vesselName='Typed Boat', registration='TY1', vesselId='')
        self.assertEqual(r.status_code, 400)
        self.assertEqual(set(r.json['fields']), {'vesselName', 'registration'})
        self.assertIn("pick one of their vessels", r.json['error'])
        r = self.logon(memberNumber='m00001', vesselId='')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIsNone(L.get(self.db(), r.json['id'])['vesselName'])
        # nothing picked: typed as heard
        r = self.logon(vesselName='Heard Boat', registration='HB1', vesselId='')
        self.assertEqual(L.get(self.db(), r.json['id'])['vesselName'], 'Heard Boat')
        # the orange "worth asking for" does not ask for a picked member's vessel name
        check = self.a.post('/logons/new', json={'check': True, 'fields': {'callDay': date.today().isoformat(), 'callTime': '0915',
                                                                           'memberNumber': 'm00001', 'mobile': '0400000001', 'vesselId': ''}})
        self.assertEqual(check.json['orange'], [])

    def test_the_badges_and_the_member_vessel_picker_answer_for_the_log_on_page(self):
        m = self.member()
        self.vessel(m)
        vessel = M.children(self.db(), 'vessels', m)[0]
        both = self.a.get('/logons/who?member=%d&vessel=%d' % (m, vessel['id'])).get_data(as_text=True)
        self.assertIn('data-who="member"', both)
        self.assertIn('data-ro-clear="vessel"', both)
        alone = self.a.get('/logons/who?member=%d' % m).get_data(as_text=True)
        self.assertIn('data-ro-pick-vessel', alone)                                   # no vessel: a button to pick one
        pub = self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'ownerName': 'Alex', 'ownerPhone': '0411222333'},
                          headers={'Accept': 'application/json'}).json['id']
        self.assertEqual(self.a.get('/logons/who?member=%d&vessel=%d' % (m, pub)).status_code, 400)   # not this member's
        self.assertIn('data-who="public"', self.a.get('/logons/who?vessel=%d' % pub).get_data(as_text=True))
        self.assertEqual([i['primary'] for i in self.a.get('/api/logons/members/%d/vessels' % m).json['items']], ['Sea Dog'])

    def test_the_member_tab_saves_in_place(self):
        m = self.member()
        self.vessel(m)
        vessel = M.children(self.db(), 'vessels', m)[0]
        json = {'Accept': 'application/json'}
        panel = self.a.get('/member/%d/panel' % m).get_data(as_text=True)
        self.assertIn('<form id="member" method="post" action="/member/%d#details" class="ro-record-form" autocomplete="off" novalidate data-ro-json>' % m, panel)
        self.assertIn('hx-get="/member/%d/vessels/new?panel=1" hx-target="#roWhoPanel"' % m, panel)
        self.assertIn('hx-get="/member/%d/vessels/%d?panel=1" hx-target="#roWhoPanel"' % (m, vessel['id']), panel)
        form = self.a.get('/member/%d/vessels/%d?panel=1' % (m, vessel['id'])).get_data(as_text=True)
        self.assertNotIn('<html', form)
        self.assertIn('data-ro-json data-ro-remove', form)
        saved = self.a.post('/member/%d' % m, data={'firstName': 'Janet', 'lastName': 'Smith', 'mobile': '0412345678', 'version': '0'}, headers=json)
        self.assertEqual((saved.status_code, saved.json['member']['primary']), (200, 'm00001 Janet Smith'))
        bad = self.a.post('/member/%d' % m, data={'firstName': '', 'lastName': 'Smith', 'version': '1'}, headers=json)
        self.assertEqual((bad.status_code, bad.json['fields']), (400, ['firstName']))
        stale = self.a.post('/member/%d' % m, data={'firstName': 'J', 'lastName': 'S', 'version': '0'}, headers=json)
        self.assertEqual(stale.status_code, 409)
        boat = self.a.post('/member/%d/vessels/%d' % (m, vessel['id']), data={'vesselName': 'Sea Dog II', 'registration': 'AB123Q', 'version': '0'}, headers=json)
        self.assertEqual(boat.json['item']['primary'], 'Sea Dog II')
        car = self.a.post('/member/%d/cars' % m, data={'registration': 'CAR1'}, headers=json)
        self.assertEqual((car.status_code, car.json['kind']), (200, 'cars'))
        gone = self.a.post('/member/%d/vessels/%d/remove' % (m, vessel['id']), data={'version': '1'}, headers=json)
        self.assertEqual((gone.json['removed'], gone.json['id']), (True, vessel['id']))
        pub = self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'ownerName': 'Alex', 'ownerPhone': '0411222333'}, headers=json).json['id']
        vpanel = self.a.get('/vessel/%d/panel' % pub).get_data(as_text=True)
        self.assertIn('data-ro-json', vpanel)
        again = self.a.post('/vessel/%d' % pub, data={'vesselName': 'Blue Duck', 'hullColour': 'blue', 'ownerName': 'Alex', 'ownerPhone': '0411222333',
                                                     'version': '0'}, headers=json)
        self.assertEqual(again.json['item']['fields']['hullColour'], 'blue')
        page = self.a.get('/member/%d' % m).get_data(as_text=True)                   # the member page itself stays plain forms
        self.assertNotIn('data-ro-json', page)

    def test_a_public_vessel_has_emergency_contacts_and_notes(self):
        r = self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'ownerName': 'Alex', 'ownerPhone': '0411222333',
                                              'notes': 'Keeps a spare radio\nUsually two aboard'})
        self.assertEqual(r.status_code, 302, r.data)
        v = int(r.location.rsplit('/', 1)[1])
        page = self.a.get('/vessel/%d' % v).get_data(as_text=True)
        self.assertIn('>Keeps a spare radio\nUsually two aboard</textarea>', page)        # notes, a text box that grows
        self.assertIn('<label for="public-notes"><span class="ro-field-symbol" aria-hidden="true">🗒️</span> Notes</label>', page)
        for tab in ('details', 'contacts', 'history'):
            self.assertIn('data-entity-tab="%s"' % tab, page)
        self.assertIn('id="radioVesselContacts" class="dc-record-view dc-record-grid"', page)   # the same list as a member's
        self.assertIn('href="/vessel/%d/contacts/new"' % v, page)
        bad = self.a.post('/vessel/%d/contacts' % v, data={'name': 'Sam'})
        self.assertEqual(bad.status_code, 400)
        self.assertIn('id="contacts-new-phone" name="phone" class="form-control is-invalid"', bad.get_data(as_text=True))
        added = self.a.post('/vessel/%d/contacts' % v, data={'name': 'Sam Duck', 'relationship': 'Brother', 'phone': '0499888777'})
        self.assertTrue(added.location.endswith('/vessel/%d#contacts' % v))
        contact = M.children(self.db(), 'contacts', v, 'vessel')[0]
        self.assertEqual((contact['vesselId'], contact['memberId'], contact['phone']), (v, None, '0499 888 777'))
        self.assertIn('Sam Duck', self.a.get('/vessel/%d' % v).get_data(as_text=True))
        self.assertIn('value="Brother"', self.a.get('/vessel/%d/contacts/%d' % (v, contact['id'])).get_data(as_text=True))
        json = {'Accept': 'application/json'}
        saved = self.a.post('/vessel/%d/contacts/%d' % (v, contact['id']), data={'name': 'Sam Duck', 'phone': '0499888666', 'version': '0'}, headers=json)
        self.assertEqual((saved.status_code, saved.json['kind']), (200, 'contacts'))
        panel = self.a.get('/vessel/%d/panel' % v).get_data(as_text=True)
        self.assertIn('hx-get="/vessel/%d/contacts/%d?panel=1" hx-target="#roWhoPanel"' % (v, contact['id']), panel)
        form = self.a.get('/vessel/%d/contacts/new?panel=1' % v).get_data(as_text=True)
        self.assertIn('hx-get="/vessel/%d/panel"' % v, form)                          # back to the vessel, in the tab
        self.assertIn('data-ro-json', form)
        self.assertEqual(self.a.post('/vessel/%d/contacts/%d/remove' % (v, contact['id']), data={'version': '1'}).status_code, 302)
        self.assertEqual(M.children(self.db(), 'contacts', v, 'vessel'), [])
        self.assertEqual(self.a.get('/vessel/%d/cars/new' % v).status_code, 404)     # a public vessel holds contacts only
        m = self.member()
        self.assertEqual(self.a.get('/member/%d/contacts/%d' % (m, contact['id'])).status_code, 404)   # not this member's
        self.assertEqual(self.b.get('/vessel/%d/contacts/new' % v).status_code, 403)

    def test_one_search_finds_every_kind_of_radio_record(self):
        m = self.member(notes='Keeps a spare EPIRB')
        self.vessel(m, vesselName='Sea Dog', registration='AB123Q')
        self.a.post('/member/%d/contacts' % m, data={'name': 'Sam Smith', 'relationship': 'Partner', 'phone': '0499888777'})
        self.a.post('/member/%d/trailers' % m, data={'registration': 'TRL77', 'make': 'Dunbier'})
        self.a.post('/member/%d/cars' % m, data={'registration': 'CAR77', 'make': 'Toyota'})
        pub = self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'registration': 'PUB77', 'ownerName': 'Alex Public',
                                                'ownerPhone': '0411222333', 'notes': 'Yellow kayak rack'},
                          headers={'Accept': 'application/json'}).json['id']
        self.a.post('/vessel/%d/contacts' % pub, data={'name': 'Pat Public', 'phone': '0433444555'})
        self.logon(registration='AB123Q', destination='Tangalooma', notes='Called from the ramp')
        page = self.a.get('/radio/search').get_data(as_text=True)
        self.assertIn('Type two or more characters', page)
        self.assertIn('data-grp-toggle-all="radioSearch" data-grp-noun="kinds"', page)                 # collapse / expand all
        self.assertIn('<div class="container-fluid mySpacing">', page)                                  # Quackit's usual page width
        self.assertIn('href="/radio/search"', self.a.get('/logons').get_data(as_text=True))          # on the RadioLogs navbar
        found = lambda q: self.a.get('/radio/search?q=' + q).get_data(as_text=True)
        self.assertIn('data-found="members"', found('EPIRB'))                                        # notes are searched
        self.assertIn('data-found="vessels"', found('kayak'))
        self.assertIn('data-found="logons"', found('ramp'))
        everything = found('77')
        for kind in ('trailers', 'cars', 'vessels'):
            self.assertIn('data-found="%s"' % kind, everything)
        self.assertIn('data-gid="cars" data-found="cars"', everything)   # each kind collapses
        self.assertIn('GroupEngine.init({ key: \'radioSearch\', root: \'#roFoundView\'', page)                  # outside the swapped results
        self.assertIn('href="/member/%d/trailers/' % m, everything)                                  # each row opens its record
        contacts = found('0499888777')                                                               # phone without spaces
        self.assertIn('href="/member/%d/contacts/' % m, contacts)
        self.assertIn('m00001 Jane Smith', contacts)                                                 # held by
        self.assertIn('href="/vessel/%d/contacts/' % pub, found('Pat Public'))
        self.assertIn('data-found="logons"', found('Tangalooma'))
        self.assertIn('0 records match', found('zzzz-nothing'))
        self.assertIn('0 records match', self.b.get('/radio/search?q=Jane').get_data(as_text=True))                    # own unit only
        panel = lambda html: html[html.index('<div id="roMatched">'):html.index('<div id="roFound">')]
        self.assertIn('data-dc-record-panel aria-controls="roFoundPanel"', page)                          # the panel button
        self.assertIn('hx-select-oob="#roMatched"', page)                                                 # refreshed with each search
        matched = panel(contacts)                                                                     # what matched, as badges
        self.assertIn('data-matched="contacts"', matched)
        self.assertIn('data-ro-filter-kind="contacts" data-ro-filter-field="phone" data-matched-field="phone"', matched)
        self.assertIn('title="Phone: 1"', matched)
        self.assertIn('<span role="img" aria-hidden="true">📱</span>', matched)
        self.assertIn('title="Held by: ', panel(found('Jane Smith')))                                  # a holder's name
        self.assertIn('title="Across fields: 1"', panel(found('Jane Smith')))                          # first and last name together
        self.assertIn('title="Notes: 1"  data-ro-filter-kind="logons" data-ro-filter-field="notes" data-matched-field="notes"', panel(found('ramp')))   # log ons too

    def test_a_search_panel_badge_filters_the_results_and_says_so(self):
        m = self.member(firstName='Jane', lastName='Smith', mobile='0412345678')
        self.vessel(m, vesselName='Sea Dog', registration='AB123Q')
        self.a.post('/member/%d/contacts' % m, data={'name': 'Sam Smith', 'phone': '0499888777'})
        self.logon(registration='AB123Q', notes='Sam Smith called')
        get = lambda url: self.a.get(url).get_data(as_text=True)
        results = lambda html: html[html.index('<div id="roFound">'):]
        everything = get('/radio/search?q=smith')
        self.assertNotIn('Filter applied', everything)
        for kind in ('members', 'contacts', 'logons'):
            self.assertIn('data-found="%s"' % kind, everything)
        contacts = get('/radio/search?q=smith&kind=contacts')                                         # a kind's badge
        self.assertEqual(results(contacts).count('data-found='), 1)
        self.assertIn('data-found="contacts"', results(contacts))
        self.assertIn('Filter applied', contacts)
        self.assertIn('showing 1 of the 4 records found', contacts)                                  # Jane Smith, Sam Smith, her vessel, the log on
        panel = contacts[contacts.index('<div id="roMatched">'):contacts.index('<div id="roFound">')]
        self.assertLess(panel.index('data-ro-filter-clear'), panel.index('data-matched='))            # Clear filter first in the panel
        bar = contacts[contacts.index('class="dc-record-filter-applied"'):]
        self.assertNotIn('data-ro-filter-clear', bar[:bar.index('</div>')])                             # not in the bar
        self.assertNotIn('data-ro-filter-clear', everything[everything.index('<div id="roMatched">'):everything.index('<div id="roFound">')])   # no filter, no button
        self.assertIn('aria-pressed="true" class="dc-record-panel-badge dc-record-panel-badge-heading dc-record-panel-badge-active" title="Emergency contacts: 1"', contacts)
        self.assertIn('id="roFilterKind" value="contacts">', contacts)                                  # kept with the next search
        self.assertIn('data-matched="members"', contacts)                                               # the panel still counts everything
        notes = get('/radio/search?q=smith&kind=logons&field=notes')                                   # a field's badge
        self.assertEqual(results(notes).count('data-found='), 1)
        self.assertIn('data-found="logons"', results(notes))
        self.assertIn('dc-record-panel-badge-active" title="Notes: 1"', notes)
        self.assertEqual(results(get('/radio/search?q=smith&kind=members&field=mobile')).count('data-record='), 0)   # no member matched smith in mobile
        self.assertIn('0 records match', get('/radio/search?q=smith&kind=members&field=mobile'))
        self.assertIn('data-found="members"', results(get('/radio/search?q=jane%20smith&kind=members&field=across')))   # first and last name together
        for bad in ('kind=boats', 'field=notes', 'kind=members&field=phone', 'kind=logons&field=holder'):
            self.assertEqual(self.a.get('/radio/search?q=smith&' + bad).status_code, 400, bad)

    def test_the_log_members_and_public_vessels_panels_show_what_matched(self):
        m = self.member(firstName='Jane', lastName='Smith')
        self.vessel(m, vesselName='Sea Dog', registration='AB123Q')
        self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'registration': 'PUB01', 'ownerName': 'Alex Public', 'ownerPhone': '0411222333'})
        self.logon(registration='AB123Q', notes='Called from the ramp')
        get = lambda url: self.a.get(url).get_data(as_text=True)
        cases = [('/logons', 'roLogPanel', 'roMatched', 'q=ab123', 'logons', 'registration', 'Vessel Rego. No.'),
                 ('/members', 'roMemberPanel', 'roMemberMatched', 'q=ab123', 'members', 'vesselRegos', 'Vessel regos'),
                 ('/vessels', 'roVesselPanel', 'roVesselMatched', 'q=0411222333', 'public', 'ownerPhone', 'Phone')]
        for url, panel_id, body_id, query, gid, field, label in cases:
            page = get(url)
            self.assertIn('data-dc-record-panel aria-controls="%s"' % panel_id, page)                    # the panel button
            self.assertIn('id="%s" class="dc-record-panel" aria-label="What the search matched" data-open="0"' % panel_id, page)   # starts closed
            self.assertIn('The fields a search matches show here.', page)
            self.assertIn('#%s' % body_id, page)                                                         # refreshed with the rows (hx-select-oob)
            found = get(url + '?' + query)
            badge = '<span class="dc-record-panel-badge" title="%s: 1"  data-matched-field="%s">' % (label, field)   # plain: no group to open
            self.assertIn('data-matched="%s"' % gid, found)
            self.assertIn(badge, found)
        self.assertIn('data-matched-field="registration"', get('/logons/rows?partial=1&q=ab123'))          # and on the log's 30s refresh
        self.assertIn('0 records match “zzzz”', get('/members?q=zzzz'))

    def test_the_search_panel_counts_each_field_the_way_the_search_matches(self):
        rows = [{'firstName': 'Jane', 'lastName': 'Smith', 'mobile': '0412 345 678', 'holder': {'name': 'm1 Jane Smith'}},
                {'firstName': 'Janet', 'lastName': 'Jones', 'mobile': '', 'holder': {'name': 'Blue Duck'}}]
        fields = ('firstName', 'lastName', 'mobile')
        self.assertEqual(M._matched_fields(rows, 'jane', fields), [('firstName', 2)])
        self.assertEqual(M._matched_fields(rows[:1], '0412345678', fields), [('mobile', 1)])             # spaces ignored, as the search does
        self.assertEqual(M._matched_fields(rows[:1], 'jane smith', fields), [('across', 1)])
        self.assertEqual(M._matched_fields(rows[1:], 'duck', fields, extra=lambda r: r['holder']['name']), [('holder', 1)])
        self.assertEqual(M.matched({'members': rows}, 'jane'), {'members': [('firstName', 'First name', 2)]})
        found = {'members': rows, 'contacts': [], 'vessels': [], 'trailers': [], 'cars': []}             # as find returns them for 'jane'
        self.assertEqual(M.narrow(found, 'jane', 'members', 'firstName')['members'], rows)
        self.assertEqual(M.narrow(dict(found, members=rows[:1]), 'jane smith', 'members', 'across')['members'], rows[:1])
        self.assertEqual(M.narrow(found, 'jane', 'members')['members'], rows)
        self.assertEqual(M.narrow(found, 'jane', 'members')['contacts'], [])
        self.assertRaises(L.Refused, M.narrow, found, 'jane', 'members', 'holder')                    # members have no holder
        logons = [{'registration': 'AB123', 'mobile': '0412 345 678', 'notes': 'ab123 rack', 'tripRef': None}]
        self.assertEqual(L.matched_fields(logons, 'ab123'), [('registration', 'Vessel Rego. No.', 1), ('notes', 'Notes', 1)])
        self.assertEqual(L.matched_fields(logons, '0412345678'), [('mobile', 'Mobile Phone Number', 1)])
        self.assertEqual(L.matched_rows(logons, 'ab123', 'notes'), logons)
        self.assertRaises(L.Refused, L.matched_rows, logons, 'ab123', 'phone')
        symbols = self.app.jinja_env.get_template('radio/_ui.html').module.FIELD_SYMBOLS                  # every badge has its emoji
        for field in set(sum(M.SEARCH.values(), ())) | set(L.SEARCH_FIELDS) | {M.HOLDER, M.ACROSS}:
            self.assertTrue(symbols.get(field), field)
            self.assertIn(field, dict(M.MATCH_LABELS, **L.SEARCH_LABELS))

    def test_the_vessel_and_mobile_pickers_bring_their_member_or_public_vessel(self):
        m = self.member(mobile='0412000111')
        self.vessel(m, vesselName='Sea Dog', registration='AB123Q')
        self.a.post('/member/%d/contacts' % m, data={'name': 'Sam Smith', 'phone': '0499888777'})
        pub = self.a.post('/vessels/new', data={'vesselName': 'Blue Duck', 'ownerName': 'Alex', 'ownerPhone': '0411222333'},
                          headers={'Accept': 'application/json'}).json['id']
        self.a.post('/vessel/%d/contacts' % pub, data={'name': 'Pat Public', 'phone': '0433444555'})
        boats = {i['primary']: i for i in self.a.get('/api/logons/all-vessels?q=').json['items']}
        self.assertEqual(set(boats), {'Sea Dog', 'Blue Duck'})                                        # member's and public
        self.assertEqual(boats['Sea Dog']['member']['memberNumber'], 'm00001')
        self.assertIsNone(boats['Blue Duck']['member'])
        numbers = lambda q: {(i['kind'], i['name']): i for i in self.a.get('/api/logons/mobiles?q=' + q).json['items']}
        self.assertEqual(list(numbers('0412 000')), [('member', 'm00001 Jane Smith')])
        contact = numbers('0499888')[('contact', 'Sam Smith')]
        self.assertEqual((contact['member']['id'], contact['phone'], contact['holder']['name']), (m, '0499 888 777', 'm00001 Jane Smith'))
        owner = numbers('0411222')[('public', 'Alex')]
        self.assertEqual((owner['member'], owner['vessel']['id'], owner['holder']['name']), (None, pub, 'Blue Duck'))
        public_contact = numbers('0433')[('contact', 'Pat Public')]
        self.assertEqual(public_contact['vessel']['id'], pub)
        html = self.a.get('/api/logons/mobiles?q=0411222').json['html']                  # whose number and who holds it, as badges in one column
        self.assertNotIn('data-column="holder"', html)
        self.assertIn('<span class="dc-record-badge-value">Alex</span></span> · <span', html)
        self.assertNotIn('data-column="holder"', self.a.get('/api/logons/mobiles?q=0412000').json['html'])   # a member's own number: Whose, never blank
        self.assertIn('aria-label="Member">👤</span><span class="dc-record-badge-value">m00001 Jane Smith', self.a.get('/api/logons/mobiles?q=0412000').json['html'])
        self.assertIn('title="Contact"><span role="img" aria-label="Contact">🧑</span><span class="dc-record-badge-value">Alex</span>', html)
        self.assertIn('title="Public user"><span role="img" aria-label="Public user">🌐</span><span class="dc-record-badge-value">Blue Duck</span>', html)
        self.assertEqual(self.a.get('/api/logons/mobiles?q=').json['items'], [])                    # no digits, nothing
        self.assertIn('data-sp-count>0 found<', self.a.get('/api/logons/mobiles?q=').json['html'])
        page = self.a.get('/logons/new').get_data(as_text=True)
        self.assertIn('id="roPickAnyVessel"', page)
        self.assertIn('id="roPickMobile"', page)
        self.assertIn('href="/radio/search" target="_blank"', page)                                   # Search in a new tab

    def test_every_field_is_named_with_its_emoji(self):
        m = self.member()
        self.a.post('/member/%d/contacts' % m, data={'name': 'Sam Smith', 'relationship': 'Partner', 'phone': '0499888777'})
        page = self.a.get('/member/%d' % m).get_data(as_text=True)
        for name, emoji in (('firstName', '🪪'), ('mobile', '📱'), ('email', '✉️'), ('address', '🏠'), ('notes', '🗒️')):
            self.assertIn('<label for="member-%s"><span class="ro-field-symbol" aria-hidden="true">%s</span>' % (name, emoji), page)
        contact = self.a.get('/member/%d/contacts/new' % m).get_data(as_text=True)
        for name, emoji in (('name', '🆘'), ('relationship', '🤝'), ('phone', '📱')):
            self.assertIn('<label for="contacts-new-%s"><span class="ro-field-symbol" aria-hidden="true">%s</span>' % (name, emoji), contact)
        boat = self.a.get('/member/%d/vessels/new' % m).get_data(as_text=True)
        for name, emoji in (('hullColour', '🎨'), ('vesselType', '⛵'), ('make', '🏭'), ('model', '🏷️'), ('ais', '📡')):
            self.assertIn('<span class="ro-field-symbol" aria-hidden="true">%s</span>' % emoji, boat)
        self.assertIn('<span title="Relationship"><span class="dc-record-word">Relationship</span></span>', page)   # list headings: words
        self.assertIn('<span class="dc-record-grid-value-symbol" aria-hidden="true">🤝</span>', page)                   # the emoji before the value
        logon = self.a.get('/logons/new').get_data(as_text=True)
        self.assertIn('<label for="f-channel"><span class="ro-field-symbol" aria-hidden="true">📻</span> How they logged on</label>', logon)
        self.assertIn('<label for="f-hullColour"><span class="ro-field-symbol" aria-hidden="true">🎨</span> Hull colour</label>', logon)
        self.assertIn('<span title="Email"><span class="dc-record-word">Email</span></span>', self.a.get('/members').get_data(as_text=True))

    def test_member_history_holds_every_change_they_hold(self):
        from server.member_pages import member_history

        class FakeHost:
            def __init__(self):
                self.asked = []
            def history(self, cur, table, record_id, by='id_'):
                self.asked.append((table, record_id, by))
                return [{'id_': 1, 'time': '2026-09-14 10:0%d' % len(self.asked), 'changes': []}]
        h = FakeHost()
        events = member_history(None, h, 7)
        self.assertEqual(h.asked, [('Members', 7, 'id_'), ('EmergencyContacts', 7, 'memberId'), ('Vessels', 7, 'memberId'),
                                   ('Trailers', 7, 'memberId'), ('Cars', 7, 'memberId')])
        self.assertEqual([e['scope'] for e in events], ['Car', 'Trailer', 'Vessel', 'Emergency contact', 'Details'])   # newest first

        class NoHistory:
            def history(self, *a, **k):
                return None
        self.assertIsNone(member_history(None, NoHistory(), 7))
        from server.member_pages import VESSEL_HISTORY_SCOPES
        h = FakeHost()
        events = member_history(None, h, 9, VESSEL_HISTORY_SCOPES)
        self.assertEqual(h.asked, [('Vessels', 9, 'id_'), ('EmergencyContacts', 9, 'vesselId')])
        self.assertEqual([e['scope'] for e in events], ['Emergency contact', 'Details'])


if __name__ == '__main__':
    unittest.main()
