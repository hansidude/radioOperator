"""
The member and public vessel pages, on the same blueprint as the log.

Plain forms: a save posts, a refusal renders the same page again with the values typed and the
boxes that stopped it red (400), or with the reason when someone else saved first (409). Every form
action carries its tab (`#vessels`), so the browser comes back to the tab it was on either way.
"""
from flask import abort, jsonify, make_response, redirect, request

from . import logons as L
from . import members as M
from .routes import _now, _open, _page, bp

TABS = [('details', 'Details', 'person-vcard'), ('contacts', 'Emergency contacts', 'telephone-plus'),
        ('vessels', 'Vessels', 'life-preserver'), ('trailers', 'Trailers', 'truck-flatbed'),
        ('cars', 'Cars', 'car-front'), ('history', 'History', 'clock-history')]


def _member(cur, h, member_id, lock=False):
    row = M.get(cur, 'member', member_id, lock)
    if not row:
        abort(404)
    if row['unit'] != h.unit():
        abort(403)
    return row


def _wants_json():
    """A save from the log on page, which stays where it is and wants the new record back."""
    return request.headers.get('Accept') == 'application/json'


def _values(kind):
    return {f: request.form.get(f, '') for f in M.KINDS[kind]['fields']}


def _list_response(template, **ctx):
    """The page, or on a toolbar change the page for htmx to select its rows from, with the search kept in the address bar."""
    response = make_response(_page(template, **ctx))
    if request.headers.get('HX-Request'):
        response.headers['HX-Replace-Url'] = request.full_path.rstrip('?')
    return response


# ---------- members ----------

@bp.route('/members')
def members_page():
    h, (conn, cur) = _open()
    q = (request.args.get('q') or '').strip()
    rows = M.members(cur, h.unit(), q)
    cur.close()
    return _list_response('members.html', members=rows, search=q)


def _member_page(cur, h, member, failed=None, status=200):
    ctx = {'member': member, 'failed': failed or {}, 'kinds': M.KINDS, 'labels': M.LABELS, 'tabs': TABS}
    if member.get('id'):
        ctx['children'] = {kind: M.children(cur, kind, member['id']) for kind in M.CHILDREN}
        ctx['history'] = h.history(cur, 'Members', member['id'])
    cur.close()
    return _page('member.html', creating=not member.get('id'), **ctx), status


def _refused(e, form, values):
    """What a refused save puts back on the page: the form it came from, what was typed, and why."""
    return {'form': form, 'values': values, 'red': getattr(e, 'fields', []), 'error': str(e)}


@bp.route('/members/new', methods=['GET', 'POST'])
def members_new():
    h, (conn, cur) = _open()
    if request.method == 'GET':
        return _member_page(cur, h, M.blank('member'))
    values = _values('member')
    try:
        member_id = M.create_member(cur, values, h.user(), h.unit(), _now())
    except L.Refused as e:
        conn.rollback()
        return _member_page(cur, h, M.blank('member'), _refused(e, 'member', values), 400)
    conn.commit()
    cur.close()
    return redirect('/member/%d' % member_id)


@bp.route('/member/<int:member_id>', methods=['GET', 'POST'])
def member_page(member_id):
    h, (conn, cur) = _open()
    if request.method == 'GET':
        return _member_page(cur, h, _member(cur, h, member_id))
    member = _member(cur, h, member_id, lock=True)
    values = _values('member')
    try:
        M.save(cur, 'member', member, values, h.user(), _now(), request.form.get('version'))
    except (L.Refused, L.Stale) as e:
        conn.rollback()
        return _member_page(cur, h, member, _refused(e, 'member', values), 409 if isinstance(e, L.Stale) else 400)
    conn.commit()
    cur.close()
    return redirect('/member/%d' % member_id)


@bp.route('/member/<int:member_id>/<kind>', methods=['POST'])
def member_add(member_id, kind):
    """Add an emergency contact, vessel, trailer or car to a member."""
    h, (conn, cur) = _open()
    if kind not in M.CHILDREN:
        abort(404)
    member = _member(cur, h, member_id)
    values = _values(kind)
    try:
        child_id = M.add_child(cur, kind, member, values, h.user(), _now())
    except L.Refused as e:
        conn.rollback()
        if _wants_json():
            cur.close()
            return jsonify({'error': str(e), 'fields': getattr(e, 'fields', [])}), 400
        return _member_page(cur, h, member, _refused(e, kind + '-new', values), 400)
    conn.commit()
    if _wants_json() and kind == 'vessels':
        item = M.vessel_item(M.get(cur, 'vessels', child_id))
        cur.close()
        return jsonify({'id': child_id, 'item': item})
    cur.close()
    return redirect('/member/%d' % member_id)


def _child(cur, h, member_id, kind, child_id):
    if kind not in M.CHILDREN:
        abort(404)
    member = _member(cur, h, member_id)
    row = M.get(cur, kind, child_id, lock=True)
    if not row or row['memberId'] != member['id']:
        abort(404)
    return member, row


