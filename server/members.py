"""
The unit's standing records (spec §3.1 Member / PublicUser and Vessel): members, each with any number
of emergency contacts, vessels, trailers and cars, and public vessels.

A public user has no standing record of their own; for them the vessel is the record, so a public
vessel carries its owner's name and contact details (owner, 2026-09-14). A log on is a member's when
its Member No. names a member here, otherwise it is a public user's (logons._links).

Pure SQL through a dict cursor, like logons.py. A save that cannot be honoured refuses loudly:
`Invalid` names the boxes that are empty or cannot be read, `Stale` says someone else saved first.
Nothing is ever stored half right. Rows are never deleted; removing one makes it inactive, so the
host's history keeps it.
"""
import re

from . import logons as L

MEMBER_PREFIX = 'm'
MEMBER_DIGITS = 5
VESSEL_FIELDS = ('vesselName', 'registration', 'length', 'hullColour', 'vesselType', 'make', 'model', 'ais')

# What each kind of record is, what its boxes are, and what it cannot be saved without. `one_of`: at
# least one of these (a vessel is known by its name or its rego). Vessel boxes share the log on's names
# and labels, because they describe the same boat.
KINDS = {
    'member': {'table': 'Members', 'label': 'Details', 'one': 'member',
               'fields': ('firstName', 'lastName', 'mobile', 'email', 'address', 'notes'), 'required': ('firstName', 'lastName')},
    'contacts': {'table': 'EmergencyContacts', 'label': 'Emergency contacts', 'one': 'emergency contact',
                 'fields': ('name', 'relationship', 'phone', 'email'), 'required': ('name', 'phone')},
    'vessels': {'table': 'Vessels', 'label': 'Vessels', 'one': 'vessel',
                'fields': VESSEL_FIELDS, 'required': (), 'one_of': ('vesselName', 'registration')},
    'trailers': {'table': 'Trailers', 'label': 'Trailers', 'one': 'trailer',
                 'fields': ('registration', 'make', 'model', 'colour'), 'required': ('registration',)},
    'cars': {'table': 'Cars', 'label': 'Cars', 'one': 'car',
             'fields': ('registration', 'make', 'model', 'colour'), 'required': ('registration',)},
    'public': {'table': 'Vessels', 'label': 'Public vessel', 'one': 'public vessel',
               'fields': VESSEL_FIELDS + ('ownerName', 'ownerPhone', 'ownerEmail', 'notes'),
               'required': ('ownerName', 'ownerPhone'), 'one_of': ('vesselName', 'registration')},
}
CHILDREN = ('contacts', 'vessels', 'trailers', 'cars')
# Who holds records of those kinds, and by which column: a member holds all four; a public vessel, whose record
# stands for a public user, holds emergency contacts.
OWNERS = {'member': {'key': 'memberId', 'kinds': CHILDREN}, 'vessel': {'key': 'vesselId', 'kinds': ('contacts',)}}
LONG_TEXT = ('notes',)
LABELS = dict({f: L.LABELS[f] for f in VESSEL_FIELDS if f in L.LABELS},
              vesselName='Vessel Name', registration='Rego', memberNumber='Member No.', name='Name', address='Address',
              firstName='First name', lastName='Last name', mobile=L.LABELS['mobile'],
              phone='Phone', email='Email', relationship='Relationship', colour='Colour', ais='AIS / MMSI',
              ownerName='Owner name', ownerPhone='Owner phone', ownerEmail='Owner email', notes='Notes')
PHONES = ('mobile', 'phone', 'ownerPhone')
EMAILS = ('email', 'ownerEmail')
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class Invalid(L.Refused):
    """A save refused for boxes that are empty or cannot be read. Nothing was written."""

    def __init__(self, kind, fields):
        self.fields = fields
        super().__init__('This %s needs: %s' % (KINDS[kind]['one'], ', '.join(LABELS[f] for f in fields)))


