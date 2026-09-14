"""The data layer on an isolated SQLite database: any subset, any order, nothing invented, nothing lost."""
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import logons as L
from server.sqlite import Connection, create_schema
from fixtures import known_members

T0 = datetime(2026, 9, 12, 14, 32)


class LogOns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / 'radio.sqlite'
        create_schema(path)
        self.conn = Connection(path)
        known_members(self.conn)
        self.cur = self.conn.cursor()

    def eta(self, i, day, time, who='alice', at=T0):
        """A deadline needs both cells, so the tests set both, as an operator must."""
        L.set_field(self.cur, i, 'etaDay', day, who, at)
        return L.set_field(self.cur, i, 'eta', time, who, at)

    def mandatory(self, i, rego='AB123Q', member='4471', day='today', time='1800', at=T0):
        """Everything ACC-1 asks for, so the record can be accepted."""
        for field, value in (('registration', rego), ('memberNumber', member), ('pob', '3'),
                             ('departurePoint', 'Marina'), ('destination', 'Facing Island')):
            L.set_field(self.cur, i, field, value, 'alice', at)
        self.eta(i, day, time, at=at)
        return i

    def accepted(self, at=T0, **kw):
        i = L.create(self.cur, 'alice', '', at)
        self.mandatory(i, at=at, **kw)
        L.accept(self.cur, i, 'alice', at)
        return i

    def test_an_empty_draft_persists_owned_and_is_not_watched(self):  # AC-1, CAP-1, CAP-2, ACC-2
        i = L.create(self.cur, 'alice', 'unitA', T0)
        row = L.get(self.cur, i)
        self.assertEqual((row['watchStatus'], row['unit']), ('draft', 'unitA'))
        self.assertIsNone(row['eta']); self.assertIsNone(row['pob']); self.assertIsNone(row['destination'])   # CAP-4
        self.assertEqual(L.queue(self.cur, 'unitA', T0, 30), [])          # a draft is not a watch
        d = L.drafts(self.cur, 'unitA', T0, 30)
        self.assertEqual([r['id'] for r in d], [i])
        self.assertEqual(d[0]['condition'], 'notwatched')
        self.assertEqual(L.drafts(self.cur, 'unitB', T0, 30), [])
        self.assertRegex(row['tripRef'], r'^T-\d{5}$')                                 # REC-9
        self.cur.execute("SELECT watchStatus FROM LogOns WHERE id = %s", (i,))     # written, not defaulted
        self.assertEqual(self.cur.fetchone()['watchStatus'], 'draft')
        self.assertEqual(L.reference(row), row['tripRef'])                            # read out as its Trip ID No.

    def test_a_record_left_in_a_state_this_version_forgot_is_chased(self):
        """An earlier version's state, or a hand-edited row, must not vanish: anything neither
        watched nor closed is a draft and gets chased."""
        i = L.create(self.cur, 'alice', '', T0)
        self.cur.execute("UPDATE LogOns SET watchStatus = 'pending' WHERE id = %s", (i,))
        self.assertEqual([r['id'] for r in L.drafts(self.cur, '', T0, 30)], [i])
        self.assertEqual(L.queue(self.cur, '', T0, 30), [])
        L.discard(self.cur, i, 'alice', T0, 'left by an earlier version')
        self.assertEqual(L.drafts(self.cur, '', T0, 30), [])

    def test_the_trip_id_runs_on_across_days_and_units(self):         # AC-56, REC-9
        a = L.create(self.cur, 'alice', '', T0)
        b = L.create(self.cur, 'alice', '', T0 + timedelta(hours=1))
        c = L.create(self.cur, 'alice', '', T0 + timedelta(days=1))
        other = L.create(self.cur, 'bob', 'unitB', T0)
        refs = [L.get(self.cur, x)['tripRef'] for x in (a, b, c, other)]
        self.assertEqual(refs, sorted(refs))
        self.assertEqual(len(set(refs)), 4)                              # never the same twice, whatever the day or unit
        self.assertEqual([int(r[2:]) for r in refs], list(range(int(refs[0][2:]), int(refs[0][2:]) + 4)))
        self.assertIsNone(L.get(self.cur, a)['dayNumber'])               # no daily number any more
        row = dict(L.get(self.cur, a), tripRef=None)
        self.assertEqual(L.reference(row), '#%d' % a)                    # a row from before trip references

    def test_acceptance_needs_the_mandatory_set(self):                 # AC-50, ACC-1, ACC-8
        i = L.create(self.cur, 'alice', '', T0)
        with self.assertRaises(L.Refused) as e:
            L.accept(self.cur, i, 'alice', T0)
        self.assertIn('Still needed', str(e.exception))
        self.assertEqual([m['field'] for m in L.missing(L.get(self.cur, i))],
                         ['identity', 'pob', 'departurePoint', 'destination', 'eta'])
        L.set_field(self.cur, i, 'registration', 'AB123Q', 'alice', T0)
        self.assertEqual(L.missing(L.get(self.cur, i))[0]['field'], 'identity')   # one identifier is not two
        L.set_field(self.cur, i, 'memberNumber', '4471', 'alice', T0)
        self.assertNotIn('identity', [m['field'] for m in L.missing(L.get(self.cur, i))])
        for field, value in (('pob', '3'), ('departurePoint', 'Marina'), ('destination', 'Facing Island')):
            L.set_field(self.cur, i, field, value, 'alice', T0)
        self.assertEqual([m['field'] for m in L.missing(L.get(self.cur, i))], ['eta'])
        L.set_field(self.cur, i, 'eta', '1800', 'alice', T0)            # a time with no day is no deadline
        self.assertEqual([m['field'] for m in L.missing(L.get(self.cur, i))], ['eta'])
        L.set_field(self.cur, i, 'etaDay', 'today', 'alice', T0)
        self.assertTrue(L.acceptable(L.get(self.cur, i)))
        L.accept(self.cur, i, 'alice', T0)
        row = L.get(self.cur, i)
        self.assertEqual((row['watchStatus'], row['acceptedBy']), ('loggedOn', 'alice'))
        self.assertEqual(row['acceptedAt'], T0)
        self.assertEqual([r['id'] for r in L.queue(self.cur, '', T0, 30)], [i])
        self.assertEqual(L.drafts(self.cur, '', T0, 30), [])
        with self.assertRaises(L.Refused):
            L.accept(self.cur, i, 'alice', T0)                          # already accepted

    def test_the_save_that_completes_the_mandatory_set_logs_it_on(self):   # ACC-3, spec v1.1
        base = {'callDay': 'today', 'callTime': '1400', 'registration': 'AB123Q', 'memberNumber': '4471',
                'pob': '3', 'departurePoint': 'Marina', 'destination': 'Facing Island', 'etaDay': 'today'}
        i = L.create(self.cur, 'alice', '', T0)
        out = L.save_fields(self.cur, i, base, 'alice', T0)                # no return time yet
        self.assertFalse(out['accepted'])
        self.assertEqual(L.get(self.cur, i)['watchStatus'], 'draft')
        out = L.save_fields(self.cur, i, dict(base, eta='1800'), 'bob', T0, version=out['version'])
        self.assertTrue(out['accepted'])
        row = L.get(self.cur, i)
        self.assertEqual((row['watchStatus'], row['acceptedBy'], row['acceptedAt'], row['version']), ('loggedOn', 'bob', T0, 2))
        new = L.create_saved(self.cur, dict(base, eta='1900', registration='NEW01', memberNumber='5000'), 'carol', '', T0)
        self.assertTrue(new['accepted'])                                   # complete on its very first save
        clash = L.create_saved(self.cur, dict(base, eta='1900'), 'carol', '', T0)
        self.assertFalse(clash['accepted'])                                # same vessel already out (ACC-6)
        self.assertEqual(L.get(self.cur, clash['id'])['watchStatus'], 'draft')

    def test_a_log_on_cannot_lose_its_mandatory_set(self):              # ACC-1, WAT-10
        i = self.accepted()
        with self.assertRaises(L.InvalidDraft) as e:
            L.save_fields(self.cur, i, {'pob': ''}, 'alice', T0)
        self.assertEqual(e.exception.fields, ['pob'])
        self.assertIn('POB', str(e.exception))
        with self.assertRaises(L.InvalidDraft) as e:
            L.save_fields(self.cur, i, {'eta': 'soon', 'registration': ''}, 'alice', T0)   # unreadable, and an ID short
        self.assertEqual(set(e.exception.fields), {'eta', 'registration', 'mobile', 'vesselName'})
        with self.assertRaises(L.InvalidDraft):
            L.set_field(self.cur, i, 'destination', '', 'alice', T0)                      # the single-field path too
        row = L.get(self.cur, i)
        self.assertEqual((row['watchStatus'], row['pob'], row['destination']), ('loggedOn', '3', 'Facing Island'))
        self.assertIn('pob', L.check_fields(self.cur, row, {'pob': ''})['red'])                    # red on leaving the box
        L.save_fields(self.cur, i, {'pob': '4', 'vesselName': 'Sea Dog'}, 'alice', T0)     # changing, not emptying, is fine
        self.assertEqual(L.get(self.cur, i)['pob'], '4')

    def test_a_mobile_is_ten_digits_written_0412_345_678(self):
        self.assertEqual(L.written_mobile('0412345678'), ('0412 345 678', False))
        self.assertEqual(L.written_mobile(' 04 1234 5678 '), ('0412 345 678', False))  # spaces typed anywhere
        self.assertEqual(L.written_mobile(''), ('', False))
        for heard in ('041234567', '04123456789', '+61412345678', '0412-345-678', 'O412345678'):
            self.assertEqual(L.written_mobile(heard), (heard, True), heard)             # kept as heard, and wrong
        base = {'callDay': '12/9', 'callTime': '1400', 'registration': 'AB1'}
        self.assertIn('mobile', L.check_fields(self.cur, L.blank(T0), dict(base, mobile='041234567'))['red'])
        self.assertNotIn('mobile', L.check_fields(self.cur, L.blank(T0), dict(base, mobile='0412345678'))['red'])
        i = L.create(self.cur, 'alice', '', T0)
        L.save_fields(self.cur, i, dict(base, mobile='0412345678'), 'alice', T0)
        row = L.get(self.cur, i)
        self.assertEqual(row['mobile'], '0412 345 678')                                  # saved in the written form
        self.assertEqual([r['id'] for r in L.records(self.cur, '', T0, 30, search='0412345678')], [i])
        row['mobile'] = '0412345678'                                                     # saved before the format
        self.assertEqual(L.box(row, 'mobile'), '0412 345 678')
        out = L.set_field(self.cur, i, 'mobile', '12345', 'alice', T0)
        self.assertTrue(out['invalid'])
        self.assertEqual(L.get(self.cur, i)['mobile'], '12345')

    def test_member_or_vessel_name_heard_turns_the_other_orange(self):   # the paper's "Member No. or Vessel Name"
        base = {'callDay': '12/9', 'callTime': '1400'}
        check = lambda **kw: L.check_fields(self.cur, L.blank(T0), dict(base, **kw))
        self.assertEqual(check(memberNumber='4471', registration='AB1')['orange'], ['vesselName'])
        self.assertEqual(check(vesselName='Sea Dog', registration='AB1')['orange'], ['memberNumber'])
        self.assertEqual(check(memberNumber='4471', vesselName='Sea Dog')['orange'], [])
        self.assertEqual(check(registration='AB1', mobile='0400')['orange'], [])       # neither heard: nothing to prompt
        one = check(memberNumber='4471')                                             # still short of two IDs: red wins
        self.assertIn('vesselName', one['red'])
        self.assertEqual(one['orange'], [])

    def test_due_first_is_the_watch_order_then_the_rest_newest_first(self):
        late = self.accepted(rego='LATE01', member='1001', time='2000')
        over = self.accepted(rego='OVER01', member='1002', time='1000')  # past at 1432
        soon = self.accepted(rego='SOON01', member='1003', time='1450')  # inside the 30 minute window
        older = L.create(self.cur, 'alice', '', T0 - timedelta(minutes=5))
        newer = L.create(self.cur, 'alice', '', T0 + timedelta(minutes=5))
        ids = [r['id'] for r in L.records(self.cur, '', T0, 30, sort='due')]
        self.assertEqual(ids, [over, soon, late, newer, older])
        self.assertEqual([r['id'] for r in L.queue(self.cur, '', T0, 30)], [over, soon, late])
        with self.assertRaises(L.Refused):
            L.records(self.cur, '', T0, 30, sort='sideways')

    def test_a_watch_starts_the_moment_it_is_accepted(self):            # AC-52, ACC-4
        i = L.create(self.cur, 'alice', '', T0)
        self.mandatory(i, time='0600')                                  # already past
        self.assertEqual(L.condition(L.get(self.cur, i), T0, 30)[0], 'notwatched')
        L.accept(self.cur, i, 'alice', T0)
        self.assertEqual(L.condition(L.get(self.cur, i), T0, 30)[0], 'overdue')
        self.assertEqual(L.queue(self.cur, '', T0, 30)[0]['condition'], 'overdue')

    def test_one_vessel_one_log_on(self):                               # AC-53, ACC-6
        first = self.accepted()
        second = L.create(self.cur, 'alice', '', T0)
        self.mandatory(second)
        with self.assertRaises(L.Refused) as e:
            L.accept(self.cur, second, 'alice', T0)
        self.assertIn('already logged on', str(e.exception))
        self.assertEqual(L.get(self.cur, second)['registration'], 'AB123Q')    # nothing captured is lost
        L.log_off(self.cur, first, 'alice', T0, 'back')
        L.accept(self.cur, second, 'alice', T0)                          # now the vessel is free
        self.assertEqual(L.get(self.cur, second)['watchStatus'], 'loggedOn')

    def test_a_draft_is_discarded_and_a_log_on_is_logged_off(self):      # AC-54, ACC-7
        d = L.create(self.cur, 'alice', '', T0)
        with self.assertRaises(L.Refused):
            L.discard(self.cur, d, 'alice', T0, '')                      # a reason is required
        L.discard(self.cur, d, 'alice', T0, 'hit New by mistake')
        row = L.get(self.cur, d)
        self.assertEqual((row['watchStatus'], row['discardReason']), ('discarded', 'hit New by mistake'))
        self.assertEqual(L.drafts(self.cur, '', T0, 30), [])
        with self.assertRaises(L.Refused):
            L.log_off(self.cur, d, 'alice', T0, 'x')
        i = self.accepted(rego='CD456R', member='9001')
        with self.assertRaises(L.Refused) as e:
            L.discard(self.cur, i, 'alice', T0, 'tidying up')
        self.assertIn('logged off, not discarded', str(e.exception))

    def test_log_off_records_whether_the_trip_happened(self):            # §3.3
        i = self.accepted()
        L.log_off(self.cur, i, 'alice', T0, 'never left the marina', reason='notdeparted')
        self.assertEqual(L.get(self.cur, i)['closeReason'], 'notdeparted')
        j = self.accepted(rego='CD456R', member='9001')
        with self.assertRaises(L.Refused):
            L.log_off(self.cur, j, 'alice', T0, 'x', reason='cancelled')

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

    def test_a_time_with_no_day_is_not_a_deadline(self):                # CAP-4, ACC-1
        i = L.create(self.cur, 'alice', '', T0)
        out = L.set_field(self.cur, i, 'eta', '1500', 'alice', T0)
        self.assertIsNone(out['when']); self.assertIsNone(out['warning']); self.assertFalse(out['invalid'])
        row = L.get(self.cur, i)
        self.assertEqual(row['etaRaw'], '1500')                         # kept as heard
        self.assertIsNone(row['eta']); self.assertIsNone(row['etaDate'])
        self.assertIn('eta', [m['field'] for m in L.missing(row)])      # so it cannot be accepted
        self.assertIn('etaDay', [g['field'] for g in L.gaps(row)])
        out = L.set_field(self.cur, i, 'etaDay', 'today', 'alice', T0)
        self.assertEqual(out['when'], datetime(2026, 9, 12, 15, 0))     # the day cell makes it a deadline
        self.assertNotIn('eta', [m['field'] for m in L.missing(L.get(self.cur, i))])

    def test_times_keep_raw_and_basis_and_drive_the_condition(self):    # AC-8, AC-21, AC-27, CAP-8, CAP-23
        i = L.create(self.cur, 'alice', '', T0)
        out = L.set_field(self.cur, i, 'eta', '+2h', 'alice', T0)
        self.assertEqual(out['when'], T0 + timedelta(hours=2))
        self.assertIn('entry time', out['basis'])
        row = L.get(self.cur, i)
        self.assertEqual((row['etaRaw'], row['eta']), ('+2h', T0 + timedelta(hours=2)))
        L.accept(self.cur, i, 'alice', T0) if L.acceptable(row) else None
        row = dict(L.get(self.cur, i), watchStatus='loggedOn')
        self.assertEqual(L.condition(row, T0, 30)[0], 'notdue')
        self.assertEqual(L.condition(row, T0 + timedelta(hours=1, minutes=40), 30)[0], 'approaching')
        self.assertEqual(L.condition(row, T0 + timedelta(hours=2), 30), ('overdue', 0))
        out = L.set_field(self.cur, i, 'eta', '25:70', 'alice', T0)
        self.assertIsNone(out['when']); self.assertIn('Not understood', out['warning']); self.assertTrue(out['invalid'])
        row = L.get(self.cur, i)
        self.assertEqual(row['etaRaw'], '25:70'); self.assertIsNone(row['eta'])
        self.assertIn('eta', [m['field'] for m in L.missing(row)])
        out = L.set_field(self.cur, i, 'pob', 'about four', 'alice', T0)
        self.assertIn('kept as heard', out['warning']); self.assertTrue(out['invalid'])
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
        self.assertIsNone(out['when']); self.assertIsNone(out['warning']); self.assertFalse(out['invalid'])
        self.assertIn('eta', [m['field'] for m in L.missing(L.get(self.cur, i))])
        out = L.set_field(self.cur, i, 'etaDay', 'someday', 'alice', T0)
        self.assertIn('Not understood', out['warning'])
        L.set_field(self.cur, i, 'callDay', '11/9', 'alice', T0); out = L.set_field(self.cur, i, 'callTime', '2300', 'alice', T0)
        self.assertEqual(out['when'], datetime(2026, 9, 11, 23, 0))

    def test_late_call_entry_is_recorded_without_rebuking_the_operator(self):  # REC-5, REC-6, AC-8
        i = L.create(self.cur, 'alice', '', T0)
        day = L.set_field(self.cur, i, 'callDay', '11/9', 'alice', T0)
        out = L.set_field(self.cur, i, 'callTime', '2300', 'alice', T0)
        self.assertIsNone(day['warning'])
        self.assertIsNone(out['warning'])
        self.assertFalse(day['invalid']); self.assertFalse(out['invalid'])
        self.assertEqual(out['when'], datetime(2026, 9, 11, 23, 0))

    def test_a_resolved_day_is_a_date_from_then_on(self):                # the point of storing the date
        i = L.create(self.cur, 'alice', '', T0)
        out = self.eta(i, 'tomorrow', '0600')
        self.assertEqual(out['when'], datetime(2026, 9, 13, 6, 0))
        row = L.get(self.cur, i)
        self.assertEqual(row['etaDate'], date(2026, 9, 13))
        self.assertEqual(L.box(row, 'etaDay'), 'Sun 13/9/26')               # the box shows the date, not the word
        self.assertEqual(L.box(row, 'eta'), '0600')                      # and the time as 4-digit 24-hour
        self.assertEqual([m['boxes'] for m in L.missing(row) if m['field'] == 'eta'], [])
        self.assertEqual(row['etaDayRaw'], 'tomorrow')                   # the word is still what was heard
        # the next day, an unrelated edit must not re-read "tomorrow" as the day after
        out = L.set_field(self.cur, i, 'pob', '4', 'alice', T0 + timedelta(days=1))
        self.assertEqual(L.get(self.cur, i)['eta'], datetime(2026, 9, 13, 6, 0))
        out = L.set_field(self.cur, i, 'eta', '0700', 'alice', T0 + timedelta(days=1))
        self.assertEqual(out['when'], datetime(2026, 9, 13, 7, 0))
        # a row written before etaDate existed keeps the day its instant already settled on
        self.cur.execute('UPDATE LogOns SET etaDate = NULL WHERE id = %s', (i,))
        row = L.get(self.cur, i)
        self.assertEqual(L.box(row, 'etaDay'), 'Sun 13/9/26')
        out = L.set_field(self.cur, i, 'eta', '0800', 'alice', T0 + timedelta(days=3))
        self.assertEqual(out['when'], datetime(2026, 9, 13, 8, 0))       # not three days later
        # a date typed into the time cell fills the day cell
        j = L.create(self.cur, 'alice', '', T0)
        out = L.set_field(self.cur, j, 'eta', '14/9 0800', 'alice', T0)
        self.assertEqual(out['when'], datetime(2026, 9, 14, 8, 0))
        self.assertEqual(L.box(L.get(self.cur, j), 'etaDay'), 'Mon 14/9/26')
        k = L.create(self.cur, 'alice', '', T0)                           # a time with no day yet: day box red, time as typed
        L.set_field(self.cur, k, 'eta', '3pm', 'alice', T0)
        row = L.get(self.cur, k)
        self.assertEqual(L.box(row, 'eta'), '1500')                       # understood, so 4-digit even with no day
        self.assertEqual([m['boxes'] for m in L.missing(row) if m['field'] == 'eta'], [['etaDay']])
        L.set_field(self.cur, k, 'etaDay', 'tomorrow', 'alice', T0)
        L.set_field(self.cur, k, 'eta', 'soon', 'alice', T0)             # a day but a time that cannot be read: time box red
        self.assertEqual([m['boxes'] for m in L.missing(L.get(self.cur, k)) if m['field'] == 'eta'], [['eta']])
        self.assertEqual(L.box(L.get(self.cur, k), 'eta'), 'soon')        # not understood: kept as heard (CAP-23)

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

    def test_queue_order_never_hides_overdue(self):                     # WAT-1
        a = self.accepted(rego='AA111A', member='1', time='1800')
        b = self.accepted(rego='BB222B', member='2', time='1400')
        c = self.accepted(rego='CC333C', member='3', time='1450')
        self.assertEqual([r['id'] for r in L.queue(self.cur, '', T0, 30)], [b, c, a])
        draft = L.create(self.cur, 'alice', '', T0)
        self.assertNotIn(draft, [r['id'] for r in L.queue(self.cur, '', T0, 30)])
        self.assertEqual([r['id'] for r in L.drafts(self.cur, '', T0, 30)], [draft])

    def test_stale_version_and_closed_records_refuse(self):             # CAP-22, WAT-7
        i = L.create(self.cur, 'alice', '', T0)
        L.set_field(self.cur, i, 'pob', '2', 'alice', T0, version=0)
        with self.assertRaises(L.Stale):
            L.set_field(self.cur, i, 'pob', '3', 'bob', T0, version=0)
        self.assertEqual(L.get(self.cur, i)['pob'], '2')
        self.mandatory(i)
        L.accept(self.cur, i, 'alice', T0)
        with self.assertRaises(L.Refused):
            L.accept(self.cur, i, 'alice', T0)
        L.log_off(self.cur, i, 'alice', T0 + timedelta(hours=3), 'radio call, alongside')
        row = L.get(self.cur, i)
        self.assertEqual((row['watchStatus'], row['notes'], row['loggedOffNote']), ('loggedOff', 'radio call, alongside', None))
        self.assertEqual(L.queue(self.cur, '', T0, 30), [])
        self.assertEqual([r['id'] for r in L.recent_closed(self.cur, '', T0, 30)], [i])
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
