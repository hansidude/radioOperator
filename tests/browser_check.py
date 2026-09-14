"""Radio acceptance checks through Quackit. Run quackit's ./verify radio.
Creates a uniquely named sample record and closes/discards it, retaining history.
"""
from datetime import date, timedelta
import os
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect

URL = os.environ.get('RADIO_URL', 'http://localhost:80').rstrip('/')
if URL not in ('http://localhost:80', 'http://host.docker.internal:80'):
    raise SystemExit('Use quackit/verify radio; only the port 80 dev stack is supported.')
ARTIFACTS = Path('/artifacts')


def main(engine='chromium'):
    token = uuid4().hex[:10].upper()
    vessel = 'VERIFY-' + token
    today = date.today().isoformat()
    fields = dict(callDay=today, callTime='13:45',
                  vesselName=vessel, registration=token, mobile='0412345678',
                  length='6', hullColour='white', make='Quintrex', model='610',
                  pob='2', departurePoint='Marina', destination='Verification bay',
                  etaDay=(date.today() + timedelta(days=1)).isoformat(), eta='17:00')
    first = {k: v for k, v in fields.items() if k != 'pob'}    # POB comes later: a complete save would log it on (ACC-3)
    record = None
    layout_records = []
    watching = closed = False
    overdue_record = None
    with sync_playwright() as pw:
        browser = getattr(pw, engine).launch()
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        # Model an existing browser holding the old unversioned stylesheet. New
        # markup must request a new URL, rather than relying on a hard refresh.
        # The same for the view buttons' script: an old copy without the size buttons, as a browser that
        # had the Cards/Paragraphs rollout still holds. New buttons must never run against it.
        context.route('**/static/js/record_view.js', lambda route: route.fulfill(
            status=200, content_type='application/javascript', body='/* cached script predating the size buttons */'))
        context.route('**/static/css/record_views.css', lambda route: route.fulfill(
            status=200, content_type='text/css', body='/* cached stylesheet predating the shared grid */'))
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        errors, writes = [], []
        # A field check (focus leaving a box) posts {check: true} and writes nothing; a save is every other POST.
        is_check = lambda request: '"check":true' in (request.post_data or '')
        is_save = lambda r: r.request.method == 'POST' and '/logon' in r.url and not is_check(r.request)
        context.on('page', lambda p: p.on('pageerror', lambda e: errors.append(e.stack)))
        page.on('pageerror', lambda e: errors.append(e.stack))
        page.on('request', lambda r: writes.append(r.url) if r.method == 'POST' and '/logon' in r.url and not is_check(r) else None)

        def visit(path):
            response = page.goto(URL + path)
            assert response and response.status == 200, 'GET %s: HTTP %s' % (path, response.status if response else 'none')
            assert '/login' not in page.url, 'Sample login failed'

        def list_beside_panel(panel, listed, what):
            # An open panel sits left of the list, outside its container: the list keeps the usual ~1200px width.
            p, l = page.locator(panel).bounding_box(), page.locator(listed).bounding_box()
            assert 900 < l['width'] < 1300, '%s is not at the usual ~1200px width beside its panel: %s' % (what, l['width'])
            assert p['x'] + p['width'] <= l['x'], '%s: the panel is not left of the list: panel %s, list %s, page %s' % (
                what, p, l, page.evaluate("() => [document.getElementById('roFound').closest('.container-fluid').className, innerWidth, document.documentElement.clientWidth]"))

        def usual_width(inside, what):
            # Quackit's usual ~1200px page width (layout's mySpacing), measured at the 1920px viewport.
            width = page.evaluate("s => document.querySelector(s).closest('.container-fluid.mySpacing').getBoundingClientRect().width", inside)
            assert 900 < width < 1300, '%s is not at the usual ~1200px page width: %s' % (what, width)

        def save(status=200):
            nonlocal record
            with page.expect_response(is_save) as pending:
                page.locator('#saveRecord').click()
            response = pending.value
            assert response.status == status, 'Save HTTP %s: %s' % (response.status, response.text()[:1000])
            if status == 200:
                page.wait_for_url(re.compile('/logon/[0-9]+(?:#.*)?$'))
                record = int(re.search(r'/logon/([0-9]+)', page.url).group(1))
                expect(page.locator('#saveStatus')).to_have_text('Saved')
                return {'id': record}
            return None

        try:
            page.goto(URL + '/login')
            page.locator('input[name=username]').fill(os.environ.get('RADIO_USER', 'test'))
            page.locator('input[name=password]').fill(os.environ.get('RADIO_PASS', 'test'))
            page.locator('button[type=submit], input[type=submit]').first.click()
            # Let the post-login page finish loading: navigating away mid-load leaves Firefox running
            # htmx's start-up on a document that has no body yet, reported as a page error.
            page.wait_for_url(lambda url: '/login' not in url, wait_until='load')
            visit('/logons')
            expect(page.locator('.navbar')).to_be_visible()
            href = page.locator('link[href*="/css/record_views.css"]').get_attribute('href')
            assert '?v=' in href, 'New grid markup must not reuse the cached stylesheet URL'
            script = page.locator('script[src*="/js/record_view.js"]').get_attribute('src')
            assert '?v=' in script, 'New view buttons must not reuse the cached script URL'
            # Members and public vessels, reached from the log's navbar. The Member No. on a log on has to be one.
            page.locator('.navbar a[href="/members"]').first.click()
            page.wait_for_url(re.compile('/members$'))
            expect(page.locator('.entity-nav a[href="/vessels"]')).to_have_count(0)           # Public vessels is on the menu, not the Members page
            expect(page).to_have_title('Radio Logs')                                              # Radio Logs' own program menu
            menu = page.locator('#navbarNav .navbar-nav')
            for href in ('/logons/new', '/members', '/vessels', '/radio/search', '/radio/help', '/logout'):
                expect(menu.locator('a[href="%s"]' % href)).to_have_count(1)
            expect(menu.locator('a[href="/myTasks"]')).to_have_count(0)                            # none of Quackit's menu
            expect(page.locator('#contextNavToggle')).to_have_count(0)
            expect(page.locator('.navbar-brand')).to_have_attribute('href', '/logons')
            expect(page.locator('.navbar-brand > i')).to_have_count(1)                               # Quackit's home icon, once
            expect(page.locator('.navbar-brand > i')).to_have_class(re.compile(r'\bbi-house\b'))
            page.locator('#navbarNav a[href="/radio/help"]').click()                               # Help: the real controls, tried on a sample
            page.wait_for_url(re.compile('/radio/help$'))
            for icon in page.locator('[data-help-icon]').all():
                assert icon.locator('i, span').count() > 0, 'Help icon not filled: %s' % icon.get_attribute('data-help-icon')
            page.locator('#roHelpToolbar [data-dc-record-view="cards"]').click()
            expect(page.locator('#roHelpView')).to_have_class(re.compile(r'\bdc-record-cards\b'))
            page.locator('#roHelpToolbar [data-dc-record-view="cards"]').click()
            page.screenshot(path=str(ARTIFACTS / ('radio-help-%s.png' % engine)))
            visit('/myTasks')                                                                       # Quackit's own pages keep Quackit's menu
            expect(page.locator('#navbarNav a[href="/radio/help"]')).to_have_count(0)
            expect(page.locator('#navbarNav a[href="/logons"]')).to_have_count(1)
            expect(page.locator('#contextNavToggle')).to_have_count(1)
            expect(page).to_have_title('QUACKIT')
            page.goto(URL + '/members')
            expect(page.locator('[data-dc-record-width]:visible')).to_have_attribute('title', 'Usual page width')   # Members starts wide
            page.locator('a[href="/members/new"]').click()
            page.wait_for_url(re.compile('/members/new$'))
            usual_width('#ro-member-details', 'New member')
            page.locator('#member-firstName').fill('Verify')
            page.locator('#member-mobile').fill('0412 345')                                # not 10 digits: refused, red
            page.locator('#ro-member-details button.btn-warning').click()
            expect(page.locator('#member-mobile')).to_have_class(re.compile('is-invalid'))
            expect(page.locator('#member-lastName')).to_have_class(re.compile('is-invalid'))  # a last name is required
            expect(page.locator('#member-firstName')).to_have_value('Verify')                 # what was typed stays
            expect(page.locator('#ro-member-details [placeholder]')).to_have_count(0)
            page.locator('#member-lastName').fill('Member ' + token)
            page.locator('#member-mobile').fill('0412345678')
            page.locator('#member-email').fill('verify@example.com')
            page.locator('#ro-member-details button.btn-warning').click()
            page.wait_for_url(re.compile('/member/[0-9]+$'))
            member_page = page.url
            usual_width('#ro-member-details', 'Member')
            member_no = page.locator('#ro-member-details .ro-section-title').inner_text().split()[-1]
            assert re.match(r'^m[0-9]{5}$', member_no), 'Member number is not mXXXXX: %r' % member_no
            expect(page.locator('#member-mobile')).to_have_value('0412 345 678')
            # Contacts, vessels, trailers and cars: Quackit's shared record_grid rows, each opening its own page.
            def add_on_tab(kind, values, refused=None):
                page.locator('[data-entity-tab="%s"]' % kind).click()
                expect(page.locator('#ro-member-%s .dc-record-toolbar [data-dc-record-view="cards"]' % kind)).to_be_visible()
                page.locator('#ro-member-%s a[href$="/%s/new"]' % (kind, kind)).click()
                page.wait_for_url(re.compile(r'/member/[0-9]+/%s/new$' % kind))
                expect(page.locator('[placeholder]')).to_have_count(0)
                for name, value in values.items():
                    page.locator('#%s-new-%s' % (kind, name)).fill(value)
                if refused:
                    name, bad, good = refused
                    page.locator('#%s-new-%s' % (kind, name)).fill(bad)
                    page.locator('form#%s-new button.btn-warning' % kind).click()
                    expect(page.locator('#%s-new-%s' % (kind, name))).to_have_class(re.compile('is-invalid'))
                    page.locator('#%s-new-%s' % (kind, name)).fill(good)
                page.locator('form#%s-new button.btn-warning' % kind).click()
                page.wait_for_url(re.compile(r'/member/[0-9]+#%s$' % kind))
                expect(page.locator('#ro-member-%s' % kind)).to_be_visible()                  # back on the tab it came from
            add_on_tab('vessels', {'vesselName': vessel, 'registration': token}, refused=('length', 'six', '6'))
            add_on_tab('vessels', {'vesselName': 'SECOND-' + token, 'registration': 'S2-' + token})
            rows = page.locator('#radioMemberVessels .dc-record-grid-row')
            expect(rows).to_have_count(2)
            expect(page.locator('#radioMemberVessels .dc-record-grid-head')).to_contain_text('Vessel Name')
            expect(rows.nth(1).locator('.dc-record-count')).to_have_text('2')                     # rows numbered from 1, like Quackit's lists
            page.locator('#ro-member-vessels .dc-search-input').first.fill('second-')             # the shared row search
            expect(rows.filter(has_text='SECOND-' + token)).to_be_visible()
            expect(rows.filter(has_text='SECOND-' + token)).to_have_count(1)
            expect(page.locator('#radioMemberVessels .dc-record-grid-row:visible')).to_have_count(1)
            expect(rows.filter(has_text='SECOND-' + token).locator('.dc-record-count')).to_have_text('1')   # what is left is numbered again
            page.locator('#ro-member-vessels .dc-search-reset').first.click()
            expect(rows).to_have_count(2)
            expect(rows.nth(0)).to_be_visible()
            expect(rows.nth(1).locator('.dc-record-count')).to_have_text('2')
            page.locator('#ro-member-vessels [data-dc-record-view="cards"]').click()                 # the shared view buttons
            expect(page.locator('#radioMemberVesselsView')).to_have_class(re.compile(r'\bdc-record-cards\b'))
            page.locator('#ro-member-vessels [data-dc-record-view="cards"]').click()
            rows.nth(1).locator('a[title="Open vessel"]').click()                                 # a row opens its own page
            page.wait_for_url(re.compile(r'/member/[0-9]+/vessels/[0-9]+$'))
            page.locator('input[name="hullColour"]').fill('white')
            page.locator('form button.btn-warning').click()
            page.wait_for_url(re.compile(r'/member/[0-9]+#vessels$'))
            expect(rows.filter(has_text='SECOND-' + token)).to_contain_text('white')
            add_on_tab('contacts', {'name': 'Verify Contact ' + token, 'phone': '0499888777'})
            expect(page.locator('#radioMemberContacts .dc-record-grid-row')).to_contain_text('0499 888 777')
            page.locator('[data-entity-tab="details"]').click()
            page.locator('#member-email').fill('verify.changed@example.com')                  # one save, one history event
            page.locator('#member-firstName').fill('Verified')                                # a member's own first name is a change
            page.locator('#ro-member-details button.btn-warning').click()
            page.wait_for_url(re.compile(r'/member/[0-9]+#details$'))
            expect(page.locator('#member-email')).to_have_value('verify.changed@example.com')
            for tab in ('trailers', 'cars', 'history'):
                page.locator('[data-entity-tab="%s"]' % tab).click()
                expect(page.locator('#ro-member-%s' % tab)).to_be_visible()
            member_history = page.locator('#ro-member-history .dc-history')
            expect(member_history).to_contain_text('verify.changed@example.com')                  # Members_history
            expect(member_history.locator('.dc-history-field', has_text='First name')).not_to_have_count(0)
            expect(member_history.locator('.badge', has_text='Vessel')).not_to_have_count(0)       # and every vessel they hold
            expect(member_history.locator('.badge', has_text='Emergency contact')).not_to_have_count(0)
            expect(member_history).to_contain_text('white')                                       # the vessel's hull colour edit
            page.locator('[data-entity-tab="vessels"]').click()
            page.screenshot(path=str(ARTIFACTS / ('radio-member-%s.png' % engine)), full_page=True)
            visit('/members?q=' + token)
            expect(page.locator('#radioMembers .dc-record-grid-row')).to_have_count(1)
            expect(page.locator('#radioMembers')).to_contain_text(vessel)
            for width in (1920, 390):
                page.set_viewport_size({'width': width, 'height': 800})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Members overflow at %spx' % width
            page.set_viewport_size({'width': 1920, 'height': 1080})
            visit('/vessels')
            expect(page.locator('.entity-nav a[href="/members"]')).to_have_count(0)           # Members is on the menu, not this page
            visit('/vessels/new')
            usual_width('#ro-vessel-details', 'New public vessel')
            page.locator('#public-vesselName').fill('PUBLIC-' + token)
            page.locator('#public-registration').fill('VESSEL-' + token)
            page.locator('#public-ownerName').fill('Verify Public ' + token)
            page.locator('#public-ownerPhone').fill('0411222333')
            page.locator('#public-notes').fill('Verify notes\nsecond line')                     # a public vessel has notes
            page.locator('#ro-vessel-details button.btn-warning').click()
            page.wait_for_url(re.compile('/vessel/[0-9]+$'))
            public_vessel = int(page.url.rsplit('/', 1)[1])
            usual_width('#ro-vessel-details', 'Public vessel')
            expect(page.locator('#public-notes')).to_have_value('Verify notes\nsecond line')
            page.locator('[data-entity-tab="contacts"]').click()                                  # and emergency contacts
            page.locator('#ro-vessel-contacts a[href$="/contacts/new"]').click()
            page.wait_for_url(re.compile(r'/vessel/[0-9]+/contacts/new$'))
            usual_width('form#contacts-new', 'New emergency contact')
            page.locator('#contacts-new-name').fill('Verify Public Contact ' + token)
            page.locator('#contacts-new-phone').fill('0499777666')
            page.locator('form#contacts-new button.btn-warning').click()
            page.wait_for_url(re.compile(r'/vessel/[0-9]+#contacts$'))
            expect(page.locator('#radioVesselContacts .dc-record-grid-row')).to_contain_text('Verify Public Contact ' + token)
            visit('/vessels?q=' + token)
            expect(page.locator('#radioVessels .dc-record-grid-row')).to_have_count(1)
            # Member or public user, answered through Quackit's shared search picker without leaving the page.
            visit('/logons/new')
            def pick(text):
                page.locator('#spResults [data-pick]', has_text=text).first.click()
            page.locator('#roPickMember').click()
            expect(page.locator('#searchPicker')).to_be_visible()
            expect(page.locator('label[for="spInput"]')).to_have_text('👤 Member: number, name or mobile')   # with the emoji
            expect(page.locator('#spTitle')).to_have_text('👤Member')
            expect(page.locator('#spCrumb')).to_contain_text('👤 member: choosing')
            expect(page.locator('#searchPicker [placeholder]')).to_have_count(0)                # a label on top, nothing inside
            size = page.locator('#searchPicker > .card').evaluate('''card => {                     // a contained page wide, 80% tall
                const probe = document.createElement('div'); probe.style.width = '120ch'; card.appendChild(probe);
                const box = card.getBoundingClientRect(), out = {w: box.width, h: box.height, ch: probe.getBoundingClientRect().width,
                                                                 vw: innerWidth, vh: innerHeight};
                probe.remove(); return out; }''')
            assert abs(size['w'] - min(size['ch'], .94 * size['vw'])) < 1 and abs(size['h'] - .8 * size['vh']) < 1, size
            page.locator('#spInput').fill(token)
            expect(page.locator('#spResults [data-pick]', has_text=member_no).first).to_contain_text('📱 0412 345 678 · 🛥️ ' + vessel)
            pick(member_no)                                                                         # each field after its emoji
            expect(page.locator('#spLabel')).to_have_text("🛥️ Member's vessel: name or rego")
            expect(page.locator('#spResults [data-pick]', has_text=vessel).first).to_contain_text('🔖 ' + token)
            expect(page.locator('#spFilter')).to_contain_text('No vessel')
            pick(vessel)
            expect(page.locator('#searchPicker')).to_be_hidden()
            expect(page.locator('#f-memberNumber')).to_have_value(member_no)
            for name, value in (('vesselName', vessel), ('registration', token), ('length', '6'), ('mobile', '0412 345 678')):
                expect(page.locator('#f-' + name)).to_have_value(value)
            expect(page.locator('#roWhoNow [data-who="member"]')).to_contain_text(member_no)      # badges with their symbols
            expect(page.locator('#roWhoNow [data-who="vessel"]')).to_contain_text(vessel)
            expect(page.locator('#f-vesselId')).not_to_have_value('')
            for name in ('memberNumber', 'vesselName', 'registration', 'length', 'hullColour', 'make', 'model'):
                expect(page.locator('#f-' + name)).not_to_be_editable()                          # the record's, not typed
            expect(page.locator('#f-mobile')).to_be_editable()                                    # the caller's number
            who_tab = page.locator('#roWhoTab')                                                   # the member's own page, in a tab
            expect(who_tab).to_be_visible()
            expect(who_tab).to_have_text(re.compile('Member'))
            who_tab.click()
            panel = page.locator('#roWhoPanel')
            expect(panel.locator('#ro-member-details')).to_be_visible()
            expect(panel.locator('#member-lastName')).to_have_value('Member ' + token)
            panel.locator('[data-entity-tab="vessels"]').click()                                 # its tabs work, loaded in place
            expect(panel.locator('#radioMemberVessels .dc-record-grid-row')).to_have_count(2)
            panel.locator('#ro-member-vessels .dc-search-input').first.fill('second-')           # and its search
            expect(panel.locator('#radioMemberVessels .dc-record-grid-row:visible')).to_have_count(1)
            panel.locator('#ro-member-vessels .dc-search-reset').first.click()
            panel.locator('[data-entity-tab="history"]').click()
            expect(panel.locator('#ro-member-history .dc-history .badge', has_text='Vessel')).not_to_have_count(0)
            expect(panel.locator('#ro-member-history [data-history-toolbar]')).to_be_visible()      # its controls stay in the tab
            expect(page.locator('#appNavbarControls #roWhoPanel, #appNavbarControls [aria-label="Member history controls"]')).to_have_count(0)
            page.screenshot(path=str(ARTIFACTS / ('radio-who-member-tab-%s.png' % engine)), full_page=True)
            panel.locator('[data-entity-tab="vessels"]').click()                                 # correct the vessel on the tab
            panel.locator('#radioMemberVessels .dc-record-grid-row').filter(has_not_text='SECOND-').first.locator('a[title="Open vessel"]').click()
            expect(panel.locator('input[name="hullColour"]')).to_be_visible()
            panel.locator('input[name="hullColour"]').fill('green')
            panel.locator('form button.btn-warning').first.click()
            expect(panel.locator('#radioMemberVessels')).to_be_attached()                         # back on the member, in place
            page.locator('[data-ro-tab="entry"]').click()
            expect(page.locator('#f-hullColour')).to_have_value('green')                          # the log on box follows the record
            expect(page).to_have_url(re.compile('/logons/new(#.*)?$'))
            page.locator('#roWhoNow [data-ro-clear="vessel"]').click()                            # a wrong vessel goes, the member stays
            expect(page.locator('#f-vesselName')).to_have_value('')
            expect(page.locator('#f-vesselName')).not_to_be_editable()
            expect(page.locator('#f-memberNumber')).to_have_value(member_no)
            expect(page.locator('#roWhoNow [data-who="vessel"]')).to_have_count(0)
            page.locator('#roWhoNow [data-ro-pick-vessel]').click()                               # pick one of theirs again
            expect(page.locator('#spLabel')).to_have_text("🛥️ Member's vessel: name or rego")
            pick(vessel)
            expect(page.locator('#f-vesselName')).to_have_value(vessel)
            expect(page.locator('#roWhoNow [data-who="vessel"]')).to_contain_text(vessel)
            first_pick = page.locator('#f-vesselId').input_value()
            page.locator('#roPickMember').click()                                                 # a boat not on their record yet
            page.locator('#spInput').fill(token)
            pick(member_no)
            page.locator('#spInput').fill('NEWBOAT-' + token)
            expect(page.locator('#spResults')).to_contain_text('No matches')
            page.locator('#spFilter [data-create]').click()
            expect(page.locator('#roNewVesselPanel')).to_be_visible()
            expect(page.locator('#roNewVesselPanel')).to_contain_text(member_no)
            expect(page.locator('#roNewVesselPanel [placeholder]')).to_have_count(0)
            page.locator('#roNewVessel-vesselName').fill('NEWBOAT-' + token)
            page.locator('#roNewVessel-registration').fill('NB-' + token)
            page.locator('#roNewVessel-length').fill('six')                                       # not a number: red, still on the page
            page.locator('#roNewVessel button.btn-warning').click()
            expect(page.locator('#roNewVessel-length')).to_have_class(re.compile('is-invalid'))
            expect(page.locator('#roNewVessel [data-ro-form-error]')).to_contain_text('Length')
            page.locator('#roNewVessel-length').fill('5')
            page.locator('#roNewVessel button.btn-warning').click()
            expect(page.locator('#roNewVesselPanel')).to_be_hidden()
            expect(page.locator('#f-vesselName')).to_have_value('NEWBOAT-' + token)
            expect(page.locator('#f-registration')).to_have_value('NB-' + token)
            expect(page.locator('#f-vesselId')).not_to_have_value(first_pick)
            page.locator('#roPickPublic').click()                                                 # a public user's known vessel
            expect(page.locator('#spLabel')).to_have_text('🌐 Public vessel: name, rego or owner')
            page.locator('#spInput').fill('PUBLIC-' + token)
            pick('PUBLIC-' + token)
            expect(page.locator('#f-memberNumber')).to_have_value('')
            expect(page.locator('#f-vesselName')).to_have_value('PUBLIC-' + token)
            expect(page.locator('#f-registration')).to_have_value('VESSEL-' + token)
            expect(page.locator('#f-vesselId')).to_have_value(str(public_vessel))
            expect(page.locator('#roWhoNow')).to_contain_text('Public')
            expect(who_tab).to_have_text(re.compile('Public vessel'))
            who_tab.click()
            expect(panel.locator('#public-ownerName')).to_have_value('Verify Public ' + token)
            panel.locator('[data-entity-tab="contacts"]').click()                                # its contacts, in the tab
            expect(panel.locator('#radioVesselContacts .dc-record-grid-row')).to_contain_text('Verify Public Contact ' + token)
            page.locator('[data-ro-tab="entry"]').click()
            page.locator('#roWhoNow [data-ro-clear="vessel"]').click()                            # a public user's vessel is the pick: all goes
            for name in ('memberNumber', 'vesselName', 'registration', 'length', 'hullColour', 'make', 'model', 'vesselId'):
                expect(page.locator('#f-' + name)).to_have_value('')
            expect(page.locator('#f-mobile')).to_have_value('0412 345 678')                       # the caller's number stays
            expect(who_tab).to_be_hidden()
            expect(page.locator('#roWhoNow [data-ro-clear]')).to_have_count(0)
            expect(page.locator('#roWhoNow')).to_have_text('')
            expect(page.locator('#f-registration')).to_have_class(re.compile('is-invalid'))      # re-checked: an ID is needed again
            page.locator('#roPickPublic').click()                                                 # a public user seen for the first time
            page.locator('#spInput').fill('NEWPUB-' + token)
            page.locator('#spFilter [data-create]').click()
            expect(page.locator('#roNewPublicPanel')).to_be_visible()
            page.locator('#roNewPublic-vesselName').fill('NEWPUB-' + token)
            page.locator('#roNewPublic-registration').fill('NP-' + token)
            page.locator('#roNewPublic button.btn-warning').click()                               # no owner yet: red
            expect(page.locator('#roNewPublic-ownerName')).to_have_class(re.compile('is-invalid'))
            page.locator('#roNewPublic-ownerName').fill('Verify Public New ' + token)
            page.locator('#roNewPublic-ownerPhone').fill('0400111222')
            page.locator('#roNewPublic button.btn-warning').click()
            expect(page.locator('#roNewPublicPanel')).to_be_hidden()
            expect(page.locator('#f-vesselName')).to_have_value('NEWPUB-' + token)
            expect(page.locator('#f-vesselId')).not_to_have_value(str(public_vessel))
            expect(page).to_have_url(re.compile('/logons/new(#[a-z]+)?$'))                       # never left the page
            page.screenshot(path=str(ARTIFACTS / ('radio-who-%s.png' % engine)), full_page=True)
            page.locator('#roPickAnyVessel').click()                                               # 🛥️ Vessel: any vessel
            expect(page.locator('#spLabel')).to_have_text('🛥️ Vessel: name, rego, owner or member')
            page.locator('#spInput').fill(vessel)
            pick(vessel)
            expect(page.locator('#roWhoNow [data-who="member"]')).to_contain_text(member_no)      # a member's vessel brings its member
            expect(page.locator('#roWhoNow [data-who="vessel"]')).to_contain_text(vessel)
            page.locator('#roWhoNow [data-ro-clear="member"]').click()
            page.locator('#roPickMobile').click()                                                  # 📱 Mobile: an emergency contact's phone
            page.locator('#spInput').fill('0499888777')
            expect(page.locator('#spResults [data-pick]', has_text='Verify Contact ' + token).first.locator('span').first).to_have_text('🆘')   # a contact's number
            pick('Verify Contact ' + token)
            expect(page.locator('#roWhoNow [data-who="member"]')).to_contain_text(member_no)      # brings the member it belongs to
            expect(page.locator('#roWhoNow [data-ro-pick-vessel]')).to_be_visible()
            expect(page.locator('#roOpenSearch')).to_have_attribute('target', '_blank')          # 🔎 Search opens in a new tab
            expect(page.locator('label[for="f-hullColour"]')).to_have_text('🎨 Hull colour')         # every field with its emoji
            failing_search = re.compile(r'/api/logons/members')
            page.route(failing_search, lambda route: route.fulfill(status=500, body='verification failure'))
            page.locator('#roPickMember').click()
            expect(page.locator('#spResults [data-sp-error]')).to_have_text('Search failed: HTTP 500 from /api/logons/members?q=')
            page.unroute(failing_search)
            page.keyboard.press('Escape')
            expect(page.locator('#searchPicker')).to_be_hidden()
            visit('/logons')
            page.locator('.navbar a[href="/radio/search"]').first.click()                          # the Search page, from the log
            page.wait_for_url(re.compile('/radio/search$'))
            with page.expect_response(lambda r: '/radio/search?' in r.url):
                page.locator('#roFindAll').fill(token)
            for kind in ('members', 'contacts', 'vessels'):
                expect(page.locator('#roFound [data-found="%s"]' % kind)).to_be_visible()
            page.locator('[data-found="contacts"] > .grp-header').click()                           # a kind collapses
            expect(page.locator('#radioFoundContacts')).to_be_hidden()
            expect(page.locator('#radioFoundMembers')).to_be_visible()
            with page.expect_response(lambda r: '/radio/search?' in r.url):
                page.locator('#roFindAll').fill(token + ' ')
            expect(page.locator('#roFound [data-found="contacts"]')).to_have_class(re.compile(r'\bcollapsed\b'))   # and stays collapsed on the next search
            expect(page.locator('#radioFoundContacts')).to_be_hidden()
            page.locator('[data-found="contacts"] > .grp-header').click()
            expect(page.locator('#radioFoundContacts')).to_be_visible()
            list_beside_panel('#roFoundPanel', '#roFound', 'Search')
            width_button = page.locator('[data-dc-record-width]:visible')                          # contained or full width, remembered
            expect(width_button).to_have_attribute('title', 'Full width')
            width_button.click()
            expect(width_button).to_have_attribute('title', 'Usual page width')
            expect(width_button.locator('i')).to_have_class('bi bi-arrows-angle-contract')
            full = page.evaluate("() => document.getElementById('roFoundView').closest('.container-fluid.mySpacing').getBoundingClientRect().width")
            assert full > 1700, 'Full width did not widen Search: %s' % full
            assert page.locator('#roFoundPanel').bounding_box()['x'] < 60, 'Full width: the panel is not at the left edge'
            page.reload()
            expect(page.locator('[data-dc-record-width]:visible')).to_have_attribute('title', 'Usual page width')
            page.locator('[data-dc-record-width]:visible').click()
            list_beside_panel('#roFoundPanel', '#roFound', 'Search back in its container')
            page.locator('#roFindAll').fill(token)
            expect(page.locator('#roFound [data-found="members"]')).to_be_visible()
            # The panel (view_controls + record_panel): what the search matched, as badges beside the results.
            panel = page.locator('#roFoundPanel')
            expect(panel).to_be_visible()
            contact_names = page.locator('#roMatched [data-matched="contacts"] [data-matched-field="name"]')
            expect(contact_names).to_be_visible()
            expect(contact_names).to_have_attribute('title', re.compile(r'^Name: [0-9]+$'))
            expect(contact_names.locator('[role="img"]')).to_have_text('🆘')
            assert panel.bounding_box()['x'] + panel.bounding_box()['width'] <= page.locator('#roFound').bounding_box()['x'], 'The panel is not beside the results'
            page.locator('[data-found="contacts"] > .grp-header').click()
            expect(page.locator('#radioFoundContacts')).to_be_hidden()
            contact_names.click()                                                                  # a badge filters to it, and says so
            expect(page.locator('#radioFoundContacts')).to_be_visible()                                # opened, though it was folded away
            banner = page.locator('#roFound .dc-record-filter-applied')
            expect(banner).to_be_visible()
            expect(banner).to_contain_text('Filter applied')
            expect(page.locator('#roFound [data-found]')).to_have_count(1)                           # everything else hidden
            expect(page.locator('#roMatched [data-matched="contacts"] [data-matched-field="name"]')).to_have_attribute('aria-pressed', 'true')
            expect(page.locator('#roMatched [data-matched="members"]')).to_be_visible()             # the panel still shows the whole search
            assert 'kind=contacts' in page.url and 'field=name' in page.url, 'The filter is not in the address: %s' % page.url
            banner.locator('[data-ro-filter-clear]').click()                                         # Clear filter
            expect(page.locator('#roFound .dc-record-filter-applied')).to_have_count(0)
            expect(page.locator('#roFound [data-found="members"]')).to_be_visible()
            members_badge = page.locator('#roMatched [data-matched="members"] .dc-record-panel-badge-heading')
            members_badge.click()                                                                   # a kind's badge
            expect(page.locator('#roFound [data-found]')).to_have_count(1)
            expect(page.locator('#roFound [data-found="members"]')).to_be_visible()
            page.locator('#roMatched [data-matched="members"] .dc-record-panel-badge-heading').click()   # the same badge again
            expect(page.locator('#roFound .dc-record-filter-applied')).to_have_count(0)
            page.locator('#roMatched [data-matched="members"] .dc-record-panel-badge-heading').click()
            expect(page.locator('#roFound .dc-record-filter-applied')).to_be_visible()
            with page.expect_response(lambda r: '/radio/search?' in r.url and 'kind=' not in r.url):
                page.locator('#roFindAll').fill(token + '  ')                                        # a new search takes it off
            expect(page.locator('#roFound .dc-record-filter-applied')).to_have_count(0)
            expect(page.locator('#roFound [data-found="contacts"]')).to_be_visible()
            panel_button = page.locator('[data-dc-record-panel]:visible')
            expect(panel_button).to_have_attribute('title', 'Hide panel')
            with_panel = page.locator('#roFound').bounding_box()
            panel_button.click()
            expect(panel).to_be_hidden()
            usual_width('#roFoundView', 'Search with its panel closed')                              # the page goes back to the usual width
            without_panel = page.locator('#roFound').bounding_box()
            assert abs(with_panel['x'] - without_panel['x']) < 1 and abs(with_panel['width'] - without_panel['width']) < 1, \
                'Opening the panel moved the list: %s vs %s' % (with_panel, without_panel)            # it sits in the margin
            page.set_viewport_size({'width': 1400, 'height': 1080})                                  # no room in the margin:
            panel_button.click()
            expect(panel).to_be_visible()
            list_beside_panel('#roFoundPanel', '#roFound', 'Search on a narrower screen')            # the page makes room instead
            panel_button.click()
            expect(panel).to_be_hidden()
            page.set_viewport_size({'width': 1920, 'height': 1080})
            page.reload()                                                                          # remembered
            expect(page.locator('#roFoundPanel')).to_be_hidden()
            page.locator('[data-dc-record-panel]:visible').click()
            expect(page.locator('#roFoundPanel')).to_be_visible()
            page.locator('#roFindAll').fill(token)
            expect(page.locator('#roMatched [data-matched="members"]')).to_be_visible()             # refreshed with the search
            visit('/radio/search?q=' + token)
            expect(page.locator('#roMatched [data-matched="members"]')).to_be_visible()
            # Cards give each field a line of its own, its name on one line (there is no other card layout).
            expect(page.locator('[data-dc-record-view="lines"]')).to_have_count(0)
            page.locator('[data-dc-record-view="cards"]:visible').click()
            cells = page.evaluate('''() => [...document.querySelector('#radioFoundMembers .dc-record-grid-row').querySelectorAll('.dc-record-grid-cell:not(.dc-record-grid-action):not(.dc-record-grid-count)')]
                .filter(c => c.offsetParent !== null && getComputedStyle(c).display !== 'none')
                .map(c => ({top: c.getBoundingClientRect().top, height: c.getBoundingClientRect().height,
                            wrap: getComputedStyle(c.querySelector('.dc-record-grid-value')).whiteSpace,
                            label: getComputedStyle(c.querySelector('.dc-record-grid-label')).whiteSpace}))''')
            assert len(cells) >= 3 and all(b['top'] >= a['top'] + a['height'] - 1 for a, b in zip(cells, cells[1:])), 'Cards: fields are not a line each: %s' % cells
            assert all(c['height'] < 32 and c['wrap'] == 'nowrap' and c['label'] == 'nowrap' for c in cells), 'Cards: a field runs past one line: %s' % cells
            page.locator('[data-dc-record-view="cards"]:visible').click()
            toggle_all = page.locator('[data-grp-toggle-all="radioSearch"]:visible')                 # myTimes' collapse / expand all
            expect(toggle_all).to_have_attribute('title', 'Collapse all kinds')
            toggle_all.click()
            for grid in ('#radioFoundMembers', '#radioFoundContacts', '#radioFoundVessels'):
                expect(page.locator(grid)).to_be_hidden()
            expect(toggle_all).to_have_attribute('title', 'Expand all kinds')
            expect(toggle_all.locator('i')).to_have_class('bi bi-chevron-double-down')
            toggle_all.click()
            for grid in ('#radioFoundMembers', '#radioFoundContacts', '#radioFoundVessels'):
                expect(page.locator(grid)).to_be_visible()
            expect(toggle_all).to_have_attribute('title', 'Collapse all kinds')
            expect(page.locator('#radioFoundContacts .dc-record-grid-row').filter(has_text='Verify Contact ' + token)).to_contain_text(member_no)   # held by
            expect(page.locator('#radioFoundContacts .dc-record-grid-row').filter(has_text='Verify Public Contact ' + token)).to_contain_text('PUBLIC-' + token)
            page.locator('#radioFoundMembers a[title^="Open member"]').first.click()               # a row opens its record
            page.wait_for_url(re.compile(r'/member/[0-9]+$'))
            visit('/logons')
            page.locator('a[href="/logons/new"]').click()
            expect(page.locator('#saveStatus')).to_have_text('Not saved')
            expect(page.locator('#ro-entry-pane .ro-entry-shell > .ro-primary-actions [data-save-record]')).to_be_visible()
            expect(page.locator('#ro-entry-pane .capture-row')).to_have_count(5)
            expect(page.locator('form form')).to_have_count(0)
            expect(page.locator('#f-callTime')).to_have_value('')
            expect(page.locator('#f-callTime')).to_have_class(re.compile('is-invalid'))
            save(400)                                   # the server refuses the minimum; nothing is created
            expect(page.locator('#saveStatus')).to_have_text('Not saved')
            expect(page).to_have_url(re.compile('/logons/new$'))
            expect(page.locator('#f-callTime')).to_have_class(re.compile('is-invalid'))
            before = len(writes)
            for name, value in first.items():
                page.locator('#f-' + name).fill(value)
            page.locator('[data-picker-target="callDay"]').evaluate(
                '(el, value) => {el.value=value; el.dispatchEvent(new Event("change", {bubbles:true}));}', fields['callDay'])
            page.locator('[data-now-for="callTime"]').click()           # a real click: sets now as 4-digit 24-hour
            expect(page.locator('#f-callTime')).to_have_value(re.compile(r'^([01][0-9]|2[0-3])[0-5][0-9]$'))
            page.locator('#f-callTime').fill(fields['callTime'])
            page.select_option('#f-channel', 'phone')                                             # how they logged on
            expect(page.locator('#f-channel option')).to_have_text(['—', 'Radio', 'Phone', 'In person'])
            expect(page.locator('[data-ro-tab="contact"], [data-ro-tab="identity"], [data-ro-tab="record"]')).to_have_count(0)
            page.wait_for_timeout(400)  # detect unwanted debounced autosave
            assert len(writes) == before, 'Typing wrote a record'
            expect(page.locator('#saveStatus')).to_have_text('Unsaved changes')
            expect(page.locator('#ro-entry-pane .is-invalid')).to_have_count(1)                # only POB, held back
            expect(page.locator('#f-pob')).to_have_class(re.compile('is-invalid'))
            dialogs = []
            def dismiss_leave(dialog):
                dialogs.append(dialog.type)
                dialog.dismiss()
            page.once('dialog', dismiss_leave)
            with page.expect_event('dialog'):
                page.locator('.navbar-brand[href="/logons"]').click(no_wait_after=True)
            expect(page.locator('#f-vesselName')).to_have_value(vessel)
            assert dialogs == ['beforeunload'], 'Unsaved changes did not warn'
            page.on('dialog', lambda dialog: dialog.accept())
            record = save()['id']
            page.wait_for_url(re.compile('/logon/%s(?:#.*)?$' % record))
            assert len(writes) == before + 1, 'First Save was not one batched write'
            for name, value in first.items():
                if name not in ('callDay', 'etaDay'):   # settled times read back 4-digit: 13:45 shows 1345
                    shown = {'callTime': value.replace(':', ''), 'eta': value.replace(':', ''), 'mobile': '0412 345 678'}.get(name, value)
                    expect(page.locator('#f-' + name)).to_have_value(shown)   # times 4-digit, mobile written 0412 345 678
            expect(page.locator('#ro-entry-pane .is-invalid')).to_have_count(1)                # only POB, held back
            expect(page.locator('#f-pob')).to_have_class(re.compile('is-invalid'))
            actions = page.locator('#ro-entry-pane .ro-entry-shell > .ro-primary-actions')
            expect(actions.locator('button.btn-warning[data-save-record]')).to_be_visible()   # yellow Save
            expect(actions.locator('form[action$="/accept"]')).to_have_count(0)                  # no Accept: saving complete logs on
            expect(page.locator('#f-pob')).to_have_class(re.compile('is-invalid'))             # still needed, so still a draft
            # Second operator saves first; stale browser must fail visibly.
            other = context.new_page()
            other.on('dialog', lambda dialog: dialog.accept())
            other.goto(URL + '/logon/%s' % record)
            other.locator('#f-destination').fill('Saved by second operator')
            with other.expect_response(lambda r: '/api/logon/' in r.url and not is_check(r.request)) as pending:
                other.locator('#saveRecord').click()
            assert pending.value.status == 200, pending.value.text()
            expect(other.locator('#saveStatus')).to_have_text('Saved')
            other.close()
            page.locator('#f-destination').fill('Stale overwrite')
            save(409)
            expect(page.locator('#stale')).to_be_visible()
            page.reload()
            expect(page.locator('#f-destination')).to_have_value('Saved by second operator')
            visit('/logons?status=draft&day=' + today + '&q=' + vessel)
            expect(page.locator('[data-record="%s"]' % record)).to_have_count(1)
            row = page.locator('[data-record="%s"]' % record)
            expect(row.get_by_role('img', name='Draft', exact=True)).to_be_visible()
            expect(row).to_have_css('background-color', 'rgba(253, 126, 20, 0.1)')      # drafts are tinted orange
            expect(row.locator('[data-column="vesselName"]')).to_contain_text(vessel)          # its own column
            expect(row.locator('[data-column="day"]')).to_contain_text('/%02d' % (date.today().year % 100))
            expect(row.locator('[data-column="time"]')).to_contain_text('1345')            # typed 13:45, always 4-digit
            expect(row.locator('[data-column="returnTime"]')).to_contain_text('1700')
            expect(row.locator('[data-column="member"]')).to_contain_text('Public')             # nothing picked: a public user
            expect(row.locator('[data-column="member"]').get_by_role('img', name='Public user', exact=True)).to_be_visible()
            expect(page.locator('.dc-record-grid-head')).to_contain_text('👤 Member No.')       # symbols taught in the headings
            # The toolbar swaps the list in place through the shared htmx: no Apply button, no reload.
            expect(page.get_by_role('button', name='Apply', exact=True)).to_have_count(0)
            def rows_for(**want):
                # A /logons/rows request whose query holds exactly these values, whatever their order.
                def match(response):
                    parts = urlsplit(response.url)
                    query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
                    return parts.path == '/logons/rows' and all(query.get(k) == v for k, v in want.items())
                return match
            with page.expect_response(rows_for(q='NO-MATCH-' + token)):
                page.locator('#roSearch').fill('NO-MATCH-' + token)
            expect(page.locator('#radioRecords')).to_have_text('0 drafts')
            with page.expect_response(rows_for(q='', status='draft')):
                page.get_by_role('button', name='Reset search', exact=True).click()
            expect(page.locator('#roSearch')).to_have_value('')
            expect(page.locator('#roStatus')).to_have_value('draft')
            expect(row).to_have_count(1)
            with page.expect_response(rows_for(q=vessel)):
                page.locator('#roSearch').fill(vessel)
            expect(page).to_have_url(re.compile(r'/logons\?.*q=' + vessel))
            # The reported bug: choosing a status must change the list straight away.
            with page.expect_response(rows_for(status='loggedon', q=vessel)):
                page.select_option('#roStatus', 'loggedon')
            expect(page.locator('#radioRecords')).to_have_text('0 logged on')
            expect(page).to_have_url(re.compile(r'/logons\?.*status=loggedon'))
            with page.expect_response(rows_for(status='draft', q=vessel)):
                page.select_option('#roStatus', 'draft')
            with page.expect_response(rows_for(sort='due', q=vessel)):          # Due first swaps in place too
                page.select_option('#roSort', 'due')
            expect(page).to_have_url(re.compile(r'/logons\?.*sort=due'))
            with page.expect_response(rows_for(sort='newest', q=vessel)):
                page.select_option('#roSort', 'newest')
            expect(row.get_by_role('img', name='Draft', exact=True)).to_be_visible()
            page.reload()
            expect(page.locator('#roSearch')).to_have_value(vessel)
            expect(page.locator('#roStatus')).to_have_value('draft')
            expect(row).to_have_count(1)
            # A failed swap is shown, never a list that silently stops updating.
            failing = re.compile(r'/logons/rows\?')
            page.route(failing, lambda route: route.fulfill(status=500, body='verification failure'))
            with page.expect_response(rows_for(status='closed')):
                page.select_option('#roStatus', 'closed')
            expect(page.locator('#dcHtmxError')).to_contain_text('/logons/rows?')
            expect(page.locator('#dcHtmxError')).to_contain_text('HTTP 500')
            expect(row).to_have_count(1)
            page.unroute(failing)
            page.locator('#dcHtmxError button').click()
            expect(page.locator('#dcHtmxError')).to_be_hidden()
            # The 30s poll, on a fake clock, without waiting 30 real seconds (WAT-3, minimal).
            poll = context.new_page()
            poll.clock.install()
            poll.goto(URL + '/logons?status=draft&day=' + today + '&q=' + vessel)
            expect(poll.locator('[data-record="%s"]' % record)).to_have_count(1)
            with poll.expect_response(rows_for(q=vessel)):
                poll.clock.run_for(30000)
            expect(poll.locator('[data-record="%s"]' % record).get_by_role('img', name='Draft', exact=True)).to_be_visible()
            poll.close()
            # Review density with sparse and populated rows, like the owner's
            # i_like_this.png, rather than accepting a single tall record.
            fixtures = [
                dict(callDay=today, callTime='14:00', registration='SPARSE-' + token),
                dict(callDay=today, callTime='14:01', registration='VESSEL-' + token,
                     vesselName='The great white', length='4.2', hullColour='white', destination='Sandbank'),
                dict(first, callTime='14:02', memberNumber=member_no,
                     vesselName='A very long vessel name to exercise truncation and full phone values',
                     registration='FULL-' + token, destination='A long destination beyond the harbour entrance')]
            for fixture in fixtures:
                response = context.request.post(URL + '/logons/new', data={'fields': fixture})
                assert response.status == 200, response.text()
                layout_records.append(response.json()['id'])
            # The same panel on the log, Members and Public vessels: closed until opened, remembered, refreshed with the rows.
            for path, search_box, panel_id, gid, rows_id, answer in (('/logons', '#roSearch', '#roLogPanel', 'logons', '#roLiveRecords', '/logons/rows?'),
                                                                      ('/members', '#roMemberSearch', '#roMemberPanel', 'members', '#roMemberRows', '/members?'),
                                                                      ('/vessels', '#roVesselSearch', '#roVesselPanel', 'public', '#roVesselRows', '/vessels?')):
                visit(path)
                expect(page.locator(panel_id)).to_be_hidden()
                page.locator('[data-dc-record-panel]:visible').click()
                expect(page.locator(panel_id)).to_be_visible()
                with page.expect_response(lambda r: answer in r.url and 'q=' + token in r.url):          # the search's own answer
                    page.locator(search_box).fill(token)
                section = page.locator('%s [data-matched="%s"]' % (panel_id, gid))
                expect(section).to_be_visible()
                rows = page.locator('%s .dc-record-grid-row' % rows_id)
                expect(rows.first).to_be_visible()
                expect(section.locator('.dc-record-panel-badge-heading')).to_have_attribute('title', re.compile(r': %d$' % rows.count()))   # the panel counts the rows shown
                badge = section.locator('[data-matched-field]').first
                expect(badge).to_be_visible()
                assert badge.evaluate('b => b.tagName') == 'SPAN', 'A badge with nothing to open should be plain'
                page.reload()
                expect(page.locator(panel_id)).to_be_visible()
                page.locator('[data-dc-record-panel]:visible').click()                          # closed again for the next run
                expect(page.locator(panel_id)).to_be_hidden()
            # A draft shows what stops acceptance only as red boxes, cleared as they are typed into.
            visit('/logon/%s' % layout_records[0])
            expect(page.locator('#ro-entry-pane .ro-gate')).to_have_count(0)
            bottom = page.locator('#ro-entry-pane .ro-entry-shell > .ro-primary-actions')
            expect(bottom.locator('[data-save-record]')).to_be_visible()                 # Save, Accept, Discard in one row
            expect(page.locator('#ro-entry-pane textarea[name="reason"]')).to_be_visible()           # Reason above the buttons
            expect(bottom.get_by_role('button', name='Discard draft')).to_be_visible()
            expect(page.locator('.ro-status-now')).to_contain_text('📝')                       # its status, as on the log
            expect(page.locator('.ro-status-now')).to_contain_text('Draft')
            expect(page.locator('#f-pob')).to_have_class(re.compile('is-invalid'))
            expect(page.locator('#f-registration')).not_to_have_class(re.compile('is-invalid'))
            expect(page.locator('#f-callTime')).to_have_value('1400')
            expect(page.locator('#f-callDay')).to_have_value(re.compile(r'^\w{3} \d{1,2}/\d{1,2}/\d{2}$'))   # always with the year
            page.screenshot(path=str(ARTIFACTS / ('radio-draft-%s.png' % engine)))
            page.locator('#f-pob').fill('abc')          # red as soon as focus leaves, from the server's check
            expect(page.locator('#f-pob')).not_to_have_class(re.compile('is-invalid'))
            page.locator('#f-pob').press('Tab')
            expect(page.locator('#f-pob')).to_have_class(re.compile('is-invalid'))
            page.locator('#f-pob').fill('2')
            expect(page.locator('#f-pob')).not_to_have_class(re.compile('is-invalid'))
            page.locator('#f-pob').press('Tab')
            page.locator('#f-callTime').fill('soon')
            page.locator('#f-callTime').press('Tab')
            expect(page.locator('#f-callTime')).to_have_class(re.compile('is-invalid'))
            expect(page.locator('#f-pob')).not_to_have_class(re.compile('is-invalid'))
            expect(page.locator('#f-destination')).to_have_class(re.compile('is-invalid'))
            expect(page.locator('#saveStatus')).to_have_text('Unsaved changes')   # checking wrote nothing
            expect(page.locator('#f-vesselName')).to_have_class(re.compile('is-invalid'))   # one ID so far: still red
            expect(page.locator('#f-memberNumber')).not_to_be_editable()                         # set only by picking a member
            page.locator('#roPickMember').click()
            page.locator('#spInput').fill('m99999')                                               # heard, but not a member
            page.locator('#spFilter [data-create]').click()                                       # Not a member: note it
            expect(page.locator('#f-notes')).to_have_value('Member No. heard: m99999 (no such member)')   # kept in Notes (CAP-24)
            expect(page.locator('#f-memberNumber')).to_have_value('')
            page.locator('#f-vesselName').fill('Heard boat')                                      # Vessel Name heard, no member
            page.locator('#f-vesselName').press('Tab')
            expect(page.locator('#f-memberNumber')).to_have_class(re.compile(r'\bro-hint\b'))  # orange: worth asking for
            expect(page.locator('#f-memberNumber')).not_to_have_class(re.compile('is-invalid'))
            expect(page.locator('#f-memberNumber')).to_have_css('border-top-color', 'rgb(253, 126, 20)')
            page.locator('#roPickMember').click()
            page.locator('#spInput').fill(token)
            pick(member_no)
            page.locator('#spFilter [data-skip]').click()                                         # No vessel
            expect(page.locator('#f-vesselName')).to_have_value('')                               # a member with no vessel has none
            expect(page.locator('#f-registration')).not_to_be_editable()
            expect(page.locator('#roWhoNow [data-ro-pick-vessel]')).to_be_visible()
            page.locator('#roWhoNow [data-ro-clear="member"]').click()
            page.locator('#f-mobile').fill('041234567')                                    # 9 digits: red on leaving
            page.locator('#f-mobile').press('Tab')
            expect(page.locator('#f-mobile')).to_have_class(re.compile('is-invalid'))
            page.locator('#f-mobile').fill('0412 345 678')
            page.locator('#f-mobile').press('Tab')
            expect(page.locator('#f-mobile')).not_to_have_class(re.compile('is-invalid'))
            visit('/logon/%s' % layout_records[1])                                           # rego of a public vessel, no member
            expect(page.locator('#roWhoNow [data-who="public"]')).to_be_visible()
            expect(page.locator('#roWhoNow [data-who="vessel"]')).to_contain_text('PUBLIC-' + token)
            visit('/logons?status=draft&day=' + today + '&q=' + token)
            expect(page.locator('.dc-record-grid-row')).to_have_count(4)
            expect(page.locator('[data-record="%s"] [data-column="member"]' % layout_records[1]).get_by_role(
                'img', name='Public user', exact=True)).to_be_visible()
            expect(page.locator('#appNavbarControls #roFilters')).to_have_count(1)            # the filters ride in the navbar
            for width in (2560, 1920, 1328, 1280, 1190, 1184, 1024, 960, 900, 768, 576, 390, 320):
                page.set_viewport_size({'width': width, 'height': 800})
                expect(page.locator('table')).to_have_count(0)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Overflow at %spx' % width
                metrics = page.locator('#radioRecords').evaluate("""el => {
                    const rows = [...el.querySelectorAll('.dc-record-grid-row')];
                    const head = el.querySelector('.dc-record-grid-head');
                    const mobile = getComputedStyle(head).display === 'none';
                    const nodes = [el, ...el.querySelectorAll('.dc-record-grid-row, .dc-record-grid-cell')];
                    if (mobile) nodes.push(...el.querySelectorAll('.dc-record-grid-value'));
                    // A value cut off with … on purpose (cards, rows) hides its overflow; anything else spilling is a fault.
                    const spills = n => n.clientWidth && n.scrollWidth > n.clientWidth + 1 && getComputedStyle(n).overflowX === 'visible';
                    // A word is never split across lines (record_grid's words, no overflow-wrap: anywhere).
                    const split = [];
                    for (const v of el.querySelectorAll('.dc-record-grid-value, .dc-record-grid-head > span')) {
                        const walk = document.createTreeWalker(v, NodeFilter.SHOW_TEXT);
                        for (let t; (t = walk.nextNode());) for (const w of t.data.matchAll(/\S+/g)) {
                            const r = document.createRange(); r.setStart(t, w.index); r.setEnd(t, w.index + w[0].length);
                            if (new Set([...r.getClientRects()].map(x => Math.round(x.top))).size > 1) split.push(w[0]);
                        }
                    }
                    // Cards instead of rows only because the rows' columns, each at least its longest word, do not fit.
                    const stacked = el.classList.contains('dc-record-grid-stacked');
                    let rowsWouldOverflow = null;
                    if (stacked) {
                        el.classList.remove('dc-record-grid-stacked');
                        rowsWouldOverflow = el.scrollWidth > el.clientWidth + 1;
                        el.classList.add('dc-record-grid-stacked');
                    }
                    // A column name is one line: a row heading's words, or a card's label's words, all on the same line.
                    const names = mobile ? [...el.querySelectorAll('.dc-record-grid-row:first-of-type .dc-record-grid-label')] : [...head.children];
                    const twoLineNames = names.filter(n => new Set([...n.querySelectorAll('.dc-record-word')]
                        .map(w => Math.round(w.getBoundingClientRect().top))).size > 1).map(n => n.textContent.trim());
                    return {mobile, stacked, rowsWouldOverflow, split, twoLineNames, grid: rows.every(r => getComputedStyle(r).display === 'grid'),
                        heights: rows.map(r => r.getBoundingClientRect().height),
                        overflow: nodes.some(spills),
                        lines: !mobile || [...el.querySelectorAll('.dc-record-grid-value')].every(v => getComputedStyle(v).whiteSpace === 'nowrap'),
                        visibleBlanks: [...el.querySelectorAll('.dc-record-grid-blank')].some(n => n.getBoundingClientRect().height > 0),
                        aligned: rows.every(r => [...r.children].every((cell, i) =>
                            Math.abs(cell.getBoundingClientRect().left - head.children[i].getBoundingClientRect().left) < 3))};
                }""")
                assert metrics['grid'], 'Shared grid stylesheet is missing: %s' % metrics
                assert not metrics['overflow'], 'List/cell overflow at %spx: %s' % (width, metrics)
                assert not metrics['split'], 'Words split across lines at %spx: %s' % (width, metrics['split'])
                assert not metrics['twoLineNames'], 'Column names on two lines at %spx: %s' % (width, metrics['twoLineNames'])
                if width >= 1328:
                    assert not metrics['mobile'], 'Desktop unexpectedly switched to cards at %spx' % width
                if width >= 768 and not metrics['stacked']:
                    assert not metrics['mobile'], 'Tablet switched to cards without the rows overflowing at %spx' % width
                    # Row heights are not capped here: the table opens with Paragraphs on, so long values wrap.
                    assert metrics['aligned'], 'Headers and row columns do not align at %spx' % width
                elif width >= 768:
                    assert metrics['rowsWouldOverflow'], 'Cards chosen at %spx although the rows fit: %s' % (width, metrics)
                    assert metrics['lines'], 'Cards for rows that did not fit are not one line per field at %spx' % width
                else:
                    assert metrics['mobile'] and not metrics['visibleBlanks'], 'Phone layout: %s' % metrics
                    assert metrics['lines'], 'Phone cards are not one line per field by default at %spx' % width
                assert page.locator('.dc-record-wide').evaluate('el => el.getBoundingClientRect().width <= 1920'), 'Width cap'
                expect(row.locator('[data-column="member"]')).to_be_visible()
                if width >= 1328:                       # dates and times are never cut off on a desktop
                    cut = page.locator('#radioRecords').evaluate("""el => [...el.querySelectorAll(
                        '[data-column="day"] .dc-record-grid-value, [data-column="returnDay"] .dc-record-grid-value, '
                        + '[data-column="time"] .dc-record-grid-value, [data-column="returnTime"] .dc-record-grid-value')]
                        .filter(v => v.scrollWidth > v.clientWidth + 1).map(v => v.textContent)""")
                    assert not cut, 'Date/time cut off at %spx: %s' % (width, cut)
                if width == 390:                        # a list longer than the screen: scrolled to the end, the filters are still there
                    # Bootstrap sets scroll-behavior: smooth; an instant scroll is where it says it is when read.
                    page.evaluate("window.scrollTo({top: document.documentElement.scrollHeight, behavior: 'instant'})")
                    assert page.evaluate('window.scrollY') > 0, 'The 390px list did not scroll; the check proves nothing'
                    expect(page.locator('#roStatus')).to_be_in_viewport()
                    expect(page.locator('#roSearch')).to_be_in_viewport()
                    page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
                    nav = page.locator('.navbar.fixed-top').evaluate('el => el.getBoundingClientRect().bottom')
                    first = page.locator('.dc-record-grid-row').first.evaluate('el => el.getBoundingClientRect().top')
                    assert first >= nav - 1, 'The first record starts under the navbar: %s < %s' % (first, nav)
                if width in (1920, 1328, 960, 900, 390):
                    page.screenshot(path=str(ARTIFACTS / ('radio-list-%s-%s.png' % (engine, width))), full_page=True)
            # Chosen views on a desktop: cards on one line, a line per field, wrapped rows; a refresh keeps them.
            page.set_viewport_size({'width': 1920, 'height': 1080})
            # The table opens with Paragraphs on: long values wrap in full rather than ending in an ellipsis.
            expect(page.locator('[data-dc-record-view="paragraphs"]')).to_have_attribute('aria-pressed', 'true')
            long_name = page.locator('#radioRecords [data-column="vesselName"] .dc-record-grid-value', has_text='A very long vessel name')
            expect(long_name).to_have_css('white-space', 'normal')
            assert long_name.evaluate('el => el.scrollWidth <= el.clientWidth + 1'), 'The long vessel name is still cut off'
            view = page.locator('#roRecordView')
            grid_rows = page.locator('#radioRecords .dc-record-grid-row')
            heights = lambda: grid_rows.evaluate_all('rows => rows.map(r => r.getBoundingClientRect().height)')
            page.locator('[data-dc-record-view="cards"]').click()
            expect(view).to_have_class(re.compile(r'\bdc-record-cards\b'))
            expect(page.locator('[data-dc-record-view="cards"]')).to_have_attribute('aria-pressed', 'true')
            expect(page.locator('#radioRecords .dc-record-grid-head')).to_be_hidden()
            expect(grid_rows.first).to_have_css('display', 'grid')                           # a line per field
            got = heights()
            assert min(got) > 64, 'Cards do not give each field a line: %s' % got
            names = grid_rows.first.evaluate('''row => [...row.querySelectorAll('.dc-record-grid-label')].filter(l => l.offsetParent)
                .map(l => ({text: l.textContent, lines: new Set([...l.querySelectorAll('.dc-record-word')].map(w => Math.round(w.getBoundingClientRect().top))).size}))''')
            assert names and all(n['lines'] == 1 for n in names), 'A column name on a card takes more than one line: %s' % names
            label = grid_rows.first.locator('[data-column="member"] .dc-record-grid-label')
            expect(label.locator('.dc-record-grid-symbol')).to_be_visible()                 # the symbol and the word
            expect(label.locator('.dc-record-grid-label-text')).to_have_css('position', 'static')
            expect(label).to_have_attribute('title', 'Member No.')
            page.screenshot(path=str(ARTIFACTS / ('radio-cards-%s.png' % engine)), full_page=True)
            gap = page.locator('[data-record="%s"] [data-column="pob"]' % layout_records[0])      # the sparse draft
            expect(gap.locator('.dc-record-grid-missing')).to_have_text('?')                     # symbol and ?, not gone
            expect(gap.locator('.dc-record-grid-symbol')).to_be_visible()
            with page.expect_response(rows_for(sort='oldest', q=token)):
                page.select_option('#roSort', 'oldest')
            expect(grid_rows).to_have_count(4)
            expect(view).to_have_class(re.compile(r'\bdc-record-cards\b'))
            expect(grid_rows.first).to_have_css('display', 'grid')                        # the swapped list is still cards
            page.locator('[data-dc-record-view="cards"]').click()                          # rows again, their own Paragraphs still on
            expect(page.locator('#radioRecords .dc-record-grid-head')).to_be_visible()
            expect(page.locator('[data-dc-record-view="paragraphs"]')).to_have_attribute('aria-pressed', 'true')
            value = page.locator('#radioRecords [data-column="destination"] .dc-record-grid-value').first
            expect(value).to_have_css('white-space', 'normal')
            page.locator('[data-dc-record-view="paragraphs"]').click()
            expect(value).to_have_css('white-space', 'nowrap')
            got = heights()                                                                 # Paragraphs off: the paper's one-line rows
            assert max(got) <= 36, 'Rows with Paragraphs off are not one line at 1920px: %s' % got
            expect(view).to_have_class('')                                                    # (Cards off, Paragraphs off)
            # Text size: A+ to 200% grows the list's text, remembered in this browser across a reload; reset returns to 100%.
            readout = page.locator('[data-dc-record-size-readout]')
            larger = page.get_by_role('button', name='Larger text')
            time_value = page.locator('#radioRecords [data-column="time"] .dc-record-grid-value').first
            font = lambda: time_value.evaluate('el => parseFloat(getComputedStyle(el).fontSize)')
            expect(readout).to_have_text('100%')
            expect(page.get_by_role('button', name='Reset text size')).to_be_disabled()
            base = font()
            for _ in range(4):
                larger.click()
            expect(readout).to_have_text('200%')
            expect(larger).to_be_disabled()
            assert abs(font() - 2 * base) < 0.6, 'Text did not double at 200%%: %s -> %s' % (base, font())
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Page overflows at 200%'
            page.locator('[data-dc-record-view="cards"]').click()
            page.screenshot(path=str(ARTIFACTS / ('radio-cards-200-%s.png' % engine)), full_page=True)
            spill = grid_rows.evaluate_all('''rows => rows.filter(r => {
                const b = r.querySelector('.dc-record-grid-action .btn').getBoundingClientRect(), c = r.getBoundingClientRect();
                return b.top < c.top - 1 || b.bottom > c.bottom + 1 || b.right > c.right + 1; }).length''')
            assert spill == 0, '%s open buttons spill out of their cards at 200%%' % spill
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Cards overflow at 200%'
            page.reload()
            expect(readout).to_have_text('200%')                                              # remembered
            assert abs(font() - 2 * base) < 0.6, 'Remembered size not applied after reload'
            page.get_by_role('button', name='Smaller text').click()
            expect(readout).to_have_text('175%')
            page.get_by_role('button', name='Reset text size').click()
            expect(readout).to_have_text('100%')
            assert abs(font() - base) < 0.3, 'Reset did not return to 100%'
            assert page.evaluate("Object.keys(localStorage).filter(k => k.indexOf('dc-record-size:') === 0).length") == 0
            visit('/logon/%s' % record)
            page.locator('[data-ro-tab="history"]').click()                                    # a tab puts #history in the address
            page.locator('[data-ro-tab="entry"]').click()
            page.locator('#f-pob').fill(fields['pob'])                                          # the last required value
            expect(page.locator('#saveStatus')).to_have_text('Unsaved changes')
            assert '#' in page.url, 'The tab should be in the address, as it is after any tab click'
            with page.expect_navigation():                                                       # a real reload, not a hash jump
                save()                                                                           # the save logs it on
            expect(page.locator('.ro-status-now')).to_contain_text('👀')                          # the same symbol and word as the log
            expect(page.locator('.ro-status-now')).to_contain_text('Logged on')
            expect(page.locator('#f-channel')).to_have_value('phone')                             # how they logged on, kept
            expect(page.locator('#roWhoNow [data-who]')).to_have_count(0)                         # nothing picked: typed as heard
            page.screenshot(path=str(ARTIFACTS / ('radio-logon-status-%s.png' % engine)), full_page=True)
            bottoms = page.locator('#ro-entry-pane .ro-entry-shell > .ro-primary-actions > *').evaluate_all('els => els.map(e => Math.round(e.getBoundingClientRect().bottom))')
            assert max(bottoms) - min(bottoms) < 12, 'Save, Note and Log off are not on one line: %s' % bottoms
            expect(page.locator('#capture textarea')).to_have_count(1)                            # one notes box on the log on
            expect(page.locator('#logoffNote')).to_have_count(0)
            expect(page.locator('label[for="f-notes"]')).to_have_text('🗒️ Notes')
            note_height = lambda: page.locator('#f-notes').evaluate('el => el.getBoundingClientRect().height')
            three = note_height()
            assert three >= 3 * 20, 'The Note box is not three lines tall: %spx' % three
            page.locator('#f-notes').fill('one\ntwo\nthree\nfour\nfive\nsix')
            expect(page.locator('#f-notes')).not_to_have_css('height', '%spx' % three)             # it grows with the text
            assert note_height() > three + 30, 'The Note box did not grow: %s -> %s' % (three, note_height())
            page.locator('#f-notes').fill('')
            expect(page.locator('#ro-entry-pane [placeholder]')).to_have_count(0)
            expect(page.locator('#ro-entry-pane .ro-entry-shell > .ro-primary-actions')).not_to_contain_text('Logged on and watched')
            expect(page.locator('#ro-entry-pane select[name="reason"]')).to_have_count(0)
            watching = True
            page.locator('#f-pob').fill('')                                                     # a log on cannot lose POB
            save(400)
            expect(page.locator('#saveStatus')).to_have_text('Not saved')
            expect(page.locator('#f-pob')).to_have_class(re.compile('is-invalid'))
            page.reload()
            expect(page.locator('#f-pob')).to_have_value(fields['pob'])                        # nothing was written
            visit('/logons?status=loggedon&day=' + today + '&q=' + vessel)
            expect(page.locator('[data-record="%s"]' % record)).to_have_count(1)
            expect(row.get_by_role('img', name='Logged on', exact=True)).to_be_visible()
            expect(row).to_have_css('background-color', 'rgba(25, 135, 84, 0.1)')         # logged on: faint green
            visit('/logon/%s' % record)
            page.locator('#f-notes').fill('Verification complete ' + token)                      # Log off saves Notes with it
            leave_warnings = []
            seen = lambda dialog: leave_warnings.append(dialog.type)          # the page's accept-all handler answers it
            page.on('dialog', seen)
            page.locator('button[form="logoffForm"]').click()
            box = page.locator('#qcConfirm')                                                    # asked first, naming the log on
            expect(box).to_be_visible()
            expect(page.locator('#qcTitle')).to_contain_text('Log off T-')
            expect(page.locator('#qcTitle')).to_contain_text(vessel)
            page.locator('#qcCancel').click()                                                   # Cancel: nothing happens
            expect(box).to_be_hidden()
            assert page.url.endswith('/logon/%s' % record) or '/logon/%s#' % record in page.url, page.url
            page.locator('button[form="logoffForm"]').click()
            page.locator('#qcOk').click()
            page.wait_for_url(re.compile('/logons$'))
            page.remove_listener('dialog', seen)
            assert leave_warnings == [], 'Log off with only Notes typed warned about unsaved work: %s' % leave_warnings
            closed = True
            visit('/logon/%s' % record)                                                          # logged off by mistake: Reopen
            page.locator('#reopenReason').fill('Logged off the wrong vessel ' + token)
            page.locator('button[form="reopenForm"]').click()
            expect(page.locator('#qcTitle')).to_contain_text('Reopen T-')
            page.locator('#qcOk').click()
            page.wait_for_url(re.compile('/logon/%s$' % record))
            expect(page.locator('.ro-status-now')).to_contain_text('Logged on')
            closed = False
            page.locator('button[form="logoffForm"]').click()                                   # and off again, for real
            page.locator('#qcOk').click()
            page.wait_for_url(re.compile('/logons$'))
            closed = True
            visit('/logons?status=closed&day=' + today + '&q=' + vessel)
            expect(page.locator('[data-record="%s"]' % record)).to_have_count(1)
            expect(row.get_by_role('img', name='Logged off', exact=True)).to_be_visible()
            expect(row).to_have_css('background-color', 'rgba(0, 0, 0, 0.3)')              # closed: near-black
            visit('/logon/%s' % record)
            expect(page.locator('#saveStatus')).to_have_text('Closed: read only')
            expect(page.locator('.ro-status-now')).to_contain_text('✅')
            expect(page.locator('.ro-status-now')).to_contain_text('Logged off')
            # History: quackit's LogOns_history in the shared viewer, the whole life of this record.
            page.locator('[data-ro-tab="history"]').click()
            history = page.locator('#ro-history-pane .dc-history')
            expect(history).to_be_visible()
            # The viewer's toolbar (search, sort, count) rides in the navbar, as on every quackit history page.
            expect(page.locator('#appNavbarControls [data-history-toolbar] [data-history-count]')).to_have_text(re.compile(r'^([4-9]|\d\d+) events$'))
            expect(history).to_contain_text('Saved by second operator')                         # the second operator's edit
            expect(history).to_contain_text('Going to')                                         # labelled, not the column name
            expect(history).to_contain_text('Logged on by')
            expect(history).to_contain_text('Verification complete ' + token)                   # the log off
            expect(history).to_contain_text('📝 draft')                                          # statuses with their symbols
            expect(history).to_contain_text('👀 loggedOn')
            expect(history).to_contain_text('✅ loggedOff')
            expect(history.locator('.dc-history-field', has_text='POB').first).to_contain_text('👥')   # fields with the log's symbols
            page.screenshot(path=str(ARTIFACTS / ('radio-history-%s.png' % engine)), full_page=True)
            widths = page.evaluate('''() => ({history: document.querySelector('#ro-history-pane .dc-history').getBoundingClientRect().width,
                                               form: document.querySelector('#capture').getBoundingClientRect().width || innerWidth,
                                               view: innerWidth,
                                               cap: getComputedStyle(document.querySelector('#ro-history-pane .mySpacing')).maxWidth})''')
            assert widths['history'] < widths['view'] - 300, 'History is not in the usual page width: %s' % widths
            # An overdue notice: raised by the real checker, brought onto an open page by the 30 s refresh (no reload),
            # and gone the moment its log on is logged off.
            overdue = context.request.post(URL + '/logons/new', data={'fields': dict(
                callDay=today, callTime='00:05', registration='OVERDUE-' + token, mobile='0499000111', pob='1',
                departurePoint='Marina', destination='Verification overdue', eta='12:00',
                etaDay=(date.today() - timedelta(days=1)).isoformat())})
            assert overdue.status == 200 and overdue.json()['accepted'], overdue.text()
            overdue_record = overdue.json()['id']
            visit('/logons')
            notice = page.locator('#roLiveAlerts .ro-alert', has=page.locator('a[href="/logon/%d"]' % overdue_record))
            expect(notice).to_be_visible(timeout=80000)
            # The title flashes every second; expect's own polling settles at 1 s and can keep landing on the plain half.
            page.wait_for_function("() => /^\\(\\d+\\) OVERDUE/.test(document.title)", polling=100, timeout=5000)
            visit('/logon/%d' % overdue_record)
            page.locator('button[form="logoffForm"]').click()
            page.locator('#qcOk').click()
            page.wait_for_url(re.compile('/logons$'))
            expect(page.locator('#roLiveAlerts a[href="/logon/%d"]' % overdue_record)).to_have_count(0)
            overdue_record = None
            assert not errors, '\n'.join(errors)
            print('PASS %s: explicit save, conflicts, search, cached-CSS upgrade, compact multi-row layouts, accept/logoff; fixture %s' % (engine, record))
        except Exception:
            page.screenshot(path=str(ARTIFACTS / ('radio-failure-%s.png' % engine)), full_page=True)
            raise
        finally:
            if record and not closed:
                action = 'logoff' if watching else 'discard'
                response = context.request.post(URL + '/logon/%s/%s' % (record, action),
                                                form={'reason': 'other' if watching else 'Verification cleanup'})
                if not response.ok:
                    print('Fixture %s cleanup failed: HTTP %s. Close it on port 80.' % (record, response.status))
            if overdue_record:
                response = context.request.post(URL + '/logon/%s/logoff' % overdue_record, form={'reason': 'other'})
                if not response.ok:
                    print('Fixture %s cleanup failed: HTTP %s. Log it off on port 80.' % (overdue_record, response.status))
            for fixture_id in layout_records:
                response = context.request.post(URL + '/logon/%s/discard' % fixture_id,
                                                form={'reason': 'Layout verification complete ' + token})
                if not response.ok:
                    print('Fixture %s cleanup failed: HTTP %s. Close it on port 80.' % (fixture_id, response.status))
            context.tracing.stop(path=str(ARTIFACTS / ('radio-trace-%s.zip' % engine)))
            browser.close()


if __name__ == '__main__':
    for engine in ('chromium', 'firefox'):
        main(engine)
