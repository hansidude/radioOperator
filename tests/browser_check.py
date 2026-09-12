"""A real browser against a running site: the checks the server tests cannot make.

Form nesting, autosave races and keyboard flow are invisible to a test client that posts
straight to an endpoint. Two defects got through that way, so this drives Chromium instead.

    pip install playwright && playwright install chromium
    RADIO_URL=http://localhost:8091 python3 tests/browser_check.py          # standalone, no login
    RADIO_URL=http://localhost:8080 RADIO_USER=x RADIO_PASS=y python3 tests/browser_check.py
"""
import os
import sys

from playwright.sync_api import sync_playwright

URL = os.environ.get('RADIO_URL', 'http://localhost:8091').rstrip('/')
USER, PASS = os.environ.get('RADIO_USER'), os.environ.get('RADIO_PASS')
FIELDS = [('callDay', 'today'), ('callTime', '1345'), ('memberNumber', '4471'), ('vesselName', 'BROWSER CHECK'),
          ('registration', 'AB123Q'), ('mobile', '0412 345 678'), ('pob', '2'), ('departurePoint', 'Marina'),
          ('destination', 'Facing Island'), ('etaDay', 'tomorrow'), ('eta', '0700')]
fails = []


def check(name, ok, detail=''):
    print(('  PASS  ' if ok else '  FAIL  ') + name + (' — ' + str(detail) if detail else ''))
    if not ok:
        fails.append(name)


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.on('dialog', lambda d: d.accept())
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        if USER:
            page.goto(URL + '/login')
            page.fill('input[name=username]', USER)
            page.fill('input[name=password]', PASS)
            page.click('button[type=submit], input[type=submit]')
            page.wait_for_load_state()
        page.goto(URL + '/logons')
        page.click('button:has-text("New log on")')
        page.wait_for_load_state()
        record = page.url.rsplit('/', 1)[-1]
        print('record #%s at %s' % (record, page.url))

        forms = page.evaluate("[...document.forms].map(f => f.id || f.getAttribute('action'))")
        check('the log off form exists in its own right', 'logoffForm' in forms, forms)
        owner = page.evaluate("(()=>{const b=[...document.querySelectorAll('button')]"
                              ".find(b=>/Log off now/.test(b.textContent)); return b && (b.form.id||b.form.getAttribute('action'));})()")
        check('the log off button belongs to it', owner == 'logoffForm', owner)

        # type the way an operator does: every field, one after another, without waiting
        for field, value in FIELDS:
            page.fill('#f-' + field, value)
            page.dispatch_event('#f-' + field, 'change')
        page.wait_for_function("document.getElementById('saveStatus').textContent.indexOf('Saving') < 0", timeout=15000)
        status = page.text_content('#saveStatus').strip()
        check('every field saved with no race', status.startswith('Saved'), status)
        check('the day box shows a date', page.input_value('#f-etaDay') == 'Sun 13/9' or '/' in page.input_value('#f-etaDay'),
              page.input_value('#f-etaDay'))
        check('the ETA reads as an instant', ':' in page.text_content('#b-eta'), page.text_content('#b-eta').strip())

        page.reload()
        stored = {f: page.input_value('#f-' + f) for f, _ in FIELDS}
        check('every value survived the reload', all(stored[f] for f, _ in FIELDS),
              [f for f, _ in FIELDS if not stored[f]])
        check('the queue shows this record', page.locator('tr[data-id="%s"]' % record).count() == 1)

        page.fill('#logoffNote', 'browser check')
        page.click('button:has-text("Log off now")')
        page.wait_for_load_state()
        check('log off leaves the open queue', page.locator('tr[data-id="%s"]' % record).count() == 0)
        check('and appears as logged off', 'browser check' in page.content())
        check('no javascript errors', not errors, errors)
        browser.close()
    print(('FAILED: ' + ', '.join(fails)) if fails else 'all passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
