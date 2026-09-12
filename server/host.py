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

    # WAT-2: the approaching window, minutes before a deadline. The spec makes this an approved
    # configuration value; 30 is a placeholder a host overrides, not policy.
    approaching_minutes = 30

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


class NullHost(Host):
    """Standalone: one database, one nameless user, one unit."""

    def __init__(self, connect):
        self._connect = connect

    def connect(self):
        return self._connect()

    def user(self):
        return 'local'
