"""The checker: what becomes due, what stops being due, and whether anything is watching.

These run the sweep directly rather than the thread, because a timer is not the interesting part.
The interesting part is that an alert exists as a row before anyone looks at a page (ACC-5, WAT-3).
"""
import logging
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import logons as L
from server import watch as W
from server.sqlite import Connection, create_schema
from fixtures import known_members

logging.getLogger('radio.watch').setLevel(logging.CRITICAL)   # the warnings are the product, not test noise

T0 = datetime(2026, 9, 12, 14, 32)
FOLLOWUP = 15


class Watching(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / 'radio.sqlite'
        create_schema(path)
        self.conn = Connection(path)
        known_members(self.conn)
        self.cur = self.conn.cursor()
        self.told = []

    def notify(self, alert):
        self.told.append(alert)

    def sweep(self, now):
        return W.sweep(self.cur, now, FOLLOWUP, FOLLOWUP, self.notify)

    def accepted(self, at=T0, rego='AB123Q', member='4471', day='today', time='1800'):
        i = L.create(self.cur, 'alice', '', at)
        for field, value in (('registration', rego), ('memberNumber', member), ('pob', '3'),
                             ('departurePoint', 'Marina'), ('destination', 'Facing Island'),
                             ('etaDay', day), ('eta', time)):
            L.set_field(self.cur, i, field, value, 'alice', at)
        L.accept(self.cur, i, 'alice', at)
        return i

    def test_statuses_stored_under_the_old_words_are_renamed_once(self):   # owner, 2026-09-13
        on, off, draft = self.accepted(rego='AA1'), self.accepted(rego='BB2', member='2'), L.create(self.cur, 'alice', '', T0)
        L.log_off(self.cur, off, 'alice', T0, 'back')
        self.cur.execute("UPDATE LogOns SET watchStatus = 'watching' WHERE id = %s", (on,))       # as written before the rename
        self.cur.execute("UPDATE LogOns SET watchStatus = 'loggedoff' WHERE id = %s", (off,))
        self.assertEqual(L.rename_statuses(self.cur), 2)
        self.assertEqual([L.get(self.cur, i)['watchStatus'] for i in (on, off, draft)], ['loggedOn', 'loggedOff', 'draft'])
        self.assertEqual(L.rename_statuses(self.cur), 0)                                          # nothing left to do
        self.assertEqual(L.queue(self.cur, '', T0, 30)[0]['id'], on)                               # watched again under the new word

    def open_kinds(self):
        return sorted((a['kind'], a['logOnId']) for a in W.open_alerts(self.cur))

    # ---- drafts ----

    def test_a_draft_is_chased_after_the_interval(self):              # ACC-5
        i = L.create(self.cur, 'alice', '', T0)
        self.assertEqual(self.sweep(T0 + timedelta(minutes=FOLLOWUP - 1))['raised'], [])
        with patch.object(W.log, 'warning') as warning:
            out = self.sweep(T0 + timedelta(minutes=FOLLOWUP))
        warning.assert_not_called()
        self.assertEqual(len(out['raised']), 1)
        alert = W.open_alerts(self.cur)[0]
        self.assertEqual((alert['kind'], alert['logOnId']), ('draftfollowup', i))
        self.assertEqual(alert['dueAt'], T0 + timedelta(minutes=FOLLOWUP))
        self.assertEqual(self.told[0]['kind'], 'draftfollowup')
        self.assertIn('may believe they are logged on', self.told[0]['message'])

    def test_the_alert_exists_before_anyone_looks(self):              # the whole point
        L.create(self.cur, 'alice', '', T0)
        self.sweep(T0 + timedelta(minutes=FOLLOWUP))
        self.cur.execute('SELECT COUNT(*) AS n FROM Alerts WHERE resolvedAt IS NULL')
        self.assertEqual(self.cur.fetchone()['n'], 1)                 # a row, not a colour on a page

    def test_a_chased_draft_is_raised_again_until_it_is_seen(self):
        L.create(self.cur, 'alice', '', T0)
        self.sweep(T0 + timedelta(minutes=FOLLOWUP))
        self.assertEqual(len(self.told), 1)
        self.assertEqual(self.sweep(T0 + timedelta(minutes=FOLLOWUP + 1))['renotified'], [])
        again = self.sweep(T0 + timedelta(minutes=2 * FOLLOWUP))
        self.assertEqual(len(again['renotified']), 1)
        self.assertEqual(len(self.told), 2)
        alert = W.open_alerts(self.cur)[0]
        W.acknowledge(self.cur, alert['id'], 'alice', T0 + timedelta(minutes=2 * FOLLOWUP))
        self.sweep(T0 + timedelta(minutes=4 * FOLLOWUP))
        self.assertEqual(len(self.told), 2)                           # seen: stop putting it in front of them
        self.assertEqual(len(W.open_alerts(self.cur)), 1)             # but it is not resolved by being seen

    def test_accepting_or_discarding_the_draft_resolves_its_alert(self):
        i = L.create(self.cur, 'alice', '', T0)
        self.sweep(T0 + timedelta(minutes=FOLLOWUP))
        L.discard(self.cur, i, 'alice', T0, 'begun by mistake')
        out = self.sweep(T0 + timedelta(minutes=FOLLOWUP + 1))
        self.assertEqual(len(out['resolved']), 1)
        self.assertEqual(W.open_alerts(self.cur), [])
        self.cur.execute('SELECT resolvedReason FROM Alerts')
        self.assertEqual(self.cur.fetchone()['resolvedReason'], 'discarded')

    # ---- accepted log ons ----

    def test_an_overdue_log_on_is_raised_without_a_browser(self):     # WAT-3
        i = self.accepted(time='1500')
        self.assertEqual(self.sweep(T0 + timedelta(minutes=10))['raised'], [])
        out = self.sweep(datetime(2026, 9, 12, 15, 0))
        self.assertEqual(len(out['raised']), 1)
        self.assertEqual(self.open_kinds(), [('overdue', i)])
        self.assertEqual(self.told[-1]['kind'], 'overdue')

    def test_an_operators_change_settles_its_alerts_at_once(self):
        i = self.accepted(time='1500')
        j = self.accepted(rego='ZZ9', member='2', time='1500')
        self.sweep(datetime(2026, 9, 12, 15, 0))
        self.assertEqual(len(W.open_alerts(self.cur)), 2)
        self.assertEqual(W.settle(self.cur, i, datetime(2026, 9, 12, 15, 1), FOLLOWUP), [])       # still overdue: it stands
        L.log_off(self.cur, i, 'alice', datetime(2026, 9, 12, 15, 5), 'alongside')
        self.assertEqual(len(W.settle(self.cur, i, datetime(2026, 9, 12, 15, 5), FOLLOWUP)), 1)   # no waiting for a pass
        self.assertEqual([a['logOnId'] for a in W.open_alerts(self.cur)], [j])                     # only its own alert
        self.cur.execute('SELECT resolvedReason FROM Alerts WHERE logOnId = %s', (i,))
        self.assertEqual(self.cur.fetchone()['resolvedReason'], 'loggedOff')

    def test_logging_off_resolves_the_overdue(self):
        i = self.accepted(time='1500')
        self.sweep(datetime(2026, 9, 12, 15, 0))
        L.log_off(self.cur, i, 'alice', datetime(2026, 9, 12, 15, 5), 'alongside')
        self.sweep(datetime(2026, 9, 12, 15, 6))
        self.assertEqual(W.open_alerts(self.cur), [])

    def test_a_draft_is_never_raised_as_overdue(self):                # ACC-2
        i = L.create(self.cur, 'alice', '', T0)
        for field, value in (('etaDay', 'today'), ('eta', '1500')):
            L.set_field(self.cur, i, field, value, 'alice', T0)
        self.sweep(datetime(2026, 9, 12, 16, 0))
        self.assertEqual([k for k, _ in self.open_kinds()], ['draftfollowup'])

    def test_an_already_missed_deadline_is_found_on_the_next_pass(self):   # restart reconciliation
        i = self.accepted(time='1500')
        self.sweep(datetime(2026, 9, 13, 9, 0))                       # nothing ran for eighteen hours
        self.assertEqual(self.open_kinds(), [('overdue', i)])

    # ---- is anything watching ----

    def test_health_says_when_nothing_has_checked(self):              # WAT-3 monitoring health
        self.assertFalse(W.health(self.cur, T0, 180)['ok'])
        self.assertIn('Nothing has checked', W.health(self.cur, T0, 180)['message'])
        W.take_lease(self.cur, T0, 90, 'worker-1')
        W.mark_run(self.cur, T0)
        good = W.health(self.cur, T0 + timedelta(seconds=30), 180)
        self.assertTrue(good['ok'])
        self.assertIn('Checked', good['message'])
        stale = W.health(self.cur, T0 + timedelta(minutes=30), 180)
        self.assertFalse(stale['ok'])
        self.assertIn('Nothing may be watching', stale['message'])

    def test_only_one_worker_holds_the_lease(self):
        self.assertTrue(W.take_lease(self.cur, T0, 90, 'worker-1'))
        self.assertFalse(W.take_lease(self.cur, T0, 90, 'worker-2'))
        self.assertTrue(W.take_lease(self.cur, T0 + timedelta(seconds=30), 90, 'worker-1'))   # renewed by the holder
        self.assertTrue(W.take_lease(self.cur, T0 + timedelta(minutes=5), 90, 'worker-2'))    # taken over when it lapses

    def test_a_broken_delivery_channel_does_not_stop_the_watching(self):
        L.create(self.cur, 'alice', '', T0)
        def explode(alert):
            raise RuntimeError('the pager is unplugged')
        out = W.sweep(self.cur, T0 + timedelta(minutes=FOLLOWUP), FOLLOWUP, FOLLOWUP, explode)
        self.assertEqual(len(out['raised']), 1)
        self.assertEqual(len(W.open_alerts(self.cur)), 1)


if __name__ == '__main__':
    unittest.main()


class Delivery(unittest.TestCase):
    """Getting it in front of someone who is not looking at the screen, and knowing when that failed."""

    def test_nothing_configured_is_reported_rather_than_silent(self):
        from server import notify as N
        with patch.object(N.log, 'warning') as warning:
            sent, error = N.deliver({}, {'message': 'a vessel is overdue'})
        warning.assert_not_called()
        self.assertEqual(sent, [])
        self.assertIn('No delivery channel', error)

    def test_a_webhook_carries_the_alert(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        from server import notify as N
        got = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                got.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200)
                self.end_headers()

            def log_message(self, *a):
                pass

        server = HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = 'http://127.0.0.1:%d/alert' % server.server_address[1]
        try:
            sent, error = N.deliver({'webhook': url}, {'message': 'log on 12 is overdue', 'kind': 'overdue',
                                                       'at': datetime(2026, 9, 12, 15, 0)})
            self.assertEqual((sent, error), (['webhook'], None))
            self.assertEqual(got[0]['message'], 'log on 12 is overdue')
            self.assertEqual(got[0]['at'], '2026-09-12T15:00:00')
        finally:
            server.shutdown()

    def test_a_channel_that_is_not_answering_is_recorded_not_swallowed(self):
        from server import notify as N
        sent, error = N.deliver({'webhook': 'http://127.0.0.1:9/nothing-listens-here'},
                                {'message': 'a vessel is overdue'})
        self.assertEqual(sent, [])
        self.assertIn('webhook', error)

    def test_a_failed_delivery_shows_as_a_health_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'r.sqlite'
            create_schema(path)
            conn = Connection(path)
            cur = conn.cursor()
            L.create(cur, 'alice', '', T0)
            broken = lambda alert: ([], 'webhook: nobody is listening')
            W.sweep(cur, T0 + timedelta(minutes=FOLLOWUP), FOLLOWUP, FOLLOWUP, broken)
            alert = W.open_alerts(cur)[0]
            self.assertIsNone(alert['deliveredAt'])
            self.assertIn('nobody is listening', alert['deliveryError'])
            W.take_lease(cur, T0, 90, 'w')
            W.mark_run(cur, T0 + timedelta(minutes=FOLLOWUP))
            health = W.health(cur, T0 + timedelta(minutes=FOLLOWUP), 180)
            self.assertFalse(health['ok'])                       # the checker is fine; the pager is not
            self.assertIn('reached nobody', health['message'])
