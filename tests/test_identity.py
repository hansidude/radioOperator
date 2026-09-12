"""Section 7 on an isolated database: two identifiers that agree, two that do not, and one search."""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import identity as ID
from server import logons as L
from server.sqlite import Connection, create_schema

T0 = datetime(2026, 9, 12, 14, 32)


class Identity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / 'radio.sqlite'
        create_schema(path)
        self.conn = Connection(path)
        self.cur = self.conn.cursor()
        self.clock = T0

    def trip(self, close=True, **fields):
        """A past trip carrying whatever identifiers it carried. History is the register (§3.1)."""
        self.clock += timedelta(hours=1)
        i = L.create(self.cur, 'alice', '', self.clock)
        for field, value in fields.items():
            L.set_field(self.cur, i, field, value, 'alice', self.clock)
        if close:
            L.log_off(self.cur, i, 'alice', self.clock, 'back')
        return i

    def verify(self, i):
        row = L.get(self.cur, i)
        return ID.verify(self.cur, row, L.identifiers(self.cur, i))

    # ---- IDV-2 outcomes ----

    def test_two_identifiers_that_agree_are_verified(self):
        self.trip(registration='AB123Q', memberNumber='4471', vesselDetails='6m white Quintrex')
        i = self.trip(close=False, registration='AB123Q', memberNumber='4471')
        got = self.verify(i)
        self.assertEqual(got['outcome'], 'verified', got['basis'])
        self.assertIn('agree on one boat and person', got['basis'])
        self.assertEqual(L.get(self.cur, i)['verifyOutcome'], 'verified')      # stored, not just computed (IDV-4)

    def test_one_identifier_is_never_enough(self):
        self.trip(registration='AB123Q', memberNumber='4471')
        i = self.trip(close=False, registration='AB123Q')
        got = self.verify(i)
        self.assertEqual(got['outcome'], 'unverified', got['basis'])
        self.assertIn('two that agree', got['basis'])

    def test_identifiers_pointing_at_different_boats_are_a_conflict(self):
        self.trip(registration='AB123Q', memberNumber='4471')
        self.trip(registration='ZZ999X', memberNumber='8802')
        i = self.trip(close=False, registration='AB123Q', memberNumber='8802')
        got = self.verify(i)
        self.assertEqual(got['outcome'], 'conflict', got['basis'])
        self.assertIn('different boats or people', got['basis'])

    def test_a_member_with_several_boats_is_not_a_conflict(self):
        self.trip(registration='AB123Q', memberNumber='4471')
        self.trip(registration='CD456R', memberNumber='4471')
        i = self.trip(close=False, registration='CD456R', memberNumber='4471')
        got = self.verify(i)
        self.assertEqual(got['outcome'], 'verified', got['basis'])

    def test_an_unknown_second_identifier_is_partial_not_verified(self):
        self.trip(registration='AB123Q', memberNumber='4471')
        i = self.trip(close=False, registration='AB123Q', mobile='0400 000 000')
        got = self.verify(i)
        self.assertEqual(got['outcome'], 'partial', got['basis'])
        self.assertIn('matches nothing logged before', got['basis'])

    def test_nothing_known_yet_is_unverified(self):
        i = self.trip(close=False, registration='AB123Q', memberNumber='4471')
        self.assertEqual(self.verify(i)['outcome'], 'unverified')

    def test_a_value_applied_from_an_earlier_trip_cannot_corroborate(self):     # IDV-1
        self.trip(registration='AB123Q', memberNumber='4471')
        i = self.trip(close=False, registration='AB123Q')
        out = L.apply_profile(self.cur, i, 'rego:AB123Q', 'alice', self.clock)
        self.assertIn('Member No.', out['filled'])
        got = self.verify(i)
        self.assertEqual(got['outcome'], 'unverified', got['basis'])            # still only one thing the caller said
        applied = [e for e in got['evidence'] if e['kind'] == 'memberNumber'][0]
        self.assertFalse(applied['independent'])
        self.assertEqual(applied['source'], 'profile')

    def test_the_same_value_twice_is_not_two_identifiers(self):                 # IDV-1
        self.trip(registration='AB123Q', memberNumber='4471')
        i = self.trip(close=False, registration='AB 123-Q', vesselName='AB123Q')
        ev = self.verify(i)['evidence']
        self.assertEqual([e['independent'] for e in ev].count(True), 1)

    # ---- IDV-6 tolerant matching ----

    def test_one_letter_wrong_offers_the_boat_without_claiming_a_match(self):
        self.trip(registration='AB123Q', memberNumber='4471')
        i = self.trip(close=False, registration='AB128Q', memberNumber='4471')   # 3 and 8 are not confusable
        got = self.verify(i)
        self.assertEqual(got['outcome'], 'partial', got['basis'])
        rego = [e for e in got['evidence'] if e['kind'] == 'registration'][0]
        self.assertIsNone(rego['match'])
        i = self.trip(close=False, registration='AB1230', memberNumber='4471')   # Q is not in a group either
        self.assertEqual(self.verify(i)['outcome'], 'partial')

    def test_a_confusable_letter_suggests_the_right_boat(self):
        self.trip(registration='BX77', memberNumber='4471')
        i = self.trip(close=False, registration='DX77', memberNumber='4471')     # B and D rhyme on radio
        got = self.verify(i)
        rego = [e for e in got['evidence'] if e['kind'] == 'registration'][0]
        self.assertEqual(rego['match']['how'], 'near')
        self.assertEqual(rego['match']['suggests'], 'BX77')
        self.assertEqual((rego['match']['from'], rego['match']['to']), ('D', 'B'))
        self.assertEqual(got['outcome'], 'partial')                              # never verified on a guess
        self.assertIn('letter changed', got['basis'])

    def test_variants_cover_the_reported_confusions(self):
        self.assertIn('0', [v['value'] for v in ID.variants('O')])
        self.assertIn('S', [v['value'] for v in ID.variants('F')])
        self.assertIn('I', [v['value'] for v in ID.variants('1')])
        self.assertEqual(ID.variants(''), [])

    # ---- SRCH ----

    def test_one_box_finds_boats_people_and_trips(self):
        self.trip(registration='AB123Q', memberNumber='4471', mobile='0412 345 678', destination='Facing Island')
        at_sea = self.trip(close=False, registration='CD456R', memberNumber='4471')
        by_rego = ID.search(self.cur, '', 'ab123')
        self.assertEqual(by_rego[0]['kind'], 'vessel')
        for query in ('4471', '0412345678', '0412 345', 'facing'):
            self.assertTrue(ID.search(self.cur, '', query), query)               # any identifier, same box (SRCH-2)
        self.assertTrue(ID.search(self.cur, '', 'AB12'))                          # partial input (SRCH-5)
        self.assertEqual(ID.search(self.cur, '', 'a'), [])                        # one letter is not a search
        vessels = [h for h in ID.search(self.cur, '', 'cd456') if h['kind'] == 'vessel']
        self.assertTrue(vessels[0]['atSea'])                                      # marked as currently out (SRCH-4)
        self.assertTrue(all(h['kind'] in ('vessel', 'person', 'trip') for h in by_rego))

    def test_applying_a_result_fills_identity_but_never_trip_facts(self):        # SRCH-6
        self.trip(registration='AB123Q', memberNumber='4471', mobile='0412 345 678',
                  vesselDetails='6m white Quintrex', pob='3', destination='Facing Island')
        i = self.trip(close=False, registration='AB123Q')
        out = L.apply_profile(self.cur, i, 'rego:AB123Q', 'alice', self.clock)
        row = L.get(self.cur, i)
        self.assertEqual((row['memberNumber'], row['mobile'], row['vesselDetails']), ('4471', '0412 345 678', '6m white Quintrex'))
        self.assertIsNone(row['pob']); self.assertIsNone(row['destination'])      # a past trip is not this trip
        self.assertIsNone(row['eta'])
        with self.assertRaises(L.Refused):
            L.apply_profile(self.cur, i, 'rego:AB123Q', 'alice', self.clock)      # nothing left to add
        with self.assertRaises(L.Refused):
            L.apply_profile(self.cur, i, 'rego:NOSUCH', 'alice', self.clock)

    def test_applying_never_overwrites_what_the_caller_just_said(self):
        self.trip(registration='AB123Q', memberNumber='4471', mobile='0412 345 678')
        i = self.trip(close=False, registration='AB123Q', mobile='0499 999 999')
        L.apply_profile(self.cur, i, 'rego:AB123Q', 'alice', self.clock)
        self.assertEqual(L.get(self.cur, i)['mobile'], '0499 999 999')
        self.assertEqual(L.get(self.cur, i)['memberNumber'], '4471')


if __name__ == '__main__':
    unittest.main()
