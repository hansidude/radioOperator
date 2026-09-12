"""Times as operators say them: read against a reference, never guessed (CAP-8, CAP-23, REC-6)."""
import sys
import unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import times

REF = datetime(2026, 9, 12, 14, 32)    # a Saturday afternoon call


class Times(unittest.TestCase):
    def when(self, raw):
        return times.parse(raw, REF, 'call time')

    def test_forms_operators_use(self):
        self.assertEqual(self.when('1500')['when'], datetime(2026, 9, 12, 15, 0))
        self.assertEqual(self.when('15:00')['when'], datetime(2026, 9, 12, 15, 0))
        self.assertEqual(self.when('3pm')['when'], datetime(2026, 9, 12, 15, 0))
        self.assertEqual(self.when('3:30 PM')['when'], datetime(2026, 9, 12, 15, 30))
        self.assertEqual(self.when('12am tomorrow')['when'], datetime(2026, 9, 13, 0, 0))
        self.assertEqual(self.when('0730 tomorrow')['when'], datetime(2026, 9, 13, 7, 30))
        self.assertEqual(self.when('13/9 0600')['when'], datetime(2026, 9, 13, 6, 0))
        self.assertEqual(self.when('2026-09-14 15:00')['when'], datetime(2026, 9, 14, 15, 0))

    def test_relative_to_the_reference_and_says_so(self):
        got = self.when('+2h')
        self.assertEqual(got['when'], datetime(2026, 9, 12, 16, 32))
        self.assertIn('call time', got['basis'])
        self.assertEqual(self.when('+90m')['when'], datetime(2026, 9, 12, 16, 2))
        self.assertEqual(self.when('+2h30')['when'], datetime(2026, 9, 12, 17, 2))
        self.assertEqual(self.when('+1:30')['when'], datetime(2026, 9, 12, 16, 2))
        self.assertIsNone(self.when('+2')['when'])

    def test_never_guesses(self):
        for raw in ('25:70', '3', 'soonish', '13pm', '+0h', '12/9', '31/2 1500'):
            got = self.when(raw)
            self.assertIsNone(got['when'], raw)
            self.assertIn('Not understood', got['basis'])
            self.assertIn(raw, got['basis'])          # kept as typed
        self.assertEqual(self.when('')['when'], None)
        self.assertEqual(self.when('')['basis'], '')

    def test_past_time_stays_today_and_is_marked(self):
        got = self.when('0900')
        self.assertEqual(got['when'], datetime(2026, 9, 12, 9, 0))   # not shifted to tomorrow (REC-6)
        self.assertIn('already due', got['warning'])
        self.assertIsNone(self.when('0900 tomorrow')['warning'])

    def test_ambiguous_hour_is_read_as_24_hour_and_flagged(self):
        got = self.when('3:30')
        self.assertEqual(got['when'], datetime(2026, 9, 12, 3, 30))
        self.assertIn('24-hour', got['warning'])
        self.assertIsNone(self.when('1530')['warning'])
        self.assertIn('24-hour', self.when('330')['warning'])


if __name__ == '__main__':
    unittest.main()
