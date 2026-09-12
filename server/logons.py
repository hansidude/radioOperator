"""
The data layer: everything the app knows about a log on, as rows.

Pure SQL over `LogOns` and `Identifiers` through a dict cursor. No Flask, no host, no JSON —
so it is unit-testable on SQLite, and so the same functions serve the pages, the API and any
job a host wants to run. Every write that cannot be honoured refuses loudly (`Refused`,
`Stale`) rather than storing something other than what was heard.
"""
import re
from datetime import datetime, timedelta

from . import times

DT = '%Y-%m-%d %H:%M:%S'
OPEN = ('pending', 'watching')          # watch statuses that are on the open queue (§2 Active)
CHANNELS = ('radio', 'phone', 'person', 'self')

# §6.1 field priority classes, in the order the gap list prompts them (CAP-11). Vessel name is not in
# §6.1; it is an Identifier (§2, SRCH-2) and is prompted with class B — confirm with the unit.
CLASSES = (
    ('A', 'Locate the vessel', ('eta', 'pob', 'destination', 'departurePoint', 'departureTime')),
    ('B', 'Identify and verify', ('memberNumber', 'registration', 'mobile', 'vesselName')),
    ('C', 'Reach the vessel', ('radioChannel', 'contactName', 'contactNumber', 'ais')),
    ('D', 'Describe the vessel', ('length', 'hullColour', 'vesselType', 'make', 'model')),
)
LABELS = {
    'eta': 'ETA (return)', 'pob': 'POB', 'destination': 'Destination', 'departurePoint': 'Departure point',
    'departureTime': 'Departure time', 'memberNumber': 'Member number', 'registration': 'Registration',
    'mobile': 'Mobile', 'vesselName': 'Vessel name', 'radioChannel': 'Radio channel', 'contactName': 'Contact (aboard / ashore)',
    'contactNumber': 'Contact number', 'ais': 'AIS / MMSI', 'length': 'Length (m)', 'hullColour': 'Hull colour',
    'vesselType': 'Type', 'make': 'Make', 'model': 'Model', 'channel': 'Channel', 'callTime': 'Call time', 'notes': 'Notes',
}
TIME_FIELDS = {'eta': ('etaRaw', 'eta', 'etaBasis'),
               'departureTime': ('departureRaw', 'departureTime', 'departureBasis'),
               'callTime': ('callTimeRaw', 'callTime', 'callTimeBasis')}
NUMBER_FIELDS = {'pob': 'whole number', 'length': 'number of metres'}
IDENT_FIELDS = ('memberNumber', 'registration', 'mobile', 'vesselName')
RANKED = tuple(f for _, _, fs in CLASSES for f in fs)
FIELDS = RANKED + ('channel', 'callTime', 'notes')
DATETIMES = ('eta', 'departureTime', 'callTime', 'createdAt', 'updatedAt', 'loggedOffAt', 'capturedAt')
RANK = {'overdue': 0, 'approaching': 1, 'nodeadline': 2, 'notdue': 3}


class Refused(Exception):
    """A write the app will not store, with the reason. Hosts turn it into 400 / a message."""


class Stale(Exception):
    """The row changed since the caller last saw it (CAP-22). Hosts turn it into 409."""


# ---------- rows in and out ----------

def _dt(v):
    if v is None or isinstance(v, datetime):
        return v
    return datetime.strptime(str(v)[:19], DT)


def _row(r):
    if r:
        for k in DATETIMES:
            if k in r:
                r[k] = _dt(r[k])
    return r


def _s(dt):
    return dt.strftime(DT) if dt else None


def normalize(kind, raw):
    """The comparable form of an identifier (IDV-9): formatting only, never a character substitution."""
    if kind == 'mobile':
        return re.sub(r'\D', '', raw)
    if kind == 'vesselName':
        return re.sub(r'\s+', ' ', raw).strip().lower()
    return re.sub(r'[\s\-]', '', raw).upper()


# ---------- reading ----------

