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

from . import identity as ID
from . import logons as L
from . import watch as W
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


def _drafts(cur, h):
    return L.drafts(cur, h.unit(), _now(), h.approaching_minutes)


def _alerts(cur, h):
    """What the checker has raised, and whether the checker is alive. Both are shown, because an
    empty alert list from a dead checker looks exactly like an empty one from a quiet night."""
    now = _now()
    alerts = W.open_alerts(cur, h.unit())
    for a in alerts:
        row = L.get(cur, a['logOnId'])
        a['reference'] = L.reference(row) if row else '#%d' % a['logOnId']
        a['vessel'] = (row or {}).get('registration') or (row or {}).get('vesselName') or ''
        a['overdueMinutes'] = int((now - a['dueAt']).total_seconds() // 60)
    return alerts, W.health(cur, now, h.watch_stale_seconds)


# ---------- pages ----------

@bp.route('/logons')
def logons_page():
    h, (conn, cur) = _open()
    rows = _queue(cur, h)
    unaccepted = _drafts(cur, h)
    closed = L.recent_closed(cur, h.unit())
    alerts, health = _alerts(cur, h)
    cur.close()
    return _page('logons.html', queue=rows, drafts=unaccepted, closed=closed, alerts=alerts, health=health,
                 window=h.approaching_minutes, reference=L.reference)


@bp.route('/logons/rows')
def logons_rows():
    """The queue on its own: what the pages re-fetch so overdue shows without anyone pressing anything (WAT-3, minimal)."""
    h, (conn, cur) = _open()
    if request.args.get('partial') != '1':
        cur.close()
        return redirect('/logons')
    rows = _queue(cur, h)
    unaccepted = _drafts(cur, h)
    alerts, health = _alerts(cur, h)
    cur.close()
    return _page('_queue.html', queue=rows, drafts=unaccepted, alerts=alerts, health=health,
                 current=request.args.get('current', type=int), window=h.approaching_minutes, reference=L.reference)


@bp.route('/logons/new', methods=['POST'])
def logons_new():
    """Begin capture: an empty draft exists and is owned before a word is typed (CAP-1). It is not a
    log on and is not watched until it is accepted (ACC-2)."""
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
    verified = ID.verify(cur, row, idents)
    unaccepted = _drafts(cur, h)
    alerts, health = _alerts(cur, h)
    clash = L.open_for_vessel(cur, h.unit(), row) if row['watchStatus'] != 'watching' else None
    cur.close()
    cond, minutes = L.condition(row, _now(), h.approaching_minutes)
    return _page('logon.html', logon=row, queue=rows, drafts=unaccepted, alerts=alerts, health=health,
                 identifiers=idents, gaps=L.gaps(row),
                 condition=cond, minutes=minutes, verified=verified, missing=L.missing(row), clash=clash,
                 extra=L.EXTRA, mandatory=L.IDENTITY_SET, labels=L.LABELS, time_fields=L.TIME_FIELDS,
                 day_fields=L.DAY_FIELDS, column=L.column, box=L.box, pair=L.DAY_FIELDS, channels=L.CHANNELS,
                 close_reasons=L.CLOSE_REASONS, reference=L.reference, window=h.approaching_minutes)


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
    """Take the watch (ACC-3). Refused until the mandatory set is there and no other log on holds
    this vessel; the refusal says which, and discards nothing."""
    return _action(logon_id, lambda cur, v: L.accept(cur, logon_id, host().user(), _now(), v))


@bp.route('/logon/<int:logon_id>/discard', methods=['POST'])
def logon_discard(logon_id):
    """Throw away a draft that was never a log on (ACC-7)."""
    return _action(logon_id, lambda cur, v: L.discard(cur, logon_id, host().user(), _now(), request.form.get('reason'), v))


@bp.route('/logon/<int:logon_id>/reopen', methods=['POST'])
def logon_reopen(logon_id):
    """Correct a closure made in error: the record comes back under watch, the closure event stays."""
    h, (conn, cur) = _open()
    _logon(cur, logon_id, h, lock=True)
    try:
        L.reopen(cur, logon_id, h.user(), _now(), request.form.get('reason'), request.form.get('version'))
    except (L.Refused, L.Stale) as e:
        conn.rollback()
        cur.close()
        return str(e), 409 if isinstance(e, L.Stale) else 400
    conn.commit()
    cur.close()
    return redirect(request.form.get('back') or '/logon/%d' % logon_id)


@bp.route('/logon/<int:logon_id>/logoff', methods=['POST'])
def logon_logoff(logon_id):
    return _action(logon_id, lambda cur, v: L.log_off(cur, logon_id, host().user(), _now(),
                                                      request.form.get('note'), request.form.get('reason'), v))


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


@bp.route('/api/logons/search')
def api_search():
    """One input, every record type (SRCH-1 to SRCH-5). `for` is the record being captured, so each
    result can say what applying it would fill in.

    Namespaced under /api/logons because a host may already have mounted another app: quackit's
    3D planner owns a bare /api/search, and whichever blueprint registers first wins the URL."""
    h, (conn, cur) = _open()
    hits = ID.search(cur, h.unit(), request.args.get('q'))
    current = request.args.get('for', type=int)
    if current:
        for hit in hits:
            fields, _ = ID.profile(cur, h.unit(), hit['key'], current)
            hit['offers'] = [L.LABELS.get(f, f) for f in (fields or {}) if f in L.FIELDS]
    cur.close()
    for hit in hits:
        if hit.get('lastSeen'):
            hit['lastSeen'] = hit['lastSeen'].isoformat()
    return jsonify({'hits': hits, 'query': request.args.get('q', '')})


@bp.route('/logon/<int:logon_id>/apply', methods=['POST'])
def logon_apply(logon_id):
    """Put a search result's known detail onto this capture, in one action (SRCH-6)."""
    h, (conn, cur) = _open()
    _logon(cur, logon_id, h, lock=True)
    body = request.get_json(silent=True) or request.form
    try:
        out = L.apply_profile(cur, logon_id, body.get('key'), h.user(), _now(), body.get('version'))
    except (L.Refused, L.Stale, ValueError) as e:
        conn.rollback()
        cur.close()
        return jsonify({'error': str(e)}), 409 if isinstance(e, L.Stale) else 400
    conn.commit()
    cur.close()
    return jsonify(out)


@bp.route('/logon/<int:logon_id>/alert/<int:alert_id>/ack', methods=['POST'])
def alert_ack(logon_id, alert_id):
    """Record that someone has seen it. It satisfies nothing and closes nothing (§2)."""
    h, (conn, cur) = _open()
    _logon(cur, logon_id, h, lock=True)
    W.acknowledge(cur, alert_id, h.user(), _now())
    conn.commit()
    cur.close()
    return redirect(request.form.get('back') or '/logons')


@bp.route('/logons/alerts/test', methods=['POST'])
def alerts_test():
    """Send a test alert through whatever is configured, and say plainly what happened.

    A delivery channel nobody has ever proved is a delivery channel nobody should rely on, so this
    exists to be pressed before the unit trusts any of this."""
    h, (conn, cur) = _open()
    cur.close()
    now = _now()
    alert = {'alertId': None, 'kind': 'test', 'unit': h.unit(), 'logOnId': None, 'reference': 'test',
             'vessel': None, 'at': now,
             'message': 'Test alert from the vessel log on, sent by %s. Nothing is wrong.' % h.user()}
    try:
        sent, error = h.notify(alert) or ([], None)
    except Exception as e:
        sent, error = [], str(e)
    # Answered here rather than flashed through the host: a host's flash styling is its own, and a
    # delivery that reached nobody must not be rendered as good news.
    return jsonify({'ok': bool(sent), 'sent': sent, 'error': error,
                    'message': ('Test alert accepted by %s.%s' % (', '.join(sent), (' Not by %s.' % error) if error else ''))
                               if sent else ('Test alert reached nobody. %s' % (error or 'No delivery channel is configured.'))})


@bp.route('/api/logons/alerts')
def api_alerts():
    """What is due and whether anything is watching. Served so a page can poll, but the alerts
    exist whether or not anyone does (ACC-5, WAT-3)."""
    h, (conn, cur) = _open()
    alerts, health = _alerts(cur, h)
    cur.close()
    for a in alerts:
        for k in ('dueAt', 'raisedAt', 'notifiedAt', 'deliveredAt', 'acknowledgedAt'):
            if a.get(k):
                a[k] = a[k].isoformat()
    if health.get('lastRunAt'):
        health['lastRunAt'] = health['lastRunAt'].isoformat()
    return jsonify({'alerts': alerts, 'health': health, 'now': _now().isoformat()})


@bp.route('/api/logons/queue')
def api_queue():
    h, (conn, cur) = _open()
    rows = _queue(cur, h)
    unaccepted = _drafts(cur, h)
    cur.close()
    for r in rows + unaccepted:
        for k in L.DATETIMES:
            if r.get(k):
                r[k] = r[k].isoformat()
        for k in L.DATES:
            if r.get(k):
                r[k] = r[k].isoformat()
    return jsonify({'now': _now().isoformat(), 'approachingMinutes': h.approaching_minutes,
                    'watching': rows, 'drafts': unaccepted})


@bp.errorhandler(NotLoggedIn)
def _to_login(_):
    return redirect(host().login_url)


def mount(app, host, watch_every=30):
    """Give a Flask app the log on pages and API, and start the thing that watches deadlines.

    `watch_every=0` leaves the checker off, which means nothing is watched unless a browser is
    open. That is a choice a host has to make deliberately, not a default."""
    app.config['RADIO_HOST'] = host
    app.register_blueprint(bp)
    if watch_every:
        W.start(app, host, watch_every)
    return bp
