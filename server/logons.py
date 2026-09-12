"""
The data layer: everything the app knows about a log on, as rows.

Pure SQL over `LogOns` and `Identifiers` through a dict cursor. No Flask, no host, no JSON —
so it is unit-testable on SQLite, and so the same functions serve the pages, the API and any
job a host wants to run. Every write that cannot be honoured refuses loudly (`Refused`,
`Stale`) rather than storing something other than what was heard.

The field set and its order are the unit's paper radio log (spec A.1, DAT-6): `PAPER` is the
row as printed, `EXTRA` is what the system adds after it.

A day is never assumed (CAP-4). Each time is a day cell plus a time cell; without a day there is
no instant, and the trip is simply not time-monitorable (DAT-1) with an accountable follow-up
(WAT-9). A day cell resolves the moment it is written and the date is stored, so a word like
"tomorrow" cannot mean something else when the row is read the next day; the word itself is kept
beside the date as what was heard (REC-6).
"""
import re
from datetime import date, datetime, timedelta

from . import times

DT = '%Y-%m-%d %H:%M:%S'
OPEN = ('pending', 'watching')          # watch statuses that are on the open queue (§2 Active)
CHANNELS = ('radio', 'phone', 'person', 'self')

# The paper log's columns, in its order, under its headings (DAT-6). A column that is a heading
# over several inputs (member number OR vessel name; ETA/ETR day and time) lists them together.
PAPER = (
    ('Date', ('callDay',)),
    ('Time', ('callTime',)),
    ('Member No. OR Vessel Name', ('memberNumber', 'vesselName')),
    ('Vessel Rego. No.', ('registration',)),
    ('Mobile Phone Number', ('mobile',)),
    ('Vessel Details', ('vesselDetails',)),
    ('POB', ('pob',)),
    ('Departure Point', ('departurePoint',)),
    ('Going to', ('destination',)),
    ('ETA/ETR', ('etaDay', 'eta')),
)
MANDATORY = ('memberNumber', 'vesselName', 'registration', 'mobile')   # the paper's shaded columns: obtain before the call ends
# Not on the paper log; shown after it, visibly additional (DAT-6).
EXTRA = (
    ('Call and departure', ('channel', 'departureDay', 'departureTime')),
    ('Reach the vessel', ('radioChannel', 'contactName', 'contactNumber', 'ais')),
    ('Describe the vessel', ('length', 'hullColour', 'vesselType', 'make', 'model')),
    ('Notes', ('notes',)),
)
LABELS = {
    'callDay': 'Date', 'callTime': 'Time', 'memberNumber': 'Member No.', 'vesselName': 'Vessel Name',
    'registration': 'Vessel Rego. No.', 'mobile': 'Mobile Phone Number', 'vesselDetails': 'Vessel Details',
    'pob': 'POB', 'departurePoint': 'Departure Point', 'destination': 'Going to',
    'etaDay': 'Return Day or Date', 'eta': 'Time',
    'channel': 'Channel', 'departureDay': 'Departure day', 'departureTime': 'Departure time', 'radioChannel': 'Radio channel',
    'contactName': 'Contact (aboard / ashore)', 'contactNumber': 'Contact number', 'ais': 'AIS / MMSI',
    'length': 'Length (m)', 'hullColour': 'Hull colour', 'vesselType': 'Type', 'make': 'Make', 'model': 'Model', 'notes': 'Notes',
}
# §6.1 field priority classes, in the order the gap list prompts them (CAP-11). On the paper log
# class D is the one 'Vessel Details' cell; the structured description fields are extras.
CLASSES = (
    ('A', 'Locate the vessel', ('etaDay', 'eta', 'pob', 'destination', 'departurePoint')),
    ('B', 'Identify and verify', ('memberNumber', 'registration', 'mobile', 'vesselName')),
    ('C', 'Reach the vessel', ('radioChannel', 'contactName', 'contactNumber', 'ais')),
    ('D', 'Describe the vessel', ('vesselDetails',)),
)
# Each time: (day as written, day resolved, time as spoken, the instant they make, how it was read).
TIME_FIELDS = {'eta': ('etaDayRaw', 'etaDate', 'etaRaw', 'eta', 'etaBasis'),
               'callTime': ('callDayRaw', 'callDate', 'callTimeRaw', 'callTime', 'callTimeBasis'),
               'departureTime': ('departureDayRaw', 'departureDate', 'departureRaw', 'departureTime', 'departureBasis')}