def get(cur, logon_id, lock=False):
    cur.execute('SELECT * FROM LogOns WHERE id = %s AND isActive = 1' + (' FOR UPDATE' if lock else ''), (logon_id,))
    return _row(cur.fetchone())


def identifiers(cur, logon_id):
    cur.execute('SELECT * FROM Identifiers WHERE logOnId = %s ORDER BY capturedAt, id', (logon_id,))
    return [_row(r) for r in cur.fetchall() or []]


def present(row, field):
    """Has anything been heard for this field? A time counts once its raw expression is there, understood or not."""
    col = TIME_FIELDS[field][0] if field in TIME_FIELDS else field
    return row.get(col) not in (None, '')


def gaps(row):
    """Fields still unpopulated, ranked by class (CAP-10, CAP-11). Advisory only (CAP-12)."""
    return [{'field': f, 'label': LABELS[f], 'cls': cls} for cls, _, fs in CLASSES for f in fs if not present(row, f)]


def condition(row, now, approaching_minutes):
    """The deadline condition (§3.3): nodeadline | notdue | approaching | overdue, plus minutes to go (negative when past)."""
    eta = row['eta']
    if eta is None:
        return 'nodeadline', None
    minutes = int((eta - now).total_seconds() // 60)
    if eta <= now:
        return 'overdue', minutes
    if eta - now <= timedelta(minutes=approaching_minutes):
        return 'approaching', minutes
    return 'notdue', minutes


def queue(cur, unit, now, approaching_minutes):
    """The unit's open watch queue (WAT-1): every open record, Draft or Complete, overdue first, then
    approaching, then records with no usable deadline, then the rest by deadline. Never ETA-only."""
    cur.execute("SELECT * FROM LogOns WHERE isActive = 1 AND unit = %s AND watchStatus IN ('pending', 'watching')", (unit,))
    rows = [_row(r) for r in cur.fetchall() or []]
    for r in rows:
        r['condition'], r['minutes'] = condition(r, now, approaching_minutes)
        r['gaps'] = len(gaps(r))
        r['ageMinutes'] = int((now - r['createdAt']).total_seconds() // 60)
    rows.sort(key=lambda r: (RANK[r['condition']], r['eta'] or r['createdAt']))
    return rows


def recent_closed(cur, unit, limit=20):
    cur.execute("SELECT * FROM LogOns WHERE isActive = 1 AND unit = %s AND watchStatus IN ('loggedoff', 'cancelled') "
                'ORDER BY loggedOffAt DESC, id DESC LIMIT %s', (unit, int(limit)))
    return [_row(r) for r in cur.fetchall() or []]


# ---------- writing ----------

def create(cur, user, unit, now):
    """An empty Draft, owned by the unit and on its queue from this moment (CAP-1, CAP-2, §3.3 Begin capture)."""
    cur.execute('INSERT INTO LogOns (unit, createdBy, createdAt, updatedBy, updatedAt) VALUES (%s, %s, %s, %s, %s)',
                (unit, str(user), _s(now), str(user), _s(now)))
    return cur.lastrowid


def _open_row(cur, logon_id, version):
    row = get(cur, logon_id, lock=True)
    if not row:
        raise Refused('No such log on')
    if row['watchStatus'] not in OPEN:
        raise Refused('This log on is closed (%s). Reopening is an authorised action, not an edit.' % row['watchStatus'])
    if version is not None and int(version) != row['version']:
        raise Stale('Changed by someone else since you loaded it (now version %d, you had %s). Reload to see the current values.' % (row['version'], version))
    return row


def _bump(cur, row, sets, user, now):
    sets = dict(sets, version=row['version'] + 1, updatedBy=str(user), updatedAt=_s(now))
    cur.execute('UPDATE LogOns SET ' + ', '.join('%s = %%s' % k for k in sets) + ' WHERE id = %s', tuple(sets.values()) + (row['id'],))
    return row['version'] + 1


def _reference(row, field):
    """What a time-only or relative expression is read against (REC-6): the call time when known,
    otherwise the entry time; the call time itself is read against the entry time."""
    if field != 'callTime' and row['callTime']:
        return row['callTime'], 'call time'
    return row['createdAt'], 'entry time'


def _record_identifier(cur, logon_id, kind, value, previous, user, now):
    """Every distinct value heard for an identifier is its own row (DAT-5); a change supersedes the last one (IDV-3)."""
    if (value or None) == (previous or None):
        return
    cur.execute('UPDATE Identifiers SET isActive = 0 WHERE logOnId = %s AND kind = %s AND isActive = 1', (logon_id, kind))
    if value:
        cur.execute('INSERT INTO Identifiers (logOnId, kind, raw, normalized, source, capturedBy, capturedAt, isActive) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s, 1)',
                    (logon_id, kind, value, normalize(kind, value), 'corrected' if previous else 'call', str(user), _s(now)))


def set_field(cur, logon_id, field, value, user, now, version=None):
    """One field, in any order, on any open record (CAP-3, CAP-13). Returns what was stored and what to show
    beside the field: {'field', 'value', 'when', 'basis', 'warning', 'version', 'gaps'}."""
    if field not in FIELDS:
        raise Refused('No such field: %s' % field)
    row = _open_row(cur, logon_id, version)
    value = value.strip() if isinstance(value, str) else ('' if value is None else str(value))
    out = {'field': field, 'value': value or None, 'when': None, 'basis': None, 'warning': None}
    if field in TIME_FIELDS:
        raw_col, when_col, basis_col = TIME_FIELDS[field]
        if len(value) > 64:
            raise Refused('%s: more than 64 characters' % LABELS[field])
        ref, label = _reference(row, field)
        got = times.parse(value, ref, label)
        sets = {raw_col: value or None, when_col: _s(got['when']), basis_col: got['basis'] or None}
        out.update(when=got['when'], basis=got['basis'], warning=got['warning'])
        # CAP-5: an ETA before the departure is information, shown beside the field, never a refusal.
        after = dict(row, **{when_col: got['when']})
        if after['eta'] and after['departureTime'] and after['eta'] < after['departureTime'] and not out['warning']:
            out['warning'] = 'ETA %s is before the departure time %s.' % (after['eta'].strftime('%H:%M'), after['departureTime'].strftime('%H:%M'))
    else:
        if field == 'channel' and value and value not in CHANNELS:
            raise Refused('Channel must be one of: ' + ', '.join(CHANNELS))
        if len(value) > (65535 if field == 'notes' else 255):
            raise Refused('%s: too long to store' % LABELS[field])
        sets = {field: value or None}
        if field in NUMBER_FIELDS and value and not re.match(r'^\d+(\.\d+)?$', value):
            out['warning'] = 'Not a %s; kept as heard.' % NUMBER_FIELDS[field]
        if field in IDENT_FIELDS:
            _record_identifier(cur, logon_id, field, value, row[field], user, now)
    out['version'] = _bump(cur, row, sets, user, now)
    out['gaps'] = gaps(dict(row, **sets))
    return out


def accept(cur, logon_id, user, now, version=None):
    """Pending acceptance -> Watching (§3.3 Accept watch). Records who and when; changes nothing else."""
    row = _open_row(cur, logon_id, version)
    if row['watchStatus'] != 'pending':
        raise Refused('Already accepted')
    return _bump(cur, row, {'watchStatus': 'watching'}, user, now)


def set_capture(cur, logon_id, complete, user, now, version=None):
    """Draft <-> Complete. Gaps may remain (CAP-12); monitoring and ownership do not change (§3.3)."""
    row = _open_row(cur, logon_id, version)
    return _bump(cur, row, {'captureStatus': 'complete' if complete else 'draft'}, user, now)


def log_off(cur, logon_id, user, now, note, version=None):
    """Explicit closure of an open record with evidence and time (§3.3 Log off, WAT-7)."""
    row = _open_row(cur, logon_id, version)
    note = (note or '').strip()
    if len(note) > 255:
        raise Refused('Log off note: too long to store')
    return _bump(cur, row, {'watchStatus': 'loggedoff', 'loggedOffAt': _s(now), 'loggedOffNote': note or None}, user, now)
