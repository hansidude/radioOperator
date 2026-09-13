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
    fields = dict(callDay=today, callTime='13:45', memberNumber=token,
                  vesselName=vessel, registration=token, mobile='0412345678',
                  length='6', hullColour='white', make='Quintrex', model='610',
                  pob='2', departurePoint='Marina', destination='Verification bay',
                  etaDay=(date.today() + timedelta(days=1)).isoformat(), eta='17:00')
    first = {k: v for k, v in fields.items() if k != 'pob'}    # POB comes later: a complete save would log it on (ACC-3)
    record = None
    layout_records = []
    watching = closed = False
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
            expect(page.locator('.navbar a[href="/vessels"]')).to_have_count(0)               # no Public vessels button on Members
            page.locator('a[href="/members/new"]').click()
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
            member_no = page.locator('#ro-member-details .ro-section-title').inner_text().split()[-1]
            assert re.match(r'^m[0-9]{5}$', member_no), 'Member number is not mXXXXX: %r' % member_no
            expect(page.locator('#member-mobile')).to_have_value('0412 345 678')
            page.locator('[data-entity-tab="vessels"]').click()
            expect(page.locator('#ro-member-vessels')).to_be_visible()
            page.locator('#vessels-new-vesselName').fill(vessel)
            page.locator('#vessels-new-registration').fill(token)
            page.locator('#vessels-new-length').fill('six')                                  # not a number: red, on the same tab
            page.locator('#ro-member-vessels form#vessels-new button.btn-warning').click()
            expect(page.locator('#ro-member-vessels')).to_be_visible()
            expect(page.locator('#vessels-new-length')).to_have_class(re.compile('is-invalid'))
            page.locator('#vessels-new-length').fill('6')
            page.locator('#ro-member-vessels form#vessels-new button.btn-warning').click()
            page.wait_for_url(re.compile(r'/member/[0-9]+#vessels$'))
            expect(page.locator('#ro-member-vessels')).to_be_visible()                       # back on the tab it was on
            expect(page.locator('#ro-member-vessels input[name="vesselName"][value="%s"]' % vessel)).to_have_count(1)
            page.locator('[data-entity-tab="contacts"]').click()
            page.locator('#contacts-new-name').fill('Verify Contact ' + token)
            page.locator('#contacts-new-phone').fill('0499888777')
            page.locator('#ro-member-contacts form#contacts-new button.btn-warning').click()
            page.wait_for_url(re.compile(r'/member/[0-9]+#contacts$'))
            expect(page.locator('#ro-member-contacts input[name="name"][value="Verify Contact %s"]' % token)).to_have_count(1)
            page.locator('[data-entity-tab="details"]').click()
            page.locator('#member-email').fill('verify.changed@example.com')                  # one save, one history event
            page.locator('#ro-member-details button.btn-warning').click()
            page.wait_for_url(re.compile(r'/member/[0-9]+#details$'))
            expect(page.locator('#member-email')).to_have_value('verify.changed@example.com')
            for tab in ('trailers', 'cars', 'history'):
                page.locator('[data-entity-tab="%s"]' % tab).click()
                expect(page.locator('#ro-member-%s' % tab)).to_be_visible()
            expect(page.locator('#ro-member-history .dc-history')).to_contain_text('verify.changed@example.com')   # Members_history
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
            expect(page.locator('.navbar a[href="/members"]')).to_have_count(0)               # no Members button on Public vessels
            visit('/vessels/new')
            page.locator('#public-vesselName').fill('PUBLIC-' + token)
            page.locator('#public-registration').fill('VESSEL-' + token)
            page.locator('#public-ownerName').fill('Verify Public ' + token)
            page.locator('#public-ownerPhone').fill('0411222333')
            page.locator('#ro-vessel-details button.btn-warning').click()
            page.wait_for_url(re.compile('/vessel/[0-9]+$'))
            public_vessel = int(page.url.rsplit('/', 1)[1])
            visit('/vessels?q=' + token)
            expect(page.locator('#radioVessels .dc-record-grid-row')).to_have_count(1)
            fields['memberNumber'] = first['memberNumber'] = member_no
            visit('/logons')
            page.locator('a[href="/logons/new"]').click()
            expect(page.locator('#saveStatus')).to_have_text('Not saved')
            expect(page.locator('#ro-entry-pane .ro-primary-actions [data-save-record]')).to_be_visible()
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
                page.locator('.entity-nav-links a[href="/logons"]').click(no_wait_after=True)
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
            actions = page.locator('#ro-entry-pane .ro-primary-actions')
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
            expect(row.locator('[data-column="member"]')).to_contain_text(member_no)
            expect(row.locator('[data-column="member"]').get_by_role('img', name='Member', exact=True)).to_be_visible()
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
            # A draft shows what stops acceptance only as red boxes, cleared as they are typed into.
            visit('/logon/%s' % layout_records[0])
            expect(page.locator('#ro-entry-pane .ro-gate')).to_have_count(0)
            bottom = page.locator('#ro-entry-pane .ro-primary-actions')
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
            page.locator('#f-memberNumber').fill('m99999')                                 # not a member: left blank
            page.locator('#f-memberNumber').press('Tab')
            expect(page.locator('#f-memberNumber')).to_have_value('')
            expect(page.locator('#f-notes')).to_have_value('Member No. heard: m99999 (no such member)')   # kept in Notes (CAP-24)
            expect(page.locator('#saveStatus')).to_contain_text('m99999 is not a member')
            page.locator('#f-memberNumber').fill(member_no)                                # Member No. heard, Vessel Name empty
            page.locator('#f-memberNumber').press('Tab')
            expect(page.locator('#f-memberNumber')).to_have_value(member_no)
            expect(page.locator('#f-vesselName')).to_have_class(re.compile(r'\bro-hint\b'))    # orange, not red
            expect(page.locator('#f-vesselName')).not_to_have_class(re.compile('is-invalid'))
            expect(page.locator('#f-vesselName')).to_have_css('border-top-color', 'rgb(253, 126, 20)')
            page.locator('#f-mobile').fill('041234567')                                    # 9 digits: red on leaving
            page.locator('#f-mobile').press('Tab')
            expect(page.locator('#f-mobile')).to_have_class(re.compile('is-invalid'))
            page.locator('#f-mobile').fill('0412 345 678')
            page.locator('#f-mobile').press('Tab')
            expect(page.locator('#f-mobile')).not_to_have_class(re.compile('is-invalid'))
            visit('/logon/%s' % layout_records[1])                                           # rego of a public vessel, no member
            expect(page.locator('.ro-who[data-who="public"]')).to_have_attribute('href', '/vessel/%d' % public_vessel)
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
                    return {mobile, grid: rows.every(r => getComputedStyle(r).display === 'grid'),
                        heights: rows.map(r => r.getBoundingClientRect().height),
                        overflow: nodes.some(n => n.clientWidth && n.scrollWidth > n.clientWidth + 1),
                        visibleBlanks: [...el.querySelectorAll('.dc-record-grid-blank')].some(n => n.getBoundingClientRect().height > 0),
                        aligned: rows.every(r => [...r.children].every((cell, i) =>
                            Math.abs(cell.getBoundingClientRect().left - head.children[i].getBoundingClientRect().left) < 3))};
                }""")
                assert metrics['grid'], 'Shared grid stylesheet is missing: %s' % metrics
                assert not metrics['overflow'], 'List/cell overflow at %spx: %s' % (width, metrics)
                if width >= 768:
                    assert not metrics['mobile'], 'Desktop/tablet unexpectedly switched to cards at %spx' % width
                    # Row heights are not capped here: the table opens with Paragraphs on, so long values wrap.
                    assert metrics['aligned'], 'Headers and row columns do not align at %spx' % width
                else:
                    assert metrics['mobile'] and not metrics['visibleBlanks'], 'Phone layout: %s' % metrics
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
            expect(grid_rows.first).to_have_css('display', 'flex')
            expect(page.locator('[data-dc-record-view="paragraphs"]')).to_have_attribute('aria-pressed', 'false')   # cards keep their own: one line
            got = heights()
            assert min(got) <= 40 and max(got) <= 64, 'Cards are not compact at 1920px: %s' % got
            label = grid_rows.first.locator('[data-column="member"] .dc-record-grid-label')
            expect(label.locator('.dc-record-grid-symbol')).to_be_visible()                 # symbol instead of the word
            expect(label.locator('.dc-record-grid-label-text')).to_have_css('position', 'absolute')
            expect(label).to_have_attribute('title', 'Member No.')
            page.screenshot(path=str(ARTIFACTS / ('radio-cards-%s.png' % engine)), full_page=True)
            gap = page.locator('[data-record="%s"] [data-column="pob"]' % layout_records[0])      # the sparse draft
            expect(gap.locator('.dc-record-grid-missing')).to_have_text('?')                     # symbol and ?, not gone
            expect(gap.locator('.dc-record-grid-symbol')).to_be_visible()
            with page.expect_response(rows_for(sort='oldest', q=token)):
                page.select_option('#roSort', 'oldest')
            expect(grid_rows).to_have_count(4)
            expect(view).to_have_class(re.compile(r'\bdc-record-cards\b'))
            expect(grid_rows.first).to_have_css('display', 'flex')                        # the swapped list is still cards
            page.locator('[data-dc-record-view="paragraphs"]').click()
            expect(grid_rows.first).to_have_css('display', 'grid')
            got = heights()
            assert min(got) > 64, 'Paragraph cards do not give each field a line: %s' % got
            page.screenshot(path=str(ARTIFACTS / ('radio-paragraphs-%s.png' % engine)), full_page=True)
            page.locator('[data-dc-record-view="cards"]').click()                          # rows again, their own Paragraphs still on
            expect(page.locator('#radioRecords .dc-record-grid-head')).to_be_visible()
            expect(page.locator('[data-dc-record-view="paragraphs"]')).to_have_attribute('aria-pressed', 'true')
            value = page.locator('#radioRecords [data-column="destination"] .dc-record-grid-value').first
            expect(value).to_have_css('white-space', 'normal')
            page.locator('[data-dc-record-view="paragraphs"]').click()
            expect(value).to_have_css('white-space', 'nowrap')
            got = heights()                                                                 # Paragraphs off: the paper's one-line rows
            assert max(got) <= 36, 'Rows with Paragraphs off are not one line at 1920px: %s' % got
            expect(view).to_have_class('')
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
            expect(page.locator('.ro-who[data-who="member"]')).to_contain_text(member_no)       # tied to the member record
            expect(page.locator('.ro-who[data-who="member"]')).to_have_attribute('href', urlsplit(member_page).path)
            page.screenshot(path=str(ARTIFACTS / ('radio-logon-status-%s.png' % engine)), full_page=True)
            bottoms = page.locator('#ro-entry-pane .ro-primary-actions > *').evaluate_all('els => els.map(e => Math.round(e.getBoundingClientRect().bottom))')
            assert max(bottoms) - min(bottoms) < 12, 'Save, Note and Log off are not on one line: %s' % bottoms
            expect(page.locator('#ro-entry-pane textarea')).to_have_count(1)                       # one notes box
            expect(page.locator('label[for="f-notes"]')).to_have_text('Notes')
            note_height = lambda: page.locator('#f-notes').evaluate('el => el.getBoundingClientRect().height')
            three = note_height()
            assert three >= 3 * 20, 'The Note box is not three lines tall: %spx' % three
            page.locator('#f-notes').fill('one\ntwo\nthree\nfour\nfive\nsix')
            expect(page.locator('#f-notes')).not_to_have_css('height', '%spx' % three)             # it grows with the text
            assert note_height() > three + 30, 'The Note box did not grow: %s -> %s' % (three, note_height())
            page.locator('#f-notes').fill('')
            expect(page.locator('#ro-entry-pane [placeholder]')).to_have_count(0)
            expect(page.locator('#ro-entry-pane .ro-primary-actions')).not_to_contain_text('Logged on and watched')
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
            page.wait_for_url(re.compile('/logons$'))
            page.remove_listener('dialog', seen)
            assert leave_warnings == ['confirm'], 'Log off with only Notes typed warned about unsaved work: %s' % leave_warnings
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