def _clean(kind, values):
    """The columns a save writes, or Invalid naming every box that stops it."""
    spec = KINDS[kind]
    unknown = sorted(set(values) - set(spec['fields']))
    if unknown:
        raise L.Refused('No such field: %s' % unknown[0])
    sets, red = {}, []
    for field in spec['fields']:
        value = (values.get(field) or '').strip()
        if len(value) > (65535 if field in LONG_TEXT else 255):
            raise L.Refused('%s: too long to store' % LABELS[field])
        if field in PHONES and value:
            value, wrong = L.written_mobile(value)       # the log on's rule: 10 digits, written 0412 345 678
            if wrong:
                red.append(field)
        if field in EMAILS and value and not EMAIL.match(value):
            red.append(field)
        if field == 'length' and value and not L.NUMBER.match(value):
            red.append(field)
        if field in spec['required'] and not value:
            red.append(field)
        sets[field] = value or None
    if spec.get('one_of') and not any(sets[f] for f in spec['one_of']):
        red.extend(spec['one_of'])
    if red:
        raise Invalid(kind, sorted(set(red), key=spec['fields'].index))
    return sets


def blank(kind):
    return {field: None for field in KINDS[kind]['fields']}


# ---------- reading ----------

def get(cur, kind, record_id, lock=False):
    cur.execute('SELECT * FROM %s WHERE id = %%s AND isActive = 1%s' % (KINDS[kind]['table'], ' FOR UPDATE' if lock else ''),
                (record_id,))
    return cur.fetchone()


def members(cur, unit, search=None):
    """Every member of this unit, by last then first name, each with the names of their vessels. `search`
    matches the number, either name, mobile, email or any of their vessels' names and regos."""
    cur.execute('SELECT * FROM Members WHERE unit = %s AND isActive = 1 ORDER BY lastName, firstName, memberNumber', (unit,))
    rows = cur.fetchall() or []
    cur.execute('SELECT memberId, vesselName, registration FROM Vessels WHERE unit = %s AND isActive = 1 AND memberId IS NOT NULL '
                'ORDER BY id', (unit,))
    boats = {}
    for v in cur.fetchall() or []:
        boats.setdefault(v['memberId'], []).append(v)
    for r in rows:
        r['vessels'] = boats.get(r['id'], [])
        r['vesselNames'] = ', '.join(v['vesselName'] or v['registration'] for v in r['vessels'])
    return _search(rows, search, ('memberNumber', 'firstName', 'lastName', 'mobile', 'email', 'vesselNames'),
                   extra=lambda r: ' '.join(v['registration'] or '' for v in r['vessels']))


def public_vessels(cur, unit, search=None):
    rows = _vessels(cur, unit, {}, public_only=True)
    return _search(rows, search, VESSEL_FIELDS + ('ownerName', 'ownerPhone', 'ownerEmail'))


# ---------- one search over every radio record (the Search page and the log on's Vessel and Mobile pickers) ----------

def _holder(member=None, vessel=None):
    """Who holds a record, as the pages name it and link to it."""
    if member:
        return {'type': 'member', 'id': member['id'], 'url': '/member/%d' % member['id'],
                'name': '%s %s %s' % (member['memberNumber'], member['firstName'], member['lastName'])}
    return {'type': 'vessel', 'id': vessel['id'], 'url': '/vessel/%d' % vessel['id'],
            'name': vessel.get('vesselName') or vessel.get('registration')}


def _vessels(cur, unit, by_member, public_only=False):
    """This unit's vessels, each with its holder and the page it opens on: a member's vessel on its member."""
    cur.execute('SELECT * FROM Vessels WHERE unit = %s AND isActive = 1' + (' AND memberId IS NULL' if public_only else '') +
                ' ORDER BY vesselName, registration', (unit,))
    rows = []
    for v in cur.fetchall() or []:
        member = by_member.get(v['memberId']) if v['memberId'] else None
        if v['memberId'] and not member:
            continue
        v['holder'] = _holder(member=member) if member else {'type': 'vessel', 'id': v['id'], 'url': '/vessel/%d' % v['id'],
                                                             'name': v.get('ownerName') or 'Public'}
        v['url'] = '/member/%d/vessels/%d' % (member['id'], v['id']) if member else '/vessel/%d' % v['id']
        rows.append(v)
    return rows


