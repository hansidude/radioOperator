"""
The member and public vessel pages, on the same blueprint as the log.

A member's contacts, vessels, trailers and cars are listed on their tabs through Quackit's shared
record_grid, and each opens on its own page, like a log on from the log. Plain forms: a save posts, a
refusal renders the same page again with the values typed and the boxes that stopped it red (400), or
with the reason when someone else saved first (409); a save goes back to the member on that tab.
"""
from flask import abort, jsonify, make_response, redirect, request

from . import logons as L
from . import members as M
from .routes import _now, _open, _page, bp

TABS = [('details', 'Details', 'person-vcard'), ('contacts', 'Emergency contacts', 'telephone-plus'),
        ('vessels', 'Vessels', 'life-preserver'), ('trailers', 'Trailers', 'truck-flatbed'),
        ('cars', 'Cars', 'car-front'), ('history', 'History', 'clock-history')]
VESSEL_TABS = [('details', 'Details', 'life-preserver'), ('contacts', 'Emergency contacts', 'telephone-plus'),
               ('history', 'History', 'clock-history')]
# What a History is made of: the record's own row, and every row of these tables it holds (history by that key).
HISTORY_SCOPES = (('Members', 'id_', 'Details'), ('EmergencyContacts', 'memberId', 'Emergency contact'),
                  ('Vessels', 'memberId', 'Vessel'), ('Trailers', 'memberId', 'Trailer'), ('Cars', 'memberId', 'Car'))
VESSEL_HISTORY_SCOPES = (('Vessels', 'id_', 'Details'), ('EmergencyContacts', 'vesselId', 'Emergency contact'))


def member_history(cur, h, member_id, scopes=HISTORY_SCOPES):
    """Every change a member (or with VESSEL_HISTORY_SCOPES a public vessel) holds, newest first: its details and
    each record it holds, each event scoped to what it changed. None when the host keeps no history."""
    events = []
    for table, by, scope in scopes:
        got = h.history(cur, table, member_id, by)
        if got is None:
            return None
        for event in got:
            event['scope'] = scope
        events.extend(got)
    events.sort(key=lambda e: (e.get('time') is not None, e.get('time') or 0, e.get('id_') or 0), reverse=True)
    return events


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


def _json_refused(cur, e):
    cur.close()
    return jsonify({'error': str(e), 'fields': getattr(e, 'fields', [])}), 409 if isinstance(e, L.Stale) else 400


def _json_saved(cur, kind, record_id, removed=False):
    """What a save from the log on page's Member / Public vessel tab answers: the record as the log on uses it, so
    the boxes it fills can be refreshed without leaving the page."""
    out = {'id': record_id, 'kind': kind, 'removed': removed}
    if kind == 'member':
        out['member'] = M.member_item(M.get(cur, 'member', record_id))
    elif kind in ('vessels', 'public') and not removed:
        out['item'] = M.vessel_item(M.get(cur, 'vessels', record_id))
    cur.close()
    return jsonify(out)


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
    ctx = _member_context(cur, h, member, failed)
    cur.close()
    return _page('member.html', creating=not member.get('id'), **ctx), status


def _member_context(cur, h, member, failed=None):
    ctx = {'member': member, 'failed': failed or {}, 'kinds': M.KINDS, 'labels': M.LABELS, 'tabs': TABS}
    if member.get('id'):
        ctx['children'] = {kind: M.children(cur, kind, member['id']) for kind in M.CHILDREN}
        ctx['history'] = member_history(cur, h, member['id'])
    return ctx


@bp.route('/member/<int:member_id>/panel')
def member_panel(member_id):
    """The member page's content on its own, for the log on page's Member tab (loaded in place by htmx)."""
    h, (conn, cur) = _open()
    ctx = _member_context(cur, h, _member(cur, h, member_id))
    cur.close()
    return _page('_member_panel.html', **ctx)


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
        if _wants_json():
            return _json_refused(cur, e)
        return _member_page(cur, h, member, _refused(e, 'member', values), 409 if isinstance(e, L.Stale) else 400)
    conn.commit()
    if _wants_json():
        return _json_saved(cur, 'member', member_id)
    cur.close()
    return redirect('/member/%d' % member_id)


def _public_vessel(cur, h, vessel_id, lock=False):
    """A public vessel of this unit, or 404 / 403. A member's vessel is not one."""
    vessel = M.get(cur, 'public', vessel_id, lock)
    if not vessel or vessel['memberId']:
        abort(404)
    if vessel['unit'] != h.unit():
        abort(403)
    return vessel


