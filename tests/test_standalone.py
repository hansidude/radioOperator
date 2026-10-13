"""The standalone app: no host, one user, the pages and the API on a SQLite file."""
import re
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
                          'css/search_controls.css', 'js/search_controls.js', 'js/ui_symbols.js', 'js/record_view.js', 'js/auto_grow.js',
                          'js/controls.js', 'js/bulk_edit.js', 'js/page_stays.js', 'js/navbar_controls.js'):
                self.assertIn('/radio-shared/static/' + asset, page)
                response = c.get('/radio-shared/static/' + asset)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, (shared / asset).read_bytes())
                response.close()
            # Quackit CR-413: the shell asks for the shared files from their one owner, Quackit's myMacro_record_view.html
            # shell_scripts / shell_assets (which Quackit's layout.html draws too), each once, in its order, and nothing
            # copied beside them; a version changed there reaches this shell with no edit here.
            owner = app.jinja_env.get_template('myMacro_record_view.html').module
            with app.test_request_context('/logons'):
                owned = re.findall(r'(?:src|href)="(/radio-shared/static/[^"]+)"',
                                   str(owner.shell_scripts('radio_shared.static')) + str(owner.shell_assets('radio_shared.static')))
            head = page.split('</head>')[0]
            self.assertTrue(len(owned) >= 10, owned)
            self.assertEqual(re.findall(r'(?:src|href)="(/radio-shared/static/[^"]+)"', head), owned)
            for url in owned:
                response = c.get(url)
                self.assertEqual(response.status_code, 200, url)
                response.close()
            # Quackit CR-271 Q3: the shared macros' own scripts (the tabs, the search, the combo boxes) are controls.js
            # blocks, loaded by page_script from the shared_static_endpoint this shell sets: the same served file.
            for path in ('/logons', '/logons/new'):
                runs = re.findall(r'<script src="([^"]*)" data-dc-run="([\w-]+)"', c.get(path).get_data(as_text=True))
                self.assertTrue(runs, path + ' renders no shared macro script')
                for src, run in runs:
                    self.assertTrue(src.startswith('/radio-shared/static/js/'), '%s: %s loads from %s' % (path, run, src))
            for asset in ('fonts/RobotoMono.woff2', 'vendor/noto-emoji-2.051/Noto-COLRv1.ttf',
                          'vendor/noto-emoji-2.051/svg/emoji_u1f6df.svg',
                          'vendor/noto-emoji-2.051/svg/emoji_u1f50e.svg'):
                response = c.get('/radio-shared/static/' + asset)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, (shared / asset).read_bytes())
                response.close()

    def test_a_version_changed_in_quackit_s_owner_reaches_the_shell(self):
        """Quackit CR-413: bump a shared file's version in the owner (here in a copy of its templates) and the standalone
        shell asks for it, through Radio's shared-template loader, with no second edit."""
        import os
        import shutil
        from unittest import mock
        shared = Path(__file__).resolve().parents[2] / 'dflask' / 'templates'
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / 'dflask' / 'templates'
            shutil.copytree(shared, copy)
            (copy.parent / 'static').symlink_to(shared.parent / 'static')                     # the files themselves, unchanged
            owner = copy / 'myMacro_record_view.html'
            text, count = re.subn(r"(filename='css/navbar_controls\.css', v=')[^']+'", r"\1cr413-probe'", owner.read_text())
            self.assertEqual(count, 1, 'the owner gives navbar_controls.css one version')
            owner.write_text(text)
            with mock.patch.dict(os.environ, {'RADIO_SHARED_TEMPLATES': str(copy)}):
                app = create_app('sqlite:///' + str(Path(tmp) / 'radio.sqlite'))
            page = app.test_client().get('/logons').get_data(as_text=True)
            self.assertIn('/radio-shared/static/css/navbar_controls.css?v=cr413-probe"', page)
            self.assertEqual(page.count('css/navbar_controls.css'), 1)

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
