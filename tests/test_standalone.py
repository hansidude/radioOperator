"""The standalone app: no host, one user, the pages and the API on a SQLite file."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from standalone.app import create_app


class Standalone(unittest.TestCase):
    def test_shared_assets_are_served_from_the_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app('sqlite:///' + str(Path(tmp) / 'radio.sqlite'))
            c = app.test_client()
            shared = Path(__file__).resolve().parents[2] / 'dflask' / 'static'
            page = c.get('/logons').get_data(as_text=True)
            for asset in ('css/record_views.css', 'css/navbar_controls.css',
                          'css/search_controls.css', 'js/search_controls.js', 'js/ui_symbols.js', 'js/record_view.js', 'js/auto_grow.js'):
                self.assertIn('/radio-shared/static/' + asset, page)
                response = c.get('/radio-shared/static/' + asset)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, (shared / asset).read_bytes())
                response.close()
            for asset in ('vendor/noto-emoji-2.051/Noto-COLRv1.ttf',
                          'vendor/noto-emoji-2.051/svg/emoji_u1f6df.svg',
                          'vendor/noto-emoji-2.051/svg/emoji_u1f50e.svg'):
                response = c.get('/radio-shared/static/' + asset)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, (shared / asset).read_bytes())
                response.close()

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