@bp.route('/member/<int:member_id>/<kind>/<int:child_id>', methods=['POST'])
def member_child_save(member_id, kind, child_id):
    h, (conn, cur) = _open()
    member, row = _child(cur, h, member_id, kind, child_id)
    values = _values(kind)
    try:
        M.save(cur, kind, row, values, h.user(), _now(), request.form.get('version'))
    except (L.Refused, L.Stale) as e:
        conn.rollback()
        return _member_page(cur, h, member, _refused(e, '%s-%d' % (kind, child_id), values), 409 if isinstance(e, L.Stale) else 400)
    conn.commit()
    cur.close()
    return redirect('/member/%d' % member_id)


@bp.route('/member/<int:member_id>/<kind>/<int:child_id>/remove', methods=['POST'])
def member_child_remove(member_id, kind, child_id):
    h, (conn, cur) = _open()
    member, row = _child(cur, h, member_id, kind, child_id)
    try:
        M.remove(cur, kind, row, h.user(), _now(), request.form.get('version'))
    except (L.Refused, L.Stale) as e:
        conn.rollback()
        return _member_page(cur, h, member, _refused(e, '%s-%d' % (kind, child_id), {}), 409 if isinstance(e, L.Stale) else 400)
    conn.commit()
    cur.close()
    return redirect('/member/%d' % member_id)


# ---------- what the log on's shared search picker asks (myMacro_search_picker.html) ----------

@bp.route('/api/logons/members')
def api_members():
    h, (conn, cur) = _open()
    items = [M.member_item(m) for m in M.members(cur, h.unit(), request.args.get('q'))]
    cur.close()
    return jsonify({'items': items})


@bp.route('/api/logons/vessels')
def api_member_vessels():
    """One member's vessels: the second stage of the Member pick, scoped by the member chosen first."""
    h, (conn, cur) = _open()
    member = _member(cur, h, request.args.get('member', type=int) or abort(400))
    items = [M.vessel_item(v) for v in M.member_vessels(cur, member['id'], request.args.get('q'))]
    cur.close()
    return jsonify({'items': items})


@bp.route('/api/logons/public-vessels')
def api_public_vessels():
    h, (conn, cur) = _open()
    items = [M.vessel_item(v) for v in M.public_vessels(cur, h.unit(), request.args.get('q'))]
    cur.close()
    return jsonify({'items': items})


# ---------- public vessels ----------

@bp.route('/vessels')
def vessels_page():
    h, (conn, cur) = _open()
    q = (request.args.get('q') or '').strip()
    rows = M.public_vessels(cur, h.unit(), q)
    cur.close()
    return _list_response('vessels.html', vessels=rows, search=q)


def _vessel_page(cur, h, vessel, failed=None, status=200):
    history = h.history(cur, 'Vessels', vessel['id']) if vessel.get('id') else None
    cur.close()
    return _page('vessel.html', creating=not vessel.get('id'), vessel=vessel, failed=failed or {}, history=history,
                 kind=M.KINDS['public'], labels=M.LABELS), status


@bp.route('/vessels/new', methods=['GET', 'POST'])
def vessels_new():
    h, (conn, cur) = _open()
    if request.method == 'GET':
        return _vessel_page(cur, h, M.blank('public'))
    values = _values('public')
    try:
        vessel_id = M.create_public(cur, values, h.user(), h.unit(), _now())
    except L.Refused as e:
        conn.rollback()
        if _wants_json():
            cur.close()
            return jsonify({'error': str(e), 'fields': getattr(e, 'fields', [])}), 400
        return _vessel_page(cur, h, M.blank('public'), _refused(e, 'public', values), 400)
    conn.commit()
    if _wants_json():
        item = M.vessel_item(M.get(cur, 'vessels', vessel_id))
        cur.close()
        return jsonify({'id': vessel_id, 'item': item})
    cur.close()
    return redirect('/vessel/%d' % vessel_id)


@bp.route('/vessel/<int:vessel_id>', methods=['GET', 'POST'])
def vessel_page(vessel_id):
    """A public vessel. A member's vessel lives on its member's Vessels tab."""
    h, (conn, cur) = _open()
    vessel = M.get(cur, 'public', vessel_id, lock=request.method == 'POST')
    if not vessel:
        abort(404)
    if vessel['unit'] != h.unit():
        abort(403)
    if vessel['memberId']:
        cur.close()
        return redirect('/member/%d#vessels' % vessel['memberId'])
    if request.method == 'GET':
        return _vessel_page(cur, h, vessel)
    values = _values('public')
    try:
        M.save(cur, 'public', vessel, values, h.user(), _now(), request.form.get('version'))
    except (L.Refused, L.Stale) as e:
        conn.rollback()
        return _vessel_page(cur, h, vessel, _refused(e, 'public', values), 409 if isinstance(e, L.Stale) else 400)
    conn.commit()
    cur.close()
    return redirect('/vessel/%d' % vessel_id)
