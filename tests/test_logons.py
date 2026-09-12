"""The data layer on an isolated SQLite database: any subset, any order, nothing invented, nothing lost."""
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import logons as L
from server.sqlite import Connection, create_schema

T0 = datetime(2026, 9, 12, 14, 32)


class LogOns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / 'radio.sqlite'
        create_schema(path)
        self.conn = Connection(path)
        self.cur = self.conn.cursor()

    def eta(self, i, day, time, who='alice', at=T0):
        """A deadline needs both cells, so the tests set both, as an operator must."""
        L.set_field(self.cur, i, 'etaDay', day, who, at)
        return L.set_field(self.cur, i, 'eta', time, who, at)

    def test_empty_record_persists_owned_and_queued(self):            # AC-1, CAP-1, CAP-2
        i = L.create(self.cur, 'alice', 'unitA', T0)
        row = L.get(self.cur, i)
        self.assertEqual((row['captureStatus'], row['watchStatus'], row['unit']), ('draft', 'pending', 'unitA'))
        self.assertIsNone(row['eta']); self.assertIsNone(row['pob']); self.assertIsNone(row['destination'])   # CAP-4
        q = L.queue(self.cur, 'unitA', T0, 30)
        self.assertEqual([r['id'] for r in q], [i])
        self.assertEqual(q[0]['condition'], 'nodeadline')
        self.assertEqual(L.queue(self.cur, 'unitB', T0, 30), [])

    def test_any_order_any_subset_and_gaps_ranked(self):                # AC-2, AC-40, CAP-3, CAP-10, CAP-11
        i = L.create(self.cur, 'alice', '', T0)
        self.assertEqual([g['field'] for g in L.gaps(L.get(self.cur, i))][:5], ['etaDay', 'eta', 'pob', 'destination', 'departurePoint'])
        L.set_field(self.cur, i, 'vesselDetails', '6 m white Quintrex', 'alice', T0)
        L.set_field(self.cur, i, 'pob', '3', 'alice', T0)
        out = L.set_field(self.cur, i, 'destination', 'Tangalooma', 'alice', T0)
        self.assertEqual(out['version'], 3)
        gaps = [g['field'] for g in out['gaps']]
        self.assertNotIn('pob', gaps); self.assertNotIn('vesselDetails', gaps)
        self.assertEqual(gaps[:2], ['etaDay', 'eta'])
        self.assertEqual([g['cls'] for g in out['gaps']], sorted(g['cls'] for g in out['gaps']))

    def test_a_time_with_no_day_is_not_a_deadline(self):                # CAP-4, DAT-1, WAT-9
        i = L.create(self.cur, 'alice', '', T0)
        out = L.set_field(self.cur, i, 'eta', '1500', 'alice', T0)
        self.assertIsNone(out['when']); self.assertIn('No day', out['warning'])
        row = L.get(self.cur, i)
        self.assertEqual(row['etaRaw'], '1500')                         # kept as heard
        self.assertIsNone(row['eta']); self.assertIsNone(row['etaDate'])
        self.assertEqual(L.condition(row, T0, 30)[0], 'nodeadline')     # owned and visible, not counted down
        self.assertIn('etaDay', [g['field'] for g in L.gaps(row)])      # and the day is still being asked for
        out = L.set_field(self.cur, i, 'etaDay', 'today', 'alice', T0)
        self.assertEqual(out['when'], datetime(2026, 9, 12, 15, 0))     # the day cell makes it a deadline
        self.assertEqual(L.condition(L.get(self.cur, i), T0, 30)[0], 'approaching')

    def test_times_keep_raw_and_basis_and_drive_the_condition(self):    # AC-8, AC-21, AC-27, CAP-8, CAP-23
        i = L.create(self.cur, 'alice', '', T0)
        out = L.set_field(self.cur, i, 'eta', '+2h', 'alice', T0)
        self.assertEqual(out['when'], T0 + timedelta(hours=2))
        self.assertIn('entry time', out['basis'])
        row = L.get(self.cur, i)
        self.assertEqual((row['etaRaw'], row['eta']), ('+2h', T0 + timedelta(hours=2)))
        self.assertEqual(L.condition(row, T0, 30)[0], 'notdue')
        self.assertEqual(L.condition(row, T0 + timedelta(hours=1, minutes=40), 30)[0], 'approaching')
        self.assertEqual(L.condition(row, T0 + timedelta(hours=2), 30), ('overdue', 0))    # Draft + pending, still overdue
        out = L.set_field(self.cur, i, 'eta', '25:70', 'alice', T0)
        self.assertIsNone(out['when']); self.assertIn('Not understood', out['warning'])
        row = L.get(self.cur, i)
        self.assertEqual(row['etaRaw'], '25:70'); self.assertIsNone(row['eta'])
        self.assertEqual(L.condition(row, T0, 30)[0], 'nodeadline')
        out = L.set_field(self.cur, i, 'pob', 'about four', 'alice', T0)
        self.assertIn('kept as heard', out['warning'])
        self.assertEqual(L.get(self.cur, i)['pob'], 'about four')

    def test_return_day_and_time_are_separate_cells_read_together(self):     # DAT-6, REC-6, AC-48
        i = L.create(self.cur, 'alice', '', T0)
        out = self.eta(i, 'tomorrow', '0600')
        self.assertEqual(out['when'], datetime(2026, 9, 13, 6, 0)); self.assertIsNone(out['warning'])
        row = L.get(self.cur, i)
        self.assertEqual((row['etaDayRaw'], row['etaRaw'], row['eta']), ('tomorrow', '0600', datetime(2026, 9, 13, 6, 0)))
        out = L.set_field(self.cur, i, 'etaDay', 'mon', 'alice', T0)          # T0 is a Saturday
        self.assertEqual(out['when'], datetime(2026, 9, 14, 6, 0))
        out = L.set_field(self.cur, i, 'eta', '', 'alice', T0)                 # a day without a time is not a deadline
        self.assertIsNone(out['when']); self.assertIn('not a deadline', out['warning'])
        self.assertEqual(L.condition(L.get(self.cur, i), T0, 30)[0], 'nodeadline')
        out = L.set_field(self.cur, i, 'etaDay', 'someday', 'alice', T0)
        self.assertIn('Not understood', out['warning'])
        L.set_field(self.cur, i, 'callDay', '11/9', 'alice', T0); out = L.set_field(self.cur, i, 'callTime', '2300', 'alice', T0)
        self.assertEqual(out['when'], datetime(2026, 9, 11, 23, 0))

    def test_a_resolved_day_is_a_date_from_then_on(self):                # the point of storing the date
        i = L.create(self.cur, 'alice', '', T0)
        out = self.eta(i, 'tomorrow', '0600')
        self.assertEqual(out['when'], datetime(2026, 9, 13, 6, 0))
        row = L.get(self.cur, i)
        self.assertEqual(row['etaDate'], date(2026, 9, 13))
        self.assertEqual(L.box(row, 'etaDay'), 'Sun 13/9')               # the box shows the date, not the word
        self.assertEqual(row['etaDayRaw'], 'tomorrow')                   # the word is still what was heard
        # the next day, an unrelated edit must not re-read "tomorrow" as the day after
        out = L.set_field(self.cur, i, 'pob', '4', 'alice', T0 + timedelta(days=1))
        self.assertEqual(L.get(self.cur, i)['eta'], datetime(2026, 9, 13, 6, 0))
        out = L.set_field(self.cur, i, 'eta', '0700', 'alice', T0 + timedelta(days=1))
        self.assertEqual(out['when'], datetime(2026, 9, 13, 7, 0))
        # a row written before etaDate existed keeps the day its instant already settled on
        self.cur.execute('UPDATE LogOns SET etaDate = NULL WHERE id = %s', (i,))
        row = L.get(self.cur, i)
        self.assertEqual(L.box(row, 'etaDay'), 'Sun 13/9')
        out = L.set_field(self.cur, i, 'eta', '0800', 'alice', T0 + timedelta(days=3))
        self.assertEqual(out['when'], datetime(2026, 9, 13, 8, 0))       # not three days later
        # a date typed into the time cell fills the day cell
        j = L.create(self.cur, 'alice', '', T0)
        out = L.set_field(self.cur, j, 'eta', '14/9 0800', 'alice', T0)
        self.assertEqual(out['when'], datetime(2026, 9, 14, 8, 0))
        self.assertEqual(L.box(L.get(self.cur, j), 'etaDay'), 'Mon 14/9')

    def test_call_time_is_the_reference_once_known(self):               # REC-6
        i = L.create(self.cur, 'alice', '', T0)
        L.set_field(self.cur, i, 'callDay', 'today', 'alice', T0)
        L.set_field(self.cur, i, 'callTime', '1400', 'alice', T0)
        out = L.set_field(self.cur, i, 'eta', '+1h', 'alice', T0)
        self.assertEqual(out['when'], datetime(2026, 9, 12, 15, 0))
        self.assertIn('call time', out['basis'])

    def test_eta_before_departure_warns_and_saves(self):                # AC-4, CAP-5
        i = L.create(self.cur, 'alice', '', T0)
        L.set_field(self.cur, i, 'departureDay', 'today', 'alice', T0)
        L.set_field(self.cur, i, 'departureTime', '1600', 'alice', T0)
        out = self.eta(i, 'today', '1500')
        self.assertEqual(out['when'], datetime(2026, 9, 12, 15, 0))
        self.assertIn('before the departure', out['warning'])

    def test_identifiers_are_kept_as_heard_and_superseded_not_lost(self):   # DAT-5, IDV-3
        i = L.create(self.cur, 'alice', '', T0)
        L.set_field(self.cur, i, 'registration', 'ab 123 q', 'alice', T0)
        L.set_field(self.cur, i, 'registration', 'AB123Q', 'alice', T0)          # same normalized value, different raw: a new row
        L.set_field(self.cur, i, 'registration', 'AB128Q', 'bob', T0 + timedelta(minutes=1))
        rows = L.identifiers(self.cur, i)
        self.assertEqual([(r['raw'], r['normalized'], r['isActive'], r['source']) for r in rows],
                         [('ab 123 q', 'AB123Q', 0, 'call'), ('AB123Q', 'AB123Q', 0, 'corrected'), ('AB128Q', 'AB128Q', 1, 'corrected')])
        L.set_field(self.cur, i, 'mobile', '0412 345 678', 'alice', T0)
        self.assertEqual([r['normalized'] for r in L.identifiers(self.cur, i) if r['kind'] == 'mobile'], ['0412345678'])

    def test_queue_order_never_hides_overdue_or_unresolved(self):       # WAT-1
        a = L.create(self.cur, 'alice', '', T0); self.eta(a, 'today', '1800')
        b = L.create(self.cur, 'alice', '', T0); self.eta(b, 'today', '1400')
        c = L.create(self.cur, 'alice', '', T0)
        d = L.create(self.cur, 'alice', '', T0); self.eta(d, 'today', '1450')
        self.assertEqual([r['id'] for r in L.queue(self.cur, '', T0, 30)], [b, d, c, a])

    def test_stale_version_and_closed_records_refuse(self):             # CAP-22, WAT-7
        i = L.create(self.cur, 'alice', '', T0)
        L.set_field(self.cur, i, 'pob', '2', 'alice', T0, version=0)
        with self.assertRaises(L.Stale):
            L.set_field(self.cur, i, 'pob', '3', 'bob', T0, version=0)
        self.assertEqual(L.get(self.cur, i)['pob'], '2')
        L.accept(self.cur, i, 'alice', T0)
        with self.assertRaises(L.Refused):
            L.accept(self.cur, i, 'alice', T0)
        L.set_capture(self.cur, i, True, 'alice', T0)
        L.log_off(self.cur, i, 'alice', T0 + timedelta(hours=3), 'radio call, alongside')
        row = L.get(self.cur, i)
        self.assertEqual((row['watchStatus'], row['loggedOffNote']), ('loggedoff', 'radio call, alongside'))
        self.assertEqual(L.queue(self.cur, '', T0, 30), [])
        self.assertEqual([r['id'] for r in L.recent_closed(self.cur, '')], [i])
        with self.assertRaises(L.Refused):
            L.set_field(self.cur, i, 'pob', '4', 'alice', T0)
        with self.assertRaises(L.Refused):
            L.log_off(self.cur, i, 'alice', T0, '')

    def test_unknown_field_refused(self):
        i = L.create(self.cur, 'alice', '', T0)
        with self.assertRaises(L.Refused):
            L.set_field(self.cur, i, 'isActive', '0', 'alice', T0)


if __name__ == '__main__':
    unittest.main()
