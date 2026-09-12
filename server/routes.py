"""
The blueprint: the pages and the API. Everything a browser talks to.

Pages extend the host's base template and fill `page_title` / `navbar_buttons` / `body`, so
inside a host they wear its navbar and theme. They never touch the host's session, users or
macros — everything they need arrives as a template variable. That rule is what keeps this
liftable.
"""
from datetime import datetime
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request

from . import logons as L
from .db import cursor

HERE = Path(__file__).resolve().parent
bp = Blueprint('radio', __name__, template_folder=str(HERE / 'templates'))


def host():
    h = current_app.config.get('RADIO_HOST')
    if h is None:
        raise RuntimeError('radio.server was not mounted: no host')
    return h


class NotLoggedIn(Exception):
    """Raised by _open; turned into the host's login page, or a plain 403 when it has none."""


def _open():
    """The host and a cursor, or the host's login page when nobody is logged in."""
    h = host()
    if h.user() is None:
        if h.login_url:
            raise NotLoggedIn()
        abort(403)
    return h, cursor(h)


def _now():
    return datetime.now().replace(microsecond=0)


def _logon(cur, logon_id, h, lock=False):
    row = L.get(cur, logon_id, lock)
    if not row:
        abort(404)
    if row['unit'] != h.unit():
        abort(403)
    return row


def _page(name, **ctx):
    h = host()
    return render_template('radio/' + name, base_template=h.base_template, brand=h.brand, now=_now(), **ctx)


def _queue(cur, h):
    return L.queue(cur, h.unit(), _now(), h.approaching_minutes)


# ---------- pages ----------

@bp.route('/logons')
def logons_page():
    h, (conn, cur) = _open()
    rows = _queue(cur, h)
    closed = L.recent_closed(cur, h.unit())
    cur.close()
    return _page('logons.html', queue=rows, closed=closed, window=h.approaching_minutes)


@bp.route('/logons/rows')
def logons_rows():
    """The queue on its own: what the pages re-fetch so overdue shows without anyone pressing anything (WAT-3, minimal)."""
    h, (conn, cur) = _open()
    if request.args.get('partial') != '1':
        cur.close()
        return redirect('/logons')
    rows = _queue(cur, h)
    cur.close()
    return _page('_queue.html', queue=rows, current=request.args.get('current', type=int), window=h.approaching_minutes)


@bp.route('/logons/new', methods=['POST'])
def logons_new():
    """Begin capture: an empty Draft exists, owned and on the queue, before a word is typed (CAP-1)."""
    h, (conn, cur) = _open()
    new_id = L.create(cur, h.user(), h.unit(), _now())
    conn.commit()
    cur.close()
    return redirect('/logon/%d' % new_id)


@bp.route('/logon/<int:logon_id>')
def logon_page(logon_id):
    h, (conn, cur) = _open()
    row = _logon(cur, logon_id, h)
    rows = _queue(cur, h)
    idents = L.identifiers(cur, logon_id)
    cur.close()
    cond, minutes = L.condition(row, _now(), h.approaching_minutes)
    return _page('logon.html', logon=row, queue=rows, identifiers=idents, gaps=L.gaps(row), condition=cond, minutes=minutes,
                 classes=L.CLASSES, labels=L.LABELS, time_fields=L.TIME_FIELDS, channels=L.CHANNELS, window=h.approaching_minutes)


def _action(logon_id, do):
    """A form action on one record: run `do(cur, row_version)`, commit, go back. Refusals are shown, not swallowed."""
    h, (conn, cur) = _open()
    _logon(cur, logon_id, h, lock=True)
    try:
        do(cur, request.form.get('version'))
    except (L.Refused, L.Stale) as e:
        conn.rollback()
        cur.close()
        return str(e), 409 if isinstance(e, L.Stale) else 400
    conn.commit()
    cur.close()
    return redirect(request.form.get('back') or '/logon/%d' % logon_id)


@bp.route('/logon/<int:logon_id>/accept', methods=['POST'])
def logon_accept(logon_id):
    return _action(logon_id, lambda cur, v: L.accept(cur, logon_id, host().user(), _now(), v))


@bp.route('/logon/<int:logon_id>/capture', methods=['POST'])
def logon_capture(logon_id):
    complete = request.form.get('complete') == '1'
    return _action(logon_id, lambda cur, v: L.set_capture(cur, logon_id, complete, host().user(), _now(), v))


@bp.route('/logon/<int:logon_id>/logoff', methods=['POST'])
def logon_logoff(logon_id):
    return _action(logon_id, lambda cur, v: L.log_off(cur, logon_id, host().user(), _now(), request.form.get('note'), v))


# ---------- API ----------

@bp.route('/api/logon/<int:logon_id>', methods=['POST'])
def api_set_field(logon_id):
    """{field, value, version} -> the stored value and what to show beside it. 409 when stale, 400 when refused.
    A 200 is the durable acknowledgment the page's Saved status waits for (CAP-19)."""
    h, (conn, cur) = _open()
    _logon(cur, logon_id, h, lock=True)
    body = request.get_json(silent=True) or {}
    now = _now()
    try:
        if 'field' not in body:
            raise L.Refused('expected {field, value, version}')
        out = L.set_field(cur, logon_id, body['field'], body.get('value'), h.user(), now, body.get('version'))
    except (L.Refused, L.Stale) as e:
        conn.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 409 if isinstance(e, L.Stale) else 400
    conn.commit()
    cur.close()
    out['when'] = out['when'].isoformat() if out['when'] else None
    out['savedAt'] = now.strftime('%H:%M:%S')
    return jsonify(out)


@bp.route('/api/logons/queue')
def api_queue():
    h, (conn, cur) = _open()
    rows = _queue(cur, h)
    cur.close()
    for r in rows:
        for k in L.DATETIMES:
            if r.get(k):
                r[k] = r[k].isoformat()
    return jsonify({'now': _now().isoformat(), 'approachingMinutes': h.approaching_minutes, 'logons': rows})


@bp.errorhandler(NotLoggedIn)
def _to_login(_):
    return redirect(host().login_url)


def mount(app, host):
    """Give a Flask app the log on pages and API."""
    app.config['RADIO_HOST'] = host
    app.register_blueprint(bp)
    return bp
