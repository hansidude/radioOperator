"""Times as operators say them: read against a reference, never guessed (CAP-4, CAP-8, CAP-23, REC-6)."""
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import times

REF = datetime(2026, 9, 12, 14, 32)    # a Saturday afternoon call
TODAY = date(2026, 9, 12)


class Times(unittest.TestCase):
    def when(self, raw, day=TODAY, label='today'):
        return times.parse(raw, REF, 'call time', day=day, day_label=label)

    def test_forms_operators_use(self):
        self.assertEqual(self.when('1500')['when'], datetime(2026, 9, 12, 15, 0))
        self.assertEqual(self.when('15:00')['when'], datetime(2026, 9, 12, 15, 0))
        self.assertEqual(self.when('3pm')['when'], datetime(2026, 9, 12, 15, 0))
        self.assertEqual(self.when('3:30 PM')['when'], datetime(2026, 9, 12, 15, 30))
        self.assertEqual(self.when('0730', date(2026, 9, 13), 'tomorrow')['when'], datetime(2026, 9, 13, 7, 30))
        self.assertEqual(self.when('12am', date(2026, 9, 13), 'tomorrow')['when'], datetime(2026, 9, 13, 0, 0))

    def test_a_time_with_no_day_is_not_a_deadline(self):     # CAP-4: blank never means today
        got = self.when('1500', day=None)
        self.assertIsNone(got['when'])
        self.assertIn('No day', got['warning'])
        self.assertIn('1500', got['basis'])                  # kept as typed
        self.assertIsNone(self.when('0900', day=None)['when'])

    def test_a_date_inside_the_time_cell_still_works(self):
        self.assertEqual(times.parse('13/9 0600', REF, 'call time')['when'], datetime(2026, 9, 13, 6, 0))
        self.assertEqual(times.parse('2026-09-14 15:00', REF, 'call time')['when'], datetime(2026, 9, 14, 15, 0))
        self.assertEqual(times.parse('0730 tomorrow', REF, 'call time')['when'], datetime(2026, 9, 13, 7, 30))

    def test_relative_to_the_reference_and_says_so(self):
        got = times.parse('+2h', REF, 'call time')
        self.assertEqual(got['when'], datetime(2026, 9, 12, 16, 32))
        self.assertIn('call time', got['basis'])
        self.assertEqual(times.parse('+90m', REF, 'x')['when'], datetime(2026, 9, 12, 16, 2))
        self.assertEqual(times.parse('+2h30', REF, 'x')['when'], datetime(2026, 9, 12, 17, 2))
        self.assertEqual(times.parse('+1:30', REF, 'x')['when'], datetime(2026, 9, 12, 16, 2))
        self.assertIsNone(times.parse('+2', REF, 'x')['when'])
        self.assertIn('ignores the return day', self.when('+2h', date(2026, 9, 13), 'tomorrow')['warning'])

    def test_never_guesses(self):
        for raw in ('25:70', '3', 'soonish', '13pm', '+0h', '31/2 1500'):
            got = self.when(raw)
            self.assertIsNone(got['when'], raw)
            self.assertIn('Not understood', got['basis'])
            self.assertIn(raw, got['basis'])          # kept as typed
        self.assertEqual(self.when('')['when'], None)
        self.assertEqual(self.when('')['basis'], '')

    def test_a_past_instant_is_flagged_not_moved(self):
        got = self.when('0900')
        self.assertEqual(got['when'], datetime(2026, 9, 12, 9, 0))   # not shifted to tomorrow (REC-6)
        self.assertIn('Already past', got['warning'])
        self.assertIsNone(self.when('0900', date(2026, 9, 13), 'tomorrow')['warning'])

    def test_ambiguous_hour_is_read_as_24_hour_and_flagged(self):
        got = self.when('3:30', date(2026, 9, 13), 'tomorrow')
        self.assertEqual(got['when'], datetime(2026, 9, 13, 3, 30))
        self.assertIn('24-hour', got['warning'])
        self.assertIsNone(self.when('1530', date(2026, 9, 13), 'tomorrow')['warning'])
        self.assertIn('24-hour', self.when('330', date(2026, 9, 13), 'tomorrow')['warning'])

    def test_the_day_cell_on_its_own(self):
        d = lambda raw: times.parse_day(raw, REF)['day']
        self.assertEqual(d('today'), TODAY)
        self.assertEqual(d('tomorrow'), date(2026, 9, 13))
        self.assertEqual(d('sat'), TODAY)                      # the weekday that is today means today
        self.assertEqual(d('sun'), date(2026, 9, 13))
        self.assertEqual(d('monday'), date(2026, 9, 14))       # the day after tomorrow, by name
        self.assertEqual(d('14/9'), date(2026, 9, 14))         # or by date
        self.assertEqual(d('14/9/26'), date(2026, 9, 14))
        self.assertEqual(d('2026-09-20'), date(2026, 9, 20))
        self.assertIsNone(d('someday'))
        self.assertIsNone(d('31/2'))
        self.assertIn('Before today', times.parse_day('1/9', REF)['warning'])

    def test_a_resolved_day_shows_as_a_date_and_types_back_in(self):
        for raw in ('today', 'tomorrow', 'monday', '14/9', '2026-09-20'):
            first = times.parse_day(raw, REF)['day']
            shown = times.fmt_day(first, REF.year)
            self.assertEqual(times.parse_day(shown, REF)['day'], first, shown)   # round trip
        self.assertEqual(times.fmt_day(date(2026, 9, 13), 2026), 'Sun 13/9')
        self.assertEqual(times.fmt_day(date(2027, 1, 4), 2026), 'Mon 4/1/27')
        self.assertEqual(times.fmt_day(None), '')


if __name__ == '__main__':
    unittest.main()