def _held(cur, kind, by_member, by_vessel):
    """Every active contact, trailer or car held by this unit's members (or, for contacts, public vessels)."""
    cur.execute('SELECT * FROM %s WHERE isActive = 1 ORDER BY id' % KINDS[kind]['table'])
    rows = []
    for r in cur.fetchall() or []:
        member = by_member.get(r.get('memberId'))
        vessel = by_vessel.get(r.get('vesselId')) if 'vesselId' in r else None
        if not (member or (vessel and not vessel['memberId'])):
            continue
        r['holder'] = _holder(member=member) if member else _holder(vessel=vessel)
        r['url'] = '%s/%s/%d' % (r['holder']['url'], kind, r['id'])
        rows.append(r)
    return rows


SEARCH = {'members': ('memberNumber', 'firstName', 'lastName', 'mobile', 'email', 'address', 'notes', 'vesselNames'),
          'contacts': ('name', 'relationship', 'phone', 'email'),
          'vessels': VESSEL_FIELDS + ('ownerName', 'ownerPhone', 'ownerEmail', 'notes'),
          'trailers': ('registration', 'make', 'model', 'colour'),
          'cars': ('registration', 'make', 'model', 'colour')}


def find(cur, unit, q):
    """Every member, emergency contact, vessel, trailer and car of this unit matching `q` in any of its fields
    (SEARCH, notes included) or its holder's name: {kind: rows}, each row with its holder and url. Log ons are
    found by logons.records. Fewer than two characters finds nothing."""
    q = (q or '').strip()
    if len(q) < 2:
        return {kind: [] for kind in SEARCH}
    everyone = members(cur, unit)
    by_member = {m['id']: m for m in everyone}
    vessels = _vessels(cur, unit, by_member)
    by_vessel = {v['id']: v for v in vessels}
    holder_name = lambda r: r['holder']['name']
    return {'members': _search(everyone, q, SEARCH['members']),
            'contacts': _search(_held(cur, 'contacts', by_member, by_vessel), q, SEARCH['contacts'], extra=holder_name),
            'vessels': _search(vessels, q, SEARCH['vessels'], extra=holder_name),
            'trailers': _search(_held(cur, 'trailers', by_member, by_vessel), q, SEARCH['trailers'], extra=holder_name),
            'cars': _search(_held(cur, 'cars', by_member, by_vessel), q, SEARCH['cars'], extra=holder_name)}


def vessel_picks(cur, unit, q):
    """Every vessel, a member's or public, for the log on's 🛥️ Vessel picker: a member's vessel brings its member."""
    everyone = members(cur, unit)
    by_member = {m['id']: m for m in everyone}
    out = []
    for v in _search(_vessels(cur, unit, by_member), q, SEARCH['vessels'], extra=lambda r: r['holder']['name']):
        item = vessel_item(v)
        member = by_member.get(v['memberId'])
        item['member'] = member_item(member) if member else None
        item['meta'] = v['holder']['name'] if member else 'Public'
        out.append(item)
    return out


