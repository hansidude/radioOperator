"""The Help page and the Radio Logs program layout."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import member_pages as P
from test_pages import test_app


class Help(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = test_app(Path(self.tmp.name) / 'test.db')
        self.app.testing = True
        self.a = self.app.test_client()
        self.a.get('/test-login/alice/unitA')

    def test_help_explains_every_part_with_the_real_controls(self):
        page = self.a.get('/radio/help').get_data(as_text=True)
        for section in ('menu', 'log', 'views', 'status', 'logon', 'members', 'search', 'fields'):
            self.assertIn('id="%s"' % section, page)
        for control in ('data-dc-record-view="cards"', 'data-dc-record-view="paragraphs"',
                        'data-dc-record-panel aria-controls="roHelpPanel"', 'data-dc-record-size="larger"', 'data-dc-record-width',
                        'data-grp-toggle-all="radioHelp"'):
            self.assertIn(control, page)                                          # the demonstration is the real controls
            self.assertIn("data-help-icon='[%s" % control.split(' ')[0].split('=')[0], page)   # and each is explained
        self.assertIn('Sample Sea Dog', page)
        self.assertIn('href="/radio/help"', page)                                 # on the menu
        self.assertIn('<div class="container-fluid mySpacing">', page)

    def test_every_field_emoji_has_a_name_on_the_help_page(self):
        symbols = self.app.jinja_env.get_template('radio/_ui.html').module.FIELD_SYMBOLS
        for field in symbols:
            self.assertTrue(P.HELP_LABELS.get(field), field)
        page = self.a.get('/radio/help').get_data(as_text=True)
        self.assertIn('data-help-field="ownerPhone"><span role="img" aria-hidden="true">📱</span><span class="dc-record-panel-badge-label">Owner phone</span>', page)

    def test_help_needs_a_login(self):
        self.assertEqual(self.app.test_client().get('/radio/help').status_code, 302)          # to the host's login page


if __name__ == '__main__':
    unittest.main()
