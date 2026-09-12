"""
Vessel log on: the radio operator's capture and watch pages, as their own app a host can mount.

    from radio.server import mount
    mount(app, MyHost())

The host (see host.py) hands over a database connection and says who is logged in. Nothing
here knows anything about the host's application. The specification this implements is
`vessel-logon-spec.md` at the repo root; requirement ids (CAP-n, WAT-n, ...) are cited in
comments where code exists because of them.

`logons` (the data layer) is deliberately importable without Flask, so a script or a test can
use it on its own — hence the lazy lookup below rather than eager imports.
"""

__all__ = ['Host', 'NullHost', 'mount']


def __getattr__(name):
    if name in ('Host', 'NullHost'):
        from . import host
        return getattr(host, name)
    if name == 'mount':
        from .routes import mount
        return mount
    raise AttributeError(name)
