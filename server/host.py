"""
The app's only contact with the outside world.

A host gives the app a database connection, says who is logged in and which unit they keep
watch for. Everything else is the app's own. `unit` and `user` are opaque strings the app
only ever stores and compares; that is what keeps `LogOns` free of foreign keys.
"""


def install_standalone_ui(app):
    """Compatibility shell consumes Quackit's real presentation files, never copies.

    The mounted checkout resolves them automatically. A separate compatibility
    consumer must explicitly provide RADIO_SHARED_TEMPLATES (the templates directory).
    This is a file-loader boundary only; it does not import Quackit's application/data.
    """
    import os
    from pathlib import Path
    from flask import Blueprint
    from jinja2 import ChoiceLoader, FileSystemLoader

    templates = Path(os.environ.get('RADIO_SHARED_TEMPLATES') or
                     Path(__file__).resolve().parents[2] / 'dflask' / 'templates')
    for name in ('myMacro_record_view.html', 'myMacro_filters.html', 'myMacro_entity_nav.html', 'myMacro_search_picker.html',
                 '../static/css/record_views.css', '../static/css/navbar_controls.css',
                 '../static/css/search_controls.css', '../static/js/search_controls.js', '../static/js/record_view.js', '../static/js/auto_grow.js',
                 '../static/vendor/htmx-1.9.10/htmx.min.js', '../static/js/htmx_errors.js',
                 '../static/vendor/jquery-3.6.0/jquery.min.js'):
        if not (templates / name).is_file():
            raise RuntimeError('Missing shared UI file %s; use quackit/radio or set '
                               'RADIO_SHARED_TEMPLATES to Quackit templates.' % (templates / name))
    app.jinja_loader = ChoiceLoader([app.jinja_loader, FileSystemLoader(str(templates))])
    app.register_blueprint(Blueprint('radio_shared', __name__,
                                    static_folder=str(templates.parent / 'static'),
                                    static_url_path='/radio-shared/static'))


class Host:
    base_template = 'radio/_base.html'   # a host with its own layout passes its own
    brand = 'RadioLogs'
    login_url = None                     # where to send someone who is not logged in; None -> a plain 403

    # Operational values, every one of them a placeholder a host overrides. The spec makes these
    # approved configuration (Appendix D questions 9 and 17) and refuses to invent policy; these
    # numbers exist so the app runs, and none of them has been agreed by a unit.
    approaching_minutes = 30        # WAT-2: how long before a deadline counts as approaching
    draft_followup_minutes = 15     # ACC-5: how long a draft may sit unaccepted before it is chased
    alert_repeat_minutes = 15       # how often an unacknowledged alert is put in front of someone again
    watch_stale_seconds = 180       # after this, the checker is presumed dead and the page says so

    # ---- required ----
    def connect(self):
        """A DB-API connection (pymysql) for the app's tables. The app never closes it."""
        raise NotImplementedError

    def user(self):
        """An opaque id for whoever is logged in, or None -> the app refuses (403)."""
        raise NotImplementedError

    # ---- optional ----
    def unit(self):
        """The watch owner (§3.3) for records this user creates and sees: an opaque tag. One unit by default."""
        return ''

    def history(self, cur, table, record_id, by='id_'):
        """The change history of the app's own `table` as the host's history viewer events (newest first), or
        None when this host keeps no history; the page then says so. `by` is the history column matched against
        `record_id`: 'id_' for one row, 'memberId' for every row a member holds (their contacts, vessels ...)."""
        return None

    def system_actor(self):
        """Who a host should record for something the app did on its own (REC-2: automated events
        identify the system actor rather than inventing an operator). Hosts whose audit trail
        requires a real column type return one of theirs; the checker never claims to be a person."""
        return 'system'

    # Where alerts are sent. Empty means nowhere, and the page says so rather than looking calm.
    # `{'webhook': 'https://...', 'email': {'host', 'port', 'from', 'to', 'starttls', 'username',
    # 'password'}}`; see notify.py. The spec refuses to choose a channel (Appendix D q17), so this
    # is configuration a unit fills in, and an unfilled one is a stated gap rather than a silence.
    alert_delivery = {}

    def notify(self, alert):
        """Put an alert in front of a person by whatever channel the unit has configured.

        Returns (channels that accepted it, error or None) so the checker can record whether it
        actually reached anyone. With nothing configured it reaches whoever is looking at the site
        and nobody else, which does not meet ACC-5 and is reported as such."""
        from . import notify as N
        return N.deliver(self.alert_delivery, alert)

    # `background_connect` is deliberately not defined here. A host that cannot give a connection
    # outside a request cannot have anything watching while no browser is open, and that is said
    # out loud at start-up rather than discovered later.


class NullHost(Host):
    """Standalone: one database, one nameless user, one unit."""

    def __init__(self, connect, background_connect=None):
        self._connect = connect
        self._background = background_connect or connect

    def connect(self):
        return self._connect()

    def background_connect(self):
        """A connection for the checker, outside any request."""
        return self._background()

    def user(self):
        return 'local'