def _holder(cur, h, owner, owner_id, lock=False):
    """The member or public vessel whose contacts (and for a member, vessels, trailers and cars) these are, and how
    its pages name it and link to it."""
    if owner == 'member':
        row = _member(cur, h, owner_id, lock)
        name = '%s %s %s' % (row['memberNumber'], row['firstName'], row['lastName'])
    else:
        row = _public_vessel(cur, h, owner_id, lock)
        name = row['vesselName'] or row['registration']
    return row, {'type': owner, 'id': row['id'], 'url': '/%s/%d' % (owner, row['id']), 'name': name,
                 'icon': 'person-vcard' if owner == 'member' else 'life-preserver'}


def _child_page(cur, h, holder, kind, row, failed=None, status=200):
    """One contact, vessel, trailer or car: its form, reached from its row on its holder's tab (like a log on from
    the log). `row` is None for a new one."""
    cur.close()
    # ?panel=1: the same form as content for the log on page's Member / Public vessel tab, saved in place.
    template = '_child_record_panel.html' if request.args.get('panel') == '1' else 'child_record.html'
    return _page(template, holder=holder, kind=kind, spec=M.KINDS[kind], record=row or M.blank(kind),
                 creating=row is None, failed=failed or {}, labels=M.LABELS), status


def _kind_for(owner, kind):
    if kind not in M.OWNERS[owner]['kinds']:
        abort(404)


@bp.route('/<any(member, vessel):owner>/<int:owner_id>/<kind>/new')
def child_new(owner, owner_id, kind):
    h, (conn, cur) = _open()
    _kind_for(owner, kind)
    row, holder = _holder(cur, h, owner, owner_id)
    return _child_page(cur, h, holder, kind, None)


@bp.route('/<any(member, vessel):owner>/<int:owner_id>/<kind>', methods=['POST'])
def child_add(owner, owner_id, kind):
    """Add an emergency contact, vessel, trailer or car to a member, or an emergency contact to a public vessel."""
    h, (conn, cur) = _open()
    _kind_for(owner, kind)
    row, holder = _holder(cur, h, owner, owner_id)
    values = _values(kind)
    try:
        child_id = M.add_child(cur, kind, row, values, h.user(), _now(), owner)
    except L.Refused as e:
        conn.rollback()
        if _wants_json():
            return _json_refused(cur, e)
        return _child_page(cur, h, holder, kind, None, _refused(e, kind + '-new', values), 400)
    conn.commit()
    if _wants_json():
        return _json_saved(cur, kind, child_id)
    cur.close()
    return redirect('%s#%s' % (holder['url'], kind))


def _child(cur, h, owner, owner_id, kind, child_id, lock=True):
    _kind_for(owner, kind)
    holder_row, holder = _holder(cur, h, owner, owner_id)
    row = M.get(cur, kind, child_id, lock=lock)
    if not row or row[M.OWNERS[owner]['key']] != holder_row['id']:
        abort(404)
    return holder, row


@bp.route('/<any(member, vessel):owner>/<int:owner_id>/<kind>/<int:child_id>', methods=['GET', 'POST'])
def child_save(owner, owner_id, kind, child_id):
    h, (conn, cur) = _open()
    holder, row = _child(cur, h, owner, owner_id, kind, child_id, lock=request.method == 'POST')
    if request.method == 'GET':
        return _child_page(cur, h, holder, kind, row)
    values = _values(kind)
    try:
        M.save(cur, kind, row, values, h.user(), _now(), request.form.get('version'))
    except (L.Refused, L.Stale) as e:
        conn.rollback()
        if _wants_json():
            return _json_refused(cur, e)
        return _child_page(cur, h, holder, kind, row, _refused(e, '%s-%d' % (kind, child_id), values), 409 if isinstance(e, L.Stale) else 400)
    conn.commit()
    if _wants_json():
        return _json_saved(cur, kind, child_id)
    cur.close()
    return redirect('%s#%s' % (holder['url'], kind))


@bp.route('/<any(member, vessel):owner>/<int:owner_id>/<kind>/<int:child_id>/remove', methods=['POST'])
def child_remove(owner, owner_id, kind, child_id):
    h, (conn, cur) = _open()
    holder, row = _child(cur, h, owner, owner_id, kind, child_id)
    try:
        M.remove(cur, kind, row, h.user(), _now(), request.form.get('version'))
    except (L.Refused, L.Stale) as e:
        conn.rollback()
        if _wants_json():
            return _json_refused(cur, e)
        return _child_page(cur, h, holder, kind, row, _refused(e, '%s-%d' % (kind, child_id), {}), 409 if isinstance(e, L.Stale) else 400)
    conn.commit()
    if _wants_json():
        return _json_saved(cur, kind, child_id, removed=True)
    cur.close()
    return redirect('%s#%s' % (holder['url'], kind))


# ---------- what the log on's shared search picker asks (myMacro_search_picker.html) ----------

@bp.route('/api/logons/members')
def api_members():
    h, (conn, cur) = _open()
    items = [M.member_item(m) for m in M.members(cur, h.unit(), request.args.get('q'))]
    cur.close()
    return jsonify({'items': items})


