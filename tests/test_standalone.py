"""The standalone app: no host, one user, the pages and the API on a SQLite file."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from standalone.app import create_app


class Standalone(unittest.TestCase):
    def test_pages_and_api_work_with_no_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app('sqlite:///' + str(Path(tmp) / 'radio.sqlite'))
            app.testing = True
            c = app.test_client()
            self.assertEqual(c.get('/').status_code, 302)
            self.assertEqual(c.get('/logons').status_code, 200)
            self.assertEqual(c.get('/logons/new').status_code, 200)
            r = c.post('/logons/new', json={'fields': {
                'callDay': '2026-09-12', 'callTime': '09:00', 'registration': 'AB123Q'}})
            self.assertEqual(r.status_code, 200)
            i = r.json['id']
            self.assertEqual(c.get('/logon/%d' % i).status_code, 200)
            self.assertEqual(c.post('/api/logon/%d' % i, json={'field': 'destination', 'value': 'Moreton'}).status_code, 200)
            again = create_app('sqlite:///' + str(Path(tmp) / 'radio.sqlite')).test_client()   # the schema is IF NOT EXISTS
            self.assertIn('Moreton', again.get('/logons?day=2026-09-12').get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
