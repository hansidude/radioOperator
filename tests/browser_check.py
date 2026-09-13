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
    record = None
    layout_records = []
    watching = closed = False
    with sync_playwright() as pw:
        browser = getattr(pw, engine).launch()
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        # Model an existing browser holding the old unversioned stylesheet. New
        # markup must request a new URL, rather than relying on a hard refresh.
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
            for name, value in fields.items():
                page.locator('#f-' + name).fill(value)
            page.locator('[data-picker-target="callDay"]').evaluate(
                '(el, value) => {el.value=value; el.dispatchEvent(new Event("change", {bubbles:true}));}', fields['callDay'])
            page.locator('[data-now-for="callTime"]').click()           # a real click: sets now as 4-digit 24-hour
            expect(page.locator('#f-callTime')).to_have_value(re.compile(r'^([01][0-9]|2[0-3])[0-5][0-9]$'))
            page.locator('#f-callTime').fill(fields['callTime'])
            page.locator('[data-ro-tab="contact"]').click()
            expect(page.locator('#captureContact')).to_be_visible()
            page.locator('[data-ro-tab="entry"]').click()
            page.wait_for_timeout(400)  # detect unwanted debounced autosave
            assert len(writes) == before, 'Typing or switching tabs wrote a record'
            expect(page.locator('#saveStatus')).to_have_text('Unsaved changes')
            expect(page.locator('#ro-entry-pane .is-invalid')).to_have_count(0)
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
            for name, value in fields.items():
                if name not in ('callDay', 'etaDay'):   # settled times read back 4-digit: 13:45 shows 1345
                    expect(page.locator('#f-' + name)).to_have_value(value.replace(':', '') if name in ('callTime', 'eta') else value)
            expect(page.locator('#ro-entry-pane .is-invalid')).to_have_count(0)
            actions = page.locator('#ro-entry-pane .ro-primary-actions')
            expect(actions.locator('button.btn-warning[data-save-record]')).to_be_visible()   # yellow Save left of Accept
            expect(actions.locator('form[action="/logon/%s/accept"] button' % record)).to_be_enabled()
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
            expect(row.get_by_role('img', name='Member number', exact=True)).to_be_visible()
            expect(row.get_by_role('img', name='Vessel name', exact=True)).to_be_visible()
            expect(row.locator('[data-column="identity"]')).to_contain_text(vessel)
            expect(row.locator('[data-column="day"]')).to_contain_text('/%02d' % (date.today().year % 100))
            expect(row.locator('[data-column="time"]')).to_contain_text('1345')            # typed 13:45, always 4-digit
            expect(row.locator('[data-column="returnTime"]')).to_contain_text('1700')
            expect(row.locator('[data-column="identity"]')).to_contain_text(token)
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
                dict(fields, callTime='14:02', memberNumber='7765',
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
            expect(bottom.locator('input[name="reason"]')).to_be_visible()
            expect(bottom.get_by_role('button', name='Discard draft')).to_be_visible()
            page.locator('[data-ro-tab="contact"]').click()
            expect(page.locator('#ro-contact-pane .ro-primary-actions [data-save-record]')).to_be_visible()
            page.locator('[data-ro-tab="entry"]').click()
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
            visit('/logons?status=draft&day=' + today + '&q=' + token)
            expect(page.locator('.dc-record-grid-row')).to_have_count(4)
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
                    assert max(metrics['heights']) <= 36, 'Desktop rows lost compact density: %s' % metrics
                    assert metrics['aligned'], 'Headers and row columns do not align at %spx' % width
                else:
                    assert metrics['mobile'] and not metrics['visibleBlanks'], 'Phone layout: %s' % metrics
                assert page.locator('.dc-record-wide').evaluate('el => el.getBoundingClientRect().width <= 1920'), 'Width cap'
                expect(row.locator('[data-column="identity"]')).to_be_visible()
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
            view = page.locator('#roRecordView')
            grid_rows = page.locator('#radioRecords .dc-record-grid-row')
            heights = lambda: grid_rows.evaluate_all('rows => rows.map(r => r.getBoundingClientRect().height)')
            page.locator('[data-dc-record-view="cards"]').click()
            expect(view).to_have_class(re.compile(r'\bdc-record-cards\b'))
            expect(page.locator('[data-dc-record-view="cards"]')).to_have_attribute('aria-pressed', 'true')
            expect(page.locator('#radioRecords .dc-record-grid-head')).to_be_hidden()
            expect(grid_rows.first).to_have_css('display', 'flex')
            got = heights()
            assert min(got) <= 40 and max(got) <= 64, 'Cards are not compact at 1920px: %s' % got
            page.screenshot(path=str(ARTIFACTS / ('radio-cards-%s.png' % engine)), full_page=True)
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
            page.locator('[data-dc-record-view="cards"]').click()                          # rows again, values wrapped
            expect(page.locator('#radioRecords .dc-record-grid-head')).to_be_visible()
            value = page.locator('#radioRecords [data-column="destination"] .dc-record-grid-value').first
            expect(value).to_have_css('white-space', 'normal')
            page.locator('[data-dc-record-view="paragraphs"]').click()
            expect(value).to_have_css('white-space', 'nowrap')
            expect(view).to_have_class('')
            visit('/logon/%s' % record)
            page.locator('[data-ro-tab="identity"]').click()
            page.locator('#findBox').fill(vessel)
            expect(page.locator('#findHits')).to_contain_text(vessel)
            page.locator('[data-ro-tab="entry"]').click()
            page.locator('form[action="/logon/%s/accept"] button' % record).click()
            expect(page.locator('#ro-entry-pane .ro-primary-actions')).to_contain_text('Logged on and watched')
            watching = True
            visit('/logons?status=loggedon&day=' + today + '&q=' + vessel)
            expect(page.locator('[data-record="%s"]' % record)).to_have_count(1)
            expect(row.get_by_role('img', name='Logged on', exact=True)).to_be_visible()
            expect(row).to_have_css('background-color', 'rgba(25, 135, 84, 0.1)')         # logged on: faint green
            visit('/logon/%s' % record)
            page.locator('#logoffNote').fill('Verification complete ' + token)
            page.locator('button[form="logoffForm"]').click()
            page.wait_for_url(re.compile('/logons$'))
            closed = True
            visit('/logons?status=closed&day=' + today + '&q=' + vessel)
            expect(page.locator('[data-record="%s"]' % record)).to_have_count(1)
            expect(row.get_by_role('img', name='Logged off', exact=True)).to_be_visible()
            expect(row).to_have_css('background-color', 'rgba(0, 0, 0, 0.3)')              # closed: near-black
            visit('/logon/%s#record' % record)
            expect(page.locator('#saveStatus')).to_have_text('Closed: read only')
            expect(page.locator('#ro-record-pane')).to_contain_text('Verification complete ' + token)
            assert not errors, '\n'.join(errors)
            print('PASS %s: explicit save, conflicts, search, cached-CSS upgrade, compact multi-row layouts, accept/logoff; fixture %s' % (engine, record))
        except Exception:
            page.screenshot(path=str(ARTIFACTS / ('radio-failure-%s.png' % engine)), full_page=True)
            raise
        finally:
            if record and not closed:
                action = 'logoff' if watching else 'discard'
                response = context.request.post(URL + '/logon/%s/%s' % (record, action),
                                                form={'reason': 'other' if watching else 'Verification cleanup', 'note': vessel})
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