@bp.route('/api/logons/vessels')
@bp.route('/api/logons/members/<int:member_id>/vessels')
def api_member_vessels(member_id=None):
    """One member's vessels: the second stage of the Member pick (?member=), or the log on form's 🛥️ Vessel button
    for the member already picked (/members/<id>/vessels)."""
    h, (conn, cur) = _open()
    member = _member(cur, h, member_id or request.args.get('member', type=int) or abort(400))
    items = [M.vessel_item(v) for v in M.member_vessels(cur, member['id'], request.args.get('q'))]
    cur.close()
    return jsonify({'items': items})


@bp.route('/api/logons/public-vessels')
def api_public_vessels():
    h, (conn, cur) = _open()
    items = [M.vessel_item(v) for v in M.public_vessels(cur, h.unit(), request.args.get('q'))]
    cur.close()
    return jsonify({'items': items})


@bp.route('/api/logons/all-vessels')
def api_all_vessels():
    """The log on's 🛥️ Vessel picker: every vessel, a member's or public."""
    h, (conn, cur) = _open()
    items = M.vessel_picks(cur, h.unit(), request.args.get('q'))
    cur.close()
    return jsonify({'items': items})


@bp.route('/api/logons/mobiles')
def api_mobiles():
    """The log on's 📱 Mobile picker: members, public vessel owners and emergency contacts by phone."""
    h, (conn, cur) = _open()
    items = M.mobile_picks(cur, h.unit(), request.args.get('q'))
    cur.close()
    return jsonify({'items': items})


@bp.route('/radio/search')
def search_page():
    """One box over every radio record: log ons, members, emergency contacts, vessels, trailers and cars."""
    h, (conn, cur) = _open()
    q = (request.args.get('q') or '').strip()
    found = M.find(cur, h.unit(), q)
    logons = L.records(cur, h.unit(), _now(), h.approaching_minutes, search=q) if len(q) >= 2 else []
    cur.close()
    return _list_response('search.html', search=q, found=found, logons=logons, kinds=M.KINDS, labels=M.LABELS,
                          reference=L.reference)


@bp.route('/logons/who')
def who_badges():
    """The log on form's badges for a pick, drawn by the one macro the page itself uses (_ui.who_badges)."""
    h, (conn, cur) = _open()
    member = _member(cur, h, request.args.get('member', type=int)) if request.args.get('member') else None
    vessel = None
    if request.args.get('vessel'):
        vessel = M.get(cur, 'vessels', request.args.get('vessel', type=int))
        if not vessel:
            abort(404)
        if vessel['unit'] != h.unit() or (vessel['memberId'] or None) != (member['id'] if member else None):
            abort(400)
    cur.close()
    return _page('_who.html', member=member, vessel=vessel)


# ---------- public vessels ----------

@bp.route('/vessels')
def vessels_page():
    h, (conn, cur) = _open()
    q = (request.args.get('q') or '').strip()
    rows = M.public_vessels(cur, h.unit(), q)
    cur.close()
    return _list_response('vessels.html', vessels=rows, search=q)


def _vessel_context(cur, h, vessel, failed=None):
    ctx = {'vessel': vessel, 'failed': failed or {}, 'kind': M.KINDS['public'], 'kinds': M.KINDS, 'labels': M.LABELS,
           'vessel_tabs': VESSEL_TABS, 'history': None, 'children': {'contacts': []}}
    if vessel.get('id'):
        ctx['history'] = member_history(cur, h, vessel['id'], VESSEL_HISTORY_SCOPES)
        ctx['children'] = {'contacts': M.children(cur, 'contacts', vessel['id'], 'vessel')}
    return ctx


def _vessel_page(cur, h, vessel, failed=None, status=200):
    ctx = _vessel_context(cur, h, vessel, failed)
    cur.close()
    return _page('vessel.html', creating=not vessel.get('id'), **ctx), status


@bp.route('/vessel/<int:vessel_id>/panel')
def vessel_panel(vessel_id):
    """A public vessel's page content on its own, for the log on page's Public vessel tab."""
    h, (conn, cur) = _open()
    ctx = _vessel_context(cur, h, _public_vessel(cur, h, vessel_id))
    cur.close()
    return _page('_vessel_panel.html', **ctx)


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
            return _json_refused(cur, e)
        return _vessel_page(cur, h, M.blank('public'), _refused(e, 'public', values), 400)
    conn.commit()
    if _wants_json():
        return _json_saved(cur, 'public', vessel_id)
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
        if _wants_json():
            return _json_refused(cur, e)
        return _vessel_page(cur, h, vessel, _refused(e, 'public', values), 409 if isinstance(e, L.Stale) else 400)
    conn.commit()
    if _wants_json():
        return _json_saved(cur, 'public', vessel_id)
    cur.close()
    return redirect('/vessel/%d' % vessel_id)