def mobile_picks(cur, unit, q):
    """The log on's 📱 Mobile picker: members' mobiles, public vessel owners' phones and emergency contacts' phones
    matching the digits typed. Each says whose number it is and brings the member or public vessel it belongs to."""
    digits = re.sub(r'\D', '', q or '')
    everyone = members(cur, unit)
    by_member = {m['id']: m for m in everyone}
    vessels = _vessels(cur, unit, by_member)
    by_vessel = {v['id']: v for v in vessels}
    matches = lambda number: bool(digits) and digits in re.sub(r'\D', '', number or '')
    out = []
    for m in everyone:
        if matches(m.get('mobile')):
            out.append({'id': 'member-%d' % m['id'], 'primary': m['mobile'], 'secondary': 'Member %s %s %s' % (m['memberNumber'], m['firstName'], m['lastName']),
                        'phone': m['mobile'], 'member': member_item(m), 'vessel': None})
    for v in vessels:
        if not v['memberId'] and matches(v.get('ownerPhone')):
            out.append({'id': 'owner-%d' % v['id'], 'primary': v['ownerPhone'],
                        'secondary': '%s, owner of public vessel %s' % (v.get('ownerName') or 'Owner', v.get('vesselName') or v.get('registration')),
                        'phone': v['ownerPhone'], 'member': None, 'vessel': vessel_item(v)})
    for c in _held(cur, 'contacts', by_member, by_vessel):
        if matches(c.get('phone')):
            member = by_member.get(c.get('memberId'))
            vessel = by_vessel.get(c.get('vesselId'))
            out.append({'id': 'contact-%d' % c['id'], 'primary': c['phone'],
                        'secondary': '%s, emergency contact of %s' % (c['name'], c['holder']['name']),
                        'phone': c['phone'], 'member': member_item(member) if member else None,
                        'vessel': None if member else vessel_item(vessel)})
    return out


def _search(rows, search, fields, extra=None):
    needle = (search or '').strip().lower()
    if not needle:
        return rows
    loose = re.sub(r'[\s\-]', '', needle)           # 0412345678 finds 0412 345 678, ab-123 finds AB123
    out = []
    for r in rows:
        text = ' '.join(str(r[f]) for f in fields if r.get(f)) + ' ' + (extra(r) if extra else '')
        if needle in text.lower() or (loose and loose in re.sub(r'[\s\-]', '', text.lower())):
            out.append(r)
    return out


def children(cur, kind, owner_id, owner='member'):
    """The records of this kind a member (or a public vessel) holds."""
    if kind not in OWNERS[owner]['kinds']:
        raise L.Refused('A %s holds no %s' % (owner, KINDS[kind]['label'].lower()))
    cur.execute('SELECT * FROM %s WHERE %s = %%s AND isActive = 1 ORDER BY id' % (KINDS[kind]['table'], OWNERS[owner]['key']), (owner_id,))
    return cur.fetchall() or []


def by_number(cur, unit, number):
    """The member this unit holds under that Member No., or None. Compared the way identity compares
    member numbers (IDV-9): case, spaces and dashes are formatting."""
    wanted = L.normalize('memberNumber', number)
    if not wanted:
        return None
    cur.execute('SELECT * FROM Members WHERE unit = %s AND isActive = 1', (unit,))
    for r in cur.fetchall() or []:
        if L.normalize('memberNumber', r['memberNumber']) == wanted:
            return r
    return None


def vessel_for(cur, unit, registration, member_id):
    """The one vessel record a log on's rego names: one of its member's vessels, or with no member one
    of the public vessels. None when the rego names none, or more than one (never a guess)."""
    wanted = L.normalize('registration', registration)
    if not wanted:
        return None
    if member_id:
        cur.execute('SELECT id, registration FROM Vessels WHERE unit = %s AND isActive = 1 AND memberId = %s', (unit, member_id))
    else:
        cur.execute('SELECT id, registration FROM Vessels WHERE unit = %s AND isActive = 1 AND memberId IS NULL', (unit,))
    found = [v['id'] for v in cur.fetchall() or [] if L.normalize('registration', v['registration']) == wanted]
    return found[0] if len(found) == 1 else None


def member_item(m):
    """A member as the shared search picker shows it ({id, primary, secondary}), with what the log on takes from it."""
    return {'id': m['id'], 'primary': '%s %s %s' % (m['memberNumber'], m['firstName'], m['lastName']),
            'secondary': ' · '.join(x for x in (m.get('mobile'), m.get('vesselNames')) if x),
            'memberNumber': m['memberNumber'], 'name': '%s %s' % (m['firstName'], m['lastName']), 'mobile': m.get('mobile')}


