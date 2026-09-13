"""Radio acceptance checks through Quackit. Run quackit's ./verify radio.
Creates a uniquely named sample record and closes/discards it, retaining history.
"""
from datetime import date, timedelta
import os
from pathlib import Path
import re
from uuid import uuid4
from playwright.sync_api import sync_playwright, expect

URL = os.environ.get('RADIO_URL', 'http://localhost:80').rstrip('/')
if URL not in ('http://localhost:80', 'http://host.docker.internal:80'):
    raise SystemExit('Use quackit/verify radio; only the port 80 dev stack is supported.')
ARTIFACTS = Path('/artifacts')


def main():
    token = uuid4().hex[:10].upper()
    vessel = 'VERIFY-' + token
    today = date.today().isoformat()
    fields = dict(callDay=today, callTime='13:45', memberNumber=token,
                  vesselName=vessel, registration=token, mobile='0412345678',
                  length='6', hullColour='white', make='Quintrex', model='610',
                  pob='2', departurePoint='Marina', destination='Verification bay',
                  etaDay=(date.today() + timedelta(days=1)).isoformat(), eta='17:00')
    record = None
    watching = closed = False
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        errors, writes = [], []
        context.on('page', lambda p: p.on('pageerror', lambda e: errors.append(e.stack)))
        page.on('pageerror', lambda e: errors.append(e.stack))
        page.on('request', lambda r: writes.append(r.url) if r.method == 'POST' and '/logon' in r.url else None)

        def visit(path):
            response = page.goto(URL + path)
            assert response and response.status == 200, 'GET %s: HTTP %s' % (path, response.status if response else 'none')
            assert '/login' not in page.url, 'Sample login failed'

        def save(status=200):
            with page.expect_response(lambda r: r.request.method == 'POST' and '/logon' in r.url) as pending:
                page.locator('#saveRecord').click()
            response = pending.value
            assert response.status == status, 'Save HTTP %s: %s' % (response.status, response.text()[:1000])
            if status == 200:
                expect(page.locator('#saveStatus')).to_have_text('Saved')
            return response.json()

        try:
            page.goto(URL + '/login')
            page.locator('input[name=username]').fill(os.environ.get('RADIO_USER', 'test'))
            page.locator('input[name=password]').fill(os.environ.get('RADIO_PASS', 'test'))
            page.locator('button[type=submit], input[type=submit]').first.click()
            visit('/logons')
            expect(page.locator('.navbar')).to_be_visible()
            page.locator('a[href="/logons/new"]').click()
            expect(page.locator('#saveStatus')).to_have_text('Not saved')
            expect(page.locator('#ro-entry-pane .capture-row')).to_have_count(5)
            expect(page.locator('form form')).to_have_count(0)
            expect(page.locator('#f-callTime')).to_have_value('')
            expect(page.locator('#f-callTime')).to_have_class(re.compile('is-invalid'))
            before = len(writes)
            page.locator('#saveRecord').click()
            expect(page.locator('#saveStatus')).to_have_text('Not saved')
            assert len(writes) == before, 'Invalid minimum attempted a write'
            for name, value in fields.items():
                page.locator('#f-' + name).fill(value)
            for name in ('callDay', 'callTime'):
                page.locator('[data-picker-target="%s"]' % name).evaluate(
                    '(el, value) => {el.value=value; el.dispatchEvent(new Event("change", {bubbles:true}));}', fields[name])
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
                if name not in ('callDay', 'etaDay'):
                    expect(page.locator('#f-' + name)).to_have_value(value)
            # Second operator saves first; stale browser must fail visibly.
            other = context.new_page()
            other.on('dialog', lambda dialog: dialog.accept())
            other.goto(URL + '/logon/%s' % record)
            other.locator('#f-destination').fill('Saved by second operator')
            with other.expect_response(lambda r: '/api/logon/' in r.url) as pending:
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
            for width in (1920, 900, 390):
                page.set_viewport_size({'width': width, 'height': 1080})
                expect(page.locator('table')).to_have_count(0)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), 'Overflow at %spx' % width
                page.screenshot(path=str(ARTIFACTS / ('radio-list-%s.png' % width)), full_page=True)
            page.set_viewport_size({'width': 1920, 'height': 1080})
            visit('/logon/%s' % record)
            page.locator('[data-ro-tab="identity"]').click()
            page.locator('#findBox').fill(vessel)
            expect(page.locator('#findHits')).to_contain_text(vessel)
            page.locator('[data-ro-tab="entry"]').click()
            page.locator('form[action="/logon/%s/accept"] button' % record).click()
            expect(page.locator('.ro-primary-actions')).to_contain_text('Logged on and watched')
            watching = True
            visit('/logons?status=loggedon&day=' + today + '&q=' + vessel)
            expect(page.locator('[data-record="%s"]' % record)).to_have_count(1)
            visit('/logon/%s' % record)
            page.locator('#logoffNote').fill('Verification complete ' + token)
            page.locator('button[form="logoffForm"]').click()
            page.wait_for_url(re.compile('/logons$'))
            closed = True
            visit('/logons?status=closed&day=' + today + '&q=' + vessel)
            expect(page.locator('[data-record="%s"]' % record)).to_have_count(1)
            visit('/logon/%s#record' % record)
            expect(page.locator('#saveStatus')).to_have_text('Closed: read only')
            expect(page.locator('#ro-record-pane')).to_contain_text('Verification complete ' + token)
            assert not errors, '\n'.join(errors)
            print('PASS: explicit save, persistence, stale conflict, navigation, search, layouts, accept/logoff; fixture %s' % record)
        except Exception:
            page.screenshot(path=str(ARTIFACTS / 'radio-failure.png'), full_page=True)
            raise
        finally:
            if record and not closed:
                action = 'logoff' if watching else 'discard'
                response = context.request.post(URL + '/logon/%s/%s' % (record, action),
                                                form={'reason': 'other' if watching else 'Verification cleanup', 'note': vessel})
                if not response.ok:
                    print('Fixture %s cleanup failed: HTTP %s. Close it on port 80.' % (record, response.status))
            context.tracing.stop(path=str(ARTIFACTS / 'radio-trace.zip'))
            browser.close()


if __name__ == '__main__':
    main()
