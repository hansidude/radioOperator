"""
The app's only contact with the outside world.

A host gives the app a database connection, says who is logged in and which unit they keep
watch for. Everything else is the app's own. `unit` and `user` are opaque strings the app
only ever stores and compares; that is what keeps `LogOns` free of foreign keys.
"""


class Host:
    base_template = 'radio/_base.html'   # a host with its own layout passes its own
    brand = 'Log on'
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

    def system_actor(self):
        """Who a host should record for something the app did on its own (REC-2: automated events
        identify the system actor rather than inventing an operator). Hosts whose audit trail
        requires a real column type return one of theirs; the checker never claims to be a person."""
        return 'system'

    def notify(self, alert):
        """Put an alert in front of a person by whatever channel the unit has approved.

        The default does nothing, which means an alert reaches someone only when they look at the
        site. That is not ACC-5, and a deployment that leaves this unimplemented has not met it.
        A host wires this to the approved channel; the spec refuses to choose one (Appendix D q17)."""
        return None

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