DAY_FIELDS = {'etaDay': 'eta', 'callDay': 'callTime', 'departureDay': 'departureTime'}
DATES = ('etaDate', 'callDate', 'departureDate')
NUMBER_FIELDS = {'pob': 'whole number', 'length': 'number of metres'}
IDENT_FIELDS = ('memberNumber', 'registration', 'mobile', 'vesselName')
FIELDS = tuple(f for _, fs in PAPER + EXTRA for f in fs)
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


def _d(v):
    if v is None or isinstance(v, date) and not isinstance(v, datetime):
        return v
    return datetime.strptime(str(v)[:10], '%Y-%m-%d').date()


def _row(r):
    if r:
        for k in DATETIMES:
            if k in r:
                r[k] = _dt(r[k])
        for k in DATES:
            if k in r:
                r[k] = _d(r[k])
    return r


def _s(dt):
    return dt.strftime(DT) if dt else None


def _sd(day):
    return day.isoformat() if day else None


def column(field):
    """The column a field's value as heard lives in: a day cell's words, a time cell's words, else itself."""
    if field in DAY_FIELDS:
        return TIME_FIELDS[DAY_FIELDS[field]][0]
    if field in TIME_FIELDS:
        return TIME_FIELDS[field][2]
    return field


def box(row, field):
    """What the input shows. A day cell shows its resolved date once it has one ('Sun 13/9'), so the
    relative word the operator typed is never what anyone reads back; unresolved, it shows the words."""
    if field in DAY_FIELDS:
        day = row.get(TIME_FIELDS[DAY_FIELDS[field]][1])
        if day:
            return times.fmt_day(day, (row.get('createdAt') or datetime.now()).year)
    return row.get(column(field)) or ''


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
    return row.get(column(field)) not in (None, '')


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
        r['callDayBox'], r['etaDayBox'] = box(r, 'callDay'), box(r, 'etaDay')
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


def interpret(row, field, resolve_day=False):
    """Read a time field's day cell and time cell together: {'when', 'day', 'basis', 'warning'}.

    The day is resolved only when the day cell itself is being written (`resolve_day`); after that
    the stored date is used. Re-reading the words would let "tomorrow" drift a day every day."""
    day_raw_col, day_date_col, raw_col, when_col, basis_col = TIME_FIELDS[field]
    ref, label = _reference(row, field)
    written = (row.get(day_raw_col) or '').strip()
    stored = row.get(day_date_col)
    if resolve_day or (written and not stored):
        day = times.parse_day(written, ref)
    elif stored:
        day = {'day': stored, 'label': 'as entered', 'basis': times.fmt_day(stored, ref.year) + ' (as entered)', 'warning': None}
    else:
        day = {'day': None, 'label': '', 'basis': '', 'warning': None}
    if not (row.get(raw_col) or '').strip():
        if day['day'] or day['warning']:
            return dict(day, when=None, basis=day['basis'] + ' — no time yet',
                        warning=day['warning'] or 'A day without a time is not a deadline.')
        return {'when': None, 'day': None, 'basis': '', 'warning': None}
    got = times.parse(row.get(raw_col), ref, label, day=day['day'], day_label=day['label'])
    # a date written inside the time cell ('13/9 0630') fills the day cell too
    got['day'] = day['day'] or (got['when'].date() if got['when'] else None)
    if day['warning'] and not got['warning']:
        got['warning'] = day['warning']
        got['basis'] += ' — ' + day['warning']
    return got


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
    if field in TIME_FIELDS or field in DAY_FIELDS:
        tf = DAY_FIELDS.get(field, field)
        day_raw_col, day_date_col, raw_col, when_col, basis_col = TIME_FIELDS[tf]
        if len(value) > 64:
            raise Refused('%s: more than 64 characters' % LABELS[field])
        after = dict(row, **{column(field): value or None})
        got = interpret(after, tf, resolve_day=field in DAY_FIELDS)
        sets = {column(field): value or None, day_date_col: _sd(got['day']),
                when_col: _s(got['when']), basis_col: got['basis'] or None}
        out.update(when=got['when'], basis=got['basis'], warning=got['warning'])
        if field in DAY_FIELDS:      # the box stops showing the word and shows the date it meant
            out['display'] = times.fmt_day(got['day'], row['createdAt'].year) if got['day'] else value
        # CAP-5: an ETA before the departure is information, shown beside the field, never a refusal.
        after[when_col] = got['when']
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
    """Explicit closure of an open record with evidence and time: the paper's 'Time Arrived or Return' (§3.3, WAT-7)."""
    row = _open_row(cur, logon_id, version)
    note = (note or '').strip()
    if len(note) > 255:
        raise Refused('Log off note: too long to store')
    return _bump(cur, row, {'watchStatus': 'loggedoff', 'loggedOffAt': _s(now), 'loggedOffNote': note or None}, user, now)
