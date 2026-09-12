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
        page.wait_for_timeout(300)
        del errors[:]        # a host's own pages are not this app's business; judge only its pages
        page.click('button:has-text("New log on")')
        page.wait_for_load_state()
        record = page.url.rsplit('/', 1)[-1]
        print('record #%s at %s' % (record, page.url))

        check('a new record starts as a draft, not a log on',
              'This is a draft, not a log on' in page.content())
        check('the draft status is clear without watch jargon',
              'DRAFT' in page.content() and 'NOT WATCHED' not in page.content())
        check('the main view is the five operator rows', page.locator('#ro-entry-pane .capture-row').count() == 5)
        check('the watch queue starts on its own hidden tab', not page.locator('#queuePane').is_visible())
        size = float(page.locator('#f-callDay').evaluate("el => parseFloat(getComputedStyle(el).fontSize)"))
        check('the main entry text is large', size >= 18, '%spx' % size)
        check('the radio page uses cards and no tables', page.locator('table').count() == 0)
        page.click('[data-ro-tab="contact"]')
        check('supporting details have a focused tab', page.locator('#captureContact').is_visible())
        page.click('[data-ro-tab="watch"]')
        check('Watch shows the record collections', page.locator('#queuePane').is_visible())
        page.click('[data-ro-tab="entry"]')

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
        check('the drafts list shows this record, not the queue',
              page.locator('[data-draft="%s"]' % record).count() == 1
              and page.locator('[data-id="%s"]' % record).count() == 0)

        # section 7 through the real page: a host may own the bare /api/search, so this must not 404
        page.click('[data-ro-tab="identity"]')
        page.fill('#findBox', 'BROWSER')
        page.wait_for_selector('#findHits .ro-search-card', timeout=8000)
        rows = page.locator('#findHits .ro-search-card').all_inner_texts()
        check('the search box returns something', rows and 'Nothing matches' not in rows[0], rows[:2])
        check('and the verification panel is on the page', page.locator('.ro-verify').count() == 1)

        page.reload()
        check('the gate now says everything needed is here',
              'Everything needed is here' in page.content())
        page.click('[data-ro-tab="entry"]')
        page.click('button:has-text("Accept the log on")')
        page.wait_for_load_state()
        check('accepting puts it on the watch queue', page.locator('[data-id="%s"]' % record).count() == 1)
        check('and it reads as logged on', 'Logged on and watched' in page.content())
        check('and it is no longer a draft', page.locator('[data-draft="%s"]' % record).count() == 0)

        page.fill('#logoffNote', 'browser check')
        page.click('button:has-text("Log off")')
        page.wait_for_load_state()
        check('log off leaves the open queue', page.locator('[data-id="%s"]' % record).count() == 0)
        check('and appears as logged off', 'browser check' in page.content())
        check('no javascript errors on the log on pages', not errors, errors)
        browser.close()
    print(('FAILED: ' + ', '.join(fails)) if fails else 'all passed')
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