def vessel_item(v):
    """A vessel as the shared search picker shows it, with the log on boxes it fills."""
    length = ('%sm' % v['length']) if v.get('length') else None
    return {'id': v['id'], 'primary': v.get('vesselName') or v.get('registration'),
            'secondary': ' · '.join(x for x in (v.get('registration') if v.get('vesselName') else None, length, v.get('hullColour'),
                                                v.get('make'), v.get('model'), v.get('ownerName')) if x),
            'fields': {f: v.get(f) for f in ('vesselName', 'registration', 'length', 'hullColour', 'make', 'model', 'ownerPhone')}}


def member_vessels(cur, member_id, search=None):
    return _search(children(cur, 'vessels', member_id), search, VESSEL_FIELDS)


# ---------- writing ----------

def _stamp(user, now):
    return {'createdBy': str(user), 'createdAt': L._s(now), 'updatedBy': str(user), 'updatedAt': L._s(now), 'version': 0}


def _insert(cur, table, sets):
    columns = list(sets)
    cur.execute('INSERT INTO %s (%s) VALUES (%s)' % (table, ', '.join(columns), ', '.join(['%s'] * len(columns))),
                tuple(sets[c] for c in columns))
    return cur.lastrowid


def create_member(cur, values, user, unit, now):
    """A new member, with the next member number (m00001, one running sequence), allocated under a lock
    and retried on a unique clash like the trip reference."""
    sets = dict(_clean('member', values), unit=unit, **_stamp(user, now))
    for _ in range(5):
        try:
            return _insert(cur, 'Members', dict(sets, memberNumber=L.next_ref(cur, 'Members', 'memberNumber', MEMBER_PREFIX,
                                                                              MEMBER_DIGITS, 'member number')))
        except Exception as e:
            if not L._clash(e):
                raise
    raise L.Refused('Could not allocate a member number after several attempts')


def add_child(cur, kind, holder, values, user, now, owner='member'):
    """Add a contact, vessel, trailer or car to a member, or a contact to a public vessel (`owner`)."""
    if kind not in OWNERS[owner]['kinds']:
        raise L.Refused('A %s holds no %s' % (owner, KINDS[kind]['label'].lower()))
    sets = dict(_clean(kind, values), **_stamp(user, now))
    sets[OWNERS[owner]['key']] = holder['id']
    if kind == 'vessels':
        sets['unit'] = holder['unit']
    return _insert(cur, KINDS[kind]['table'], sets)


def create_public(cur, values, user, unit, now):
    return _insert(cur, 'Vessels', dict(_clean('public', values), unit=unit, memberId=None, **_stamp(user, now)))


def _bump(cur, kind, row, sets, user, now, version):
    if version is None or str(version) == '':
        raise L.Refused('A save must say which version it saw')
    if int(version) != row['version']:
        raise L.Stale('Changed by someone else since you loaded it (now version %d, you had %s). Reload to see the current values.'
                      % (row['version'], version))
    sets = dict(sets, version=row['version'] + 1, updatedBy=str(user), updatedAt=L._s(now))
    cur.execute('UPDATE %s SET %s WHERE id = %%s' % (KINDS[kind]['table'], ', '.join('%s = %%s' % k for k in sets)),
                tuple(sets.values()) + (row['id'],))
    return sets['version']


def save(cur, kind, row, values, user, now, version):
    """One whole form as one update (and so one history event). A version that is not the stored one is refused."""
    return _bump(cur, kind, row, _clean(kind, values), user, now, version)


def remove(cur, kind, row, user, now, version):
    """Take a contact, vessel, trailer or car off its member. The row stays, inactive, with its history."""
    if kind not in CHILDREN:
        raise L.Refused('No such record kind: %s' % kind)
    return _bump(cur, kind, row, {'isActive': 0}, user, now, version)
