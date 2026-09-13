"""
The data layer: everything the app knows about a log on, as rows.

Pure SQL over `LogOns` and `Identifiers` through a dict cursor. No Flask, no host, no JSON —
so it is unit-testable on SQLite, and so the same functions serve the pages, the API and any
job a host wants to run. Every write that cannot be honoured refuses loudly (`Refused`,
`Stale`) rather than storing something other than what was heard.

The field set and its order are the unit's paper radio log (spec A.1, DAT-6): `PAPER` is the
row as printed, `EXTRA` is what the system adds after it.

A day is never assumed (CAP-4). Each time is a day cell plus a time cell; without a day there is
no instant. A day cell resolves the moment it is written and the date is stored, so a word like
"tomorrow" cannot mean something else when the row is read the next day; the word itself is kept
beside the date as what was heard (REC-6).

Nothing is watched until the log on is accepted (§5.3). A draft holds what was heard and is not
counted down; acceptance needs the mandatory set (ACC-1) and no other open log on for the vessel
(ACC-6), and it starts the watch from that instant (ACC-4). A draft that was never a log on is
discarded; a log on that happened is logged off (ACC-7).
"""
import re
from datetime import date, datetime, timedelta

from . import identity, times

DT = '%Y-%m-%d %H:%M:%S'
# Stored status words renamed by the owner on 2026-09-13. rename_statuses converts rows written before;
# remove it and this map once every database has been converted.
STATUS_RENAMES = {'watching': 'loggedOn', 'loggedoff': 'loggedOff'}
OPEN = ('draft', 'loggedOn')            # a record still on someone's hands: unaccepted, or being watched
CLOSED = ('loggedOff', 'discarded', 'cancelled')     # cancelled is superseded; rows written under it remain
# Anything that is neither watched nor closed is treated as a draft and chased. A state this version
# does not know about, left by an earlier one or by a hand-edited row, must be conspicuous rather
# than invisible: a record in limbo is exactly the thing nobody is counting down.
NOT_CLOSED = "watchStatus NOT IN ('loggedOn', 'loggedOff', 'discarded', 'cancelled')"
CHANNELS = ('radio', 'phone', 'person', 'self')
# Why a log on ended. A trip that never sailed is still a log on that happened, so it is logged
# off like any other; only the reason differs (§3.3).
CLOSE_REASONS = (('returned', 'The vessel returned'), ('notdeparted', 'It never departed'), ('other', 'Something else'))

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
# ACC-1: what a log on cannot be accepted without. Two of the four identity values rather than all
# four, because agreement between two independently supplied ones is the unit's accuracy check.
IDENTITY_SET = ('memberNumber', 'vesselName', 'registration', 'mobile')
IDENTITY_NEEDED = 2
TRIP_SET = ('pob', 'departurePoint', 'destination', 'eta')
MANDATORY = IDENTITY_SET + TRIP_SET
# Not on the paper log; shown after it, visibly additional (DAT-6).
EXTRA = (
    ('Call and departure', ('channel', 'departureDay', 'departureTime')),
    ('Reach the vessel', ('radioChannel', 'contactName', 'contactNumber', 'ais')),
    ('Describe the vessel', ('length', 'hullColour', 'vesselType', 'make', 'model')),
    ('Notes', ('notes',)),
)
LABELS = {
    'callDay': 'Date', 'callTime': 'Time', 'memberNumber': 'Member No.', 'vesselName': 'Vessel Name',
    'registration': 'Vessel Rego. No.', 'mobile': 'Mobile Phone Number', 'vesselDetails': 'Other vessel details',
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
DATES = ('etaDate', 'callDate', 'departureDate', 'dayDate')
NUMBER_FIELDS = {'pob': 'whole number', 'length': 'number of metres'}
IDENT_FIELDS = ('memberNumber', 'registration', 'mobile', 'vesselName')
FIELDS = tuple(f for _, fs in PAPER + EXTRA for f in fs)
DATETIMES = ('eta', 'departureTime', 'callTime', 'createdAt', 'updatedAt', 'acceptedAt', 'loggedOffAt',
             'discardedAt', 'cancelledAt', 'reopenedAt', 'capturedAt')
RANK = {'overdue': 0, 'approaching': 1, 'nodeadline': 2, 'notdue': 3, 'notwatched': 4}


class Refused(Exception):
    """A write the app will not store, with the reason. Hosts turn it into 400 / a message."""


class InvalidDraft(Refused):
    """A draft save missing the unit's minimum identifying call details."""

    def __init__(self, fields):
        self.fields = fields
        super().__init__('A draft needs a valid date, time, and one of member number, vessel rego or mobile')


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


def reference(row):
    """How an operator names this record out loud: "log on 50", not a database key (REC-9)."""
    if row.get('dayNumber') is None:
        return '#%d' % row['id']
    return '%d' % row['dayNumber']


def column(field):
    """The column a field's value as heard lives in: a day cell's words, a time cell's words, else itself."""
    if field in DAY_FIELDS:
        return TIME_FIELDS[DAY_FIELDS[field]][0]
    if field in TIME_FIELDS:
        return TIME_FIELDS[field][2]
    return field


# The history viewer's names for LogOns columns: each form label on the column its value is stored in,
# the two Time boxes told apart, and the record's own state and interpretation columns.
HISTORY_LABELS = dict({column(f): LABELS[f] for f in FIELDS},
                      callTimeRaw='Call time', etaDayRaw='Return day', etaRaw='Return time', departureRaw='Departure time',
                      callDate='Call date (read)', callTime='Call time (read)', callTimeBasis='Call time reading',
                      etaDate='Return date (read)', eta='Return deadline', etaBasis='Return time reading',
                      departureDate='Departure date (read)', departureTime='Departure time (read)', departureBasis='Departure reading',
                      watchStatus='Status', dayNumber='No.', dayDate='Day', tripRef='Trip ID No.',
                      acceptedAt='Logged on at', acceptedBy='Logged on by', loggedOffAt='Logged off at',
                      loggedOffNote='Log off note', closeReason='Log off reason', discardedAt='Discarded at',
                      discardReason='Discard reason', cancelledAt='Cancelled at', cancelReason='Cancel reason',
                      duplicateOf='Duplicate of', reopenedAt='Reopened at', reopenReason='Reopen reason',
                      verifyOutcome='Identity check', verifyBasis='Identity check basis', createdBy='Entered by',
                      createdAt='Entered at', isActive='Active', unit='Unit')


def resolved_day(row, field):
    """The date a day cell settled on: the stored date, or for a row written before that column
    existed, the date of the instant it already produced. Never the words read again."""
    day_raw_col, day_date_col, raw_col, when_col, basis_col = TIME_FIELDS[DAY_FIELDS.get(field, field)]
    return row.get(day_date_col) or (row[when_col].date() if row.get(when_col) else None)


def written_mobile(value):
    """(what to store, whether it is wrong) for a mobile number. Exactly 10 digits, spaces anywhere
    ignored, is written 0412 345 678. Anything else (9 or 11 digits, +61, letters) is kept as heard and
    is wrong, so its box is red (CAP-23: never invent, never drop what was heard)."""
    digits = re.sub(r'\s+', '', value or '')
    if not digits:
        return '', False
    if not re.fullmatch(r'\d{10}', digits):
        return value, True
    return '%s %s %s' % (digits[:4], digits[4:7], digits[7:]), False


def box(row, field):
    """What the input shows. A day cell shows the date it settled on ('Sun 13/9') and a time cell the
    time ('1400'), so the words the operator typed are never what anyone reads back; unresolved, it
    shows the words."""
    if field in DAY_FIELDS:
        day = resolved_day(row, field)
        if day:
            return times.fmt_day(day)
    if field == 'mobile':
        return written_mobile(row.get('mobile'))[0]     # a number saved before the format reads 0412 345 678 too
    if field in TIME_FIELDS and row.get(field):
        return times.fmt_time(row[field])       # a time it settled on reads back as 4-digit 24-hour: '929' shows 0929
    if field in TIME_FIELDS and present(row, field):
        clock = interpret(row, field).get('clock')
        if clock:                               # understood but no day yet: '3pm' still reads 1500
            return clock
    return row.get(column(field)) or ''


normalize = identity.normalize      # one definition of "the same value", shared with resolution (IDV-9)


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


def missing(row):
    """What stops this being accepted (ACC-1): the values still needed, in the paper log's order.
    A draft is never refused for these; acceptance is the only thing withheld (ACC-8)."""
    have = [f for f in IDENTITY_SET if row.get(f)]
    out = []
    # 'boxes' are the inputs the form turns red for each entry: the empty identity boxes, or the
    # return day and/or time that has not settled into a deadline.
    if len(have) < IDENTITY_NEEDED:
        out.append({'field': 'identity', 'label': '%d more of Member No., Vessel Name, Rego or Mobile'
                    % (IDENTITY_NEEDED - len(have)), 'got': have,
                    'boxes': [f for f in IDENTITY_SET if f not in have]})
    for field in TRIP_SET:
        if field == 'eta':
            if not row.get('eta'):
                boxes = [] if resolved_day(row, 'etaDay') else ['etaDay']
                if boxes == [] or not present(row, 'eta'):
                    boxes.append('eta')
                out.append({'field': 'eta', 'label': 'A return day and time that reads as a deadline', 'boxes': boxes})
        elif not row.get(field):
            out.append({'field': field, 'label': LABELS[field], 'boxes': [field]})
    return out


def acceptable(row):
    return not missing(row)


def condition(row, now, approaching_minutes):
    """The deadline condition of an accepted log on (§3.3): notdue | approaching | overdue, and the
    minutes to go. A draft is not watched, so it has no condition at all (ACC-2)."""
    if row['watchStatus'] != 'loggedOn':
        return 'notwatched', None
    eta = row['eta']
    if eta is None:
        return 'nodeadline', None
    minutes = int((eta - now).total_seconds() // 60)
    if eta <= now:
        return 'overdue', minutes
    if eta - now <= timedelta(minutes=approaching_minutes):
        return 'approaching', minutes
    return 'notdue', minutes


def _decorate(rows, now, approaching_minutes):
    for r in rows:
        r['condition'], r['minutes'] = condition(r, now, approaching_minutes)
        r['gaps'] = len(gaps(r))
        r['missing'] = missing(r)
        r['ageMinutes'] = int((now - r['createdAt']).total_seconds() // 60)
        r['callDayBox'], r['etaDayBox'] = box(r, 'callDay'), box(r, 'etaDay')
        r['callTimeBox'], r['etaBox'], r['mobileBox'] = box(r, 'callTime'), box(r, 'eta'), box(r, 'mobile')
    return rows


# One collection, four filters. A status is a property of a record, not a reason to keep four
# queries, four sorts and four renderers. Overdue is the exception that has to be applied after the
# fetch: it is not a column but a reading of the deadline against now (see condition()).
STATUS_WHERE = {
    'draft': NOT_CLOSED,
    'loggedon': "watchStatus = 'loggedOn'",
    'overdue': "watchStatus = 'loggedOn'",
    'closed': 'watchStatus IN (' + ', '.join("'%s'" % state for state in CLOSED) + ')',
}
# What Find searches. The trip reference and the day number are how an operator refers to a record
# out loud, so both have to be findable alongside the vessel's identifying values.
SEARCH_FIELDS = ('tripRef', 'dayNumber', 'memberNumber', 'vesselName', 'registration', 'mobile', 'destination')


SORTS = ('newest', 'oldest', 'due')


def records(cur, unit, now, approaching_minutes, status=None, day=None, search=None, sort='newest'):
    """The radio log, filtered. `status` is one of STATUS_WHERE or None for every record; `day` limits
    to one call date; `search` matches any of SEARCH_FIELDS; `sort` is one of SORTS.

    Newest first by default, which is the paper log read from the bottom up: the call that just came
    in is the one being worked on. Order is by the call time, never by the entry time, so a delayed
    paper record entered tonight sits where it was called, not at the top (REC-2)."""
    if status is not None and status not in STATUS_WHERE:
        raise Refused('No such status filter: %r' % status)
    if sort not in SORTS:
        raise Refused('No such sort: %r' % sort)
    where = 'SELECT * FROM LogOns WHERE isActive = 1 AND unit = %s'
    args = [unit]
    if status is not None:
        where += ' AND ' + STATUS_WHERE[status]
    if day is not None:
        where += ' AND callDate = %s'
        args.append(_sd(day))
    cur.execute(where, tuple(args))
    rows = _decorate([_row(r) for r in cur.fetchall() or []], now, approaching_minutes)
    if status == 'overdue':
        rows = [r for r in rows if r['condition'] == 'overdue']
    if search:
        needle = str(search).strip().lower()
        spaceless = re.sub(r'\s+', '', needle)          # 0412345678 finds 0412 345 678
        rows = [r for r in rows
                if any(needle in str(r[field]).lower() or (field == 'mobile' and spaceless in re.sub(r'\s+', '', str(r[field])))
                       for field in SEARCH_FIELDS if r.get(field) is not None)]
    rows.sort(key=lambda r: (r['callTime'] or r['createdAt'], r['id']), reverse=sort != 'oldest')
    return due_first(rows) if sort == 'due' else rows


def due_first(rows):
    """The watch order (WAT-1): overdue first, then by deadline. What is not watched (drafts, closed) has
    no deadline and follows in the order it came in. One rule for the log's Due first sort and queue()."""
    rows.sort(key=lambda r: (RANK[r['condition']], r['eta'] or r['createdAt'])
              if r['condition'] != 'notwatched' else (RANK['notwatched'], datetime.min))
    return rows


def queue(cur, unit, now, approaching_minutes):
    """The open watch queue (WAT-1): the accepted log ons this unit is watching, overdue first, then
    approaching, then by deadline. Drafts are not in it, because a draft is not a watch (ACC-2).

    The watch order is the queue's own: it is a worklist, not the log. The log's own order is
    records()."""
    return due_first(records(cur, unit, now, approaching_minutes, status='loggedon'))


def drafts(cur, unit, now, approaching_minutes, day=None):
    """Saved drafts, oldest first: the oldest unaccepted call is the one that needs chasing."""
    return records(cur, unit, now, approaching_minutes, status='draft', day=day, sort='oldest')


def recent_closed(cur, unit, now, approaching_minutes, limit=20):
    """The most recently closed records, newest first. Decorated like every other row -- the old
    version was not, which is why a closed record had no callDayBox or etaDayBox to render."""
    rows = records(cur, unit, now, approaching_minutes, status='closed')
    rows.sort(key=lambda r: r['id'], reverse=True)
    return rows[:int(limit)]


# ---------- writing ----------

TRIP_PREFIX = 'T-'
TRIP_DIGITS = 5


def _clash(e):
    """A unique-index rejection, which is retried, as opposed to a real fault, which is not."""
    text = str(e).lower()
    return 'uniq' in text or 'unique' in text or 'duplicate' in text


def _next_day_number(cur, unit, day):
    """The next day number for that unit and that call date (REC-9): what the operator says out
    loud, counting from 1 each day.

    Two operators saving at the same moment must not be handed the same number, so the read of the
    highest so far takes a row lock and the caller retries if a unique index rejects the write
    anyway. Both are needed: the lock is the real defence, because a host may apply this schema with
    the uniqueness dropped (quackit's migration generator emits CREATE INDEX for a CREATE UNIQUE
    INDEX), and the retry covers the hosts where the constraint does exist."""
    cur.execute('SELECT COALESCE(MAX(dayNumber), 0) + 1 AS n FROM LogOns WHERE unit = %s AND dayDate = %s '
                'FOR UPDATE', (unit, day))
    return cur.fetchone()['n']


def _next_trip_ref(cur):
    """The next trip reference: the paper log's 'Trip ID No.', one running sequence across every
    unit and every day, and the record's key.

    Zero-padded to a fixed width so the text order is the number order, which is what lets MAX()
    find the highest without the database having to know the format. Locked and retried like the day
    number above. The state-wide system issues these across all units; this branch allocates its own,
    so two branches will eventually meet in the middle -- that is a reconciliation to do with a
    branch prefix, not something to paper over here."""
    cur.execute('SELECT MAX(tripRef) AS m FROM LogOns FOR UPDATE')
    highest = (cur.fetchone() or {}).get('m')
    if highest is None:
        nxt = 1
    else:
        if not highest.startswith(TRIP_PREFIX) or not highest[len(TRIP_PREFIX):].isdigit():
            raise Refused('The highest trip reference in the database is %r, which is not %s plus digits. '
                          'Refusing to guess the next one.' % (highest, TRIP_PREFIX))
        nxt = int(highest[len(TRIP_PREFIX):]) + 1
    if nxt >= 10 ** TRIP_DIGITS:
        raise Refused('Trip references have run past %s%s. The width has to grow before another can be issued.'
                      % (TRIP_PREFIX, '9' * TRIP_DIGITS))
    return '%s%0*d' % (TRIP_PREFIX, TRIP_DIGITS, nxt)


def create(cur, user, unit, now):
    """An empty draft, owned by the unit from this moment and chased until it is accepted or
    discarded (CAP-1, CAP-2, ACC-5). It is not watched and it is not a log on.

    The operator's path is create_saved(): nothing is stored until an explicit save passes the draft
    minimum. This remains for tests and for any host that wants a bare row."""
    day = now.date().isoformat()
    for _ in range(5):
        number = _next_day_number(cur, unit, day)
        trip = _next_trip_ref(cur)
        try:
            # watchStatus is written, never left to the column default: a host that applied an earlier
            # version of this schema still carries that version's default, and an ALTER that adds
            # columns does not change one. A row must not depend on what the database happens to think.
            cur.execute('INSERT INTO LogOns (unit, watchStatus, dayDate, dayNumber, tripRef, createdBy, createdAt, updatedBy, updatedAt) '
                        "VALUES (%s, 'draft', %s, %s, %s, %s, %s, %s, %s)",
                        (unit, day, number, trip, str(user), _s(now), str(user), _s(now)))
        except Exception as e:                       # only a clash on that index is retried; anything else is a real fault
            if not _clash(e):
                raise
            continue
        return cur.lastrowid
    raise Refused('Could not allocate a number for today after several attempts')


def rename_statuses(cur):
    """Convert statuses stored under their old words, once: LogOns.watchStatus and Alerts.resolvedReason.
    Matched in Python, exactly, because MariaDB compares text without case and 'loggedOff' would
    otherwise match 'loggedoff' again, and write a history event, on every pass. Returns rows changed."""
    changed = 0
    for table, col in (('LogOns', 'watchStatus'), ('Alerts', 'resolvedReason')):
        cur.execute('SELECT id, %s FROM %s WHERE %s IN (%s)' % (col, table, col, ', '.join(['%s'] * len(STATUS_RENAMES))),
                    tuple(STATUS_RENAMES))
        for row in cur.fetchall() or []:
            new = STATUS_RENAMES.get(row[col])
            if new:
                cur.execute('UPDATE %s SET %s = %%s WHERE id = %%s' % (table, col), (new, row['id']))
                changed += 1
    return changed


def blank(now, unit='', call_day=None):
    """An unsaved browser form. It is deliberately not a database record."""
    row = {field: None for field in FIELDS}
    for columns in TIME_FIELDS.values():
        for column_name in columns:
            row[column_name] = None
    row.update(id=None, unit=unit, watchStatus='draft', dayNumber=None, dayDate=call_day,
               callDayRaw=_sd(call_day), callDate=call_day, version=0, createdAt=now, updatedAt=now,
               createdBy='', updatedBy='', verifyOutcome='unverified', verifyBasis='')
    return row


def _prepare_fields(row, values):
    """Validate and interpret one explicit form save without writing anything. `required` lists the
    draft minimum still absent; the caller decides whether that refuses a save or only turns boxes red."""
    if not isinstance(values, dict):
        raise Refused('expected fields')
    unknown = sorted(set(values) - set(FIELDS))
    if unknown:
        raise Refused('No such field: %s' % unknown[0])

    clean, sets, after, invalid, displays = {}, {}, dict(row), [], {}
    for field, raw in values.items():
        value = raw.strip() if isinstance(raw, str) else ('' if raw is None else str(raw))
        if len(value) > (65535 if field == 'notes' else 255):
            raise Refused('%s: too long to store' % LABELS[field])
        if field == 'channel' and value and value not in CHANNELS:
            raise Refused('Channel must be one of: ' + ', '.join(CHANNELS))
        if field == 'mobile':
            value, wrong = written_mobile(value)
            if wrong:
                invalid.append(field)
        clean[field] = value
        col = column(field)
        sets[col] = value or None
        after[col] = value or None
        if field in NUMBER_FIELDS and value and not re.match(r'^\d+(\.\d+)?$', value):
            invalid.append(field)

    day_for = {target: source for source, target in DAY_FIELDS.items()}
    for time_field in ('callTime', 'departureTime', 'eta'):
        day_field = day_for[time_field]
        if time_field not in clean and day_field not in clean:
            continue
        got = interpret(after, time_field, resolve_day=day_field in clean)
        day_raw_col, day_date_col, raw_col, when_col, basis_col = TIME_FIELDS[time_field]
        parsed = {day_date_col: _sd(got['day']), when_col: _s(got['when']), basis_col: got['basis'] or None}
        sets.update(parsed)
        after.update({day_date_col: got['day'], when_col: got['when'], basis_col: got['basis'] or None})
        displays[day_field] = times.fmt_day(got['day']) if got['day'] else clean.get(day_field, '')
        if got['invalid']:
            invalid.extend(f for f in (day_field, time_field) if f in clean)

    required = []
    if row['watchStatus'] == 'draft':
        if not after.get('callDate'):
            required.append('callDay')
        if not after.get('callTime'):
            required.append('callTime')
        if not any(after.get(field) for field in ('memberNumber', 'registration', 'mobile')):
            required.extend(('memberNumber', 'registration', 'mobile'))
    return sets, after, sorted(set(invalid)), displays, required


def check_fields(row, values):
    """The boxes the form's current values turn red or orange, writing nothing: the draft minimum, what cannot be
    read, and on a draft what still stops acceptance (ACC-1). The page asks this as focus leaves a box,
    so there is one rule, here, and not a second copy in the browser."""
    sets, after, invalid, displays, required = _prepare_fields(row, values)
    red = set(required) | set(invalid)
    if row['watchStatus'] == 'draft':
        for m in missing(after):
            red.update(m['boxes'])
    # The paper's "Member No. or Vessel Name": with one heard, the other is worth asking for. Orange
    # blocks nothing, and a box already red stays red.
    pair = ('memberNumber', 'vesselName')
    heard = [field for field in pair if after.get(field)]
    orange = [field for field in pair if len(heard) == 1 and field not in heard and field not in red]
    return {'red': sorted(red), 'orange': orange}


def form_values(row):
    """What the form's boxes hold when the page opens, so its first red is the same check as later."""
    return {field: box(row, field) for field in FIELDS}


def save_fields(cur, logon_id, values, user, now, version=None):
    """Save one whole operator form as one LogOns update and therefore one host history event."""
    row = _open_row(cur, logon_id, version)
    sets, after, invalid, displays, required = _prepare_fields(row, values)
    if required:
        raise InvalidDraft(required)
    for field in IDENT_FIELDS:
        if field in values:
            _record_identifier(cur, logon_id, field, after.get(field), row.get(field), user, now)
    sets.update(_verify_sets(cur, row, sets))
    if row['watchStatus'] == 'draft' and after['callDate'] != row.get('dayDate'):
        # The day number follows the call date, not the entry date, so a delayed paper record entered
        # tonight still numbers against the day it was called in (REC-9). The trip reference does not
        # move: it was issued once and it is the record's key.
        sets.update(dayDate=_sd(after['callDate']),
                    dayNumber=_next_day_number(cur, row['unit'], _sd(after['callDate'])))
    sets.update(acceptance(cur, after, user, now))       # a complete draft is logged on by this save (ACC-3)
    saved_version = _bump(cur, row, sets, user, now)
    return {'version': saved_version, 'invalid': invalid, 'displays': displays, 'gaps': gaps(after),
            'accepted': sets.get('watchStatus') == 'loggedOn'}


def create_saved(cur, values, user, unit, now):
    """Create the first durable draft only after the explicit form save passes its minimum."""
    row = blank(now, unit)
    sets, after, invalid, displays, required = _prepare_fields(row, values)
    if required:
        raise InvalidDraft(required)
    day = after['callDate']

    synthetic = [{'kind': field, 'raw': after[field], 'normalized': normalize(field, after[field]),
                  'source': 'call', 'isActive': 1}
                 for field in IDENT_FIELDS if after.get(field)]
    verification_result = identity.verify(cur, dict(after, id=0, unit=unit), synthetic)
    sets.update(unit=unit, watchStatus='draft', dayDate=_sd(day),
                verifyOutcome=verification_result['outcome'], verifyBasis=verification_result['basis'][:255],
                createdBy=str(user), createdAt=_s(now), updatedBy=str(user), updatedAt=_s(now), version=0)
    sets.update(acceptance(cur, dict(after, id=0, unit=unit, watchStatus='draft'), user, now))   # complete on its first save (ACC-3)

    # This is the moment the record gets its numbers: the save passed the draft minimum, so it is a
    # real record now. Both are read under a lock and the insert is retried on a unique clash.
    logon_id = None
    for _ in range(5):
        attempt = dict(sets, dayNumber=_next_day_number(cur, unit, _sd(day)), tripRef=_next_trip_ref(cur))
        columns = list(attempt)
        try:
            cur.execute('INSERT INTO LogOns (' + ', '.join(columns) + ') VALUES (' + ', '.join(['%s'] * len(columns)) + ')',
                        tuple(attempt[column_name] for column_name in columns))
        except Exception as e:
            if not _clash(e):
                raise
            continue
        logon_id = cur.lastrowid
        break
    if logon_id is None:
        raise Refused('Could not allocate a day number and trip reference after several attempts')
    for field in IDENT_FIELDS:
        if after.get(field):
            _record_identifier(cur, logon_id, field, after[field], None, user, now)
    return {'id': logon_id, 'version': 0, 'invalid': invalid, 'displays': displays,
            'accepted': sets.get('watchStatus') == 'loggedOn'}


def _open_row(cur, logon_id, version):
    row = get(cur, logon_id, lock=True)
    if not row:
        raise Refused('No such log on')
    if row['watchStatus'] in CLOSED:
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
    settled = row.get(day_date_col) or (row[when_col].date() if row.get(when_col) else None)
    if resolve_day:
        day = times.parse_day(written, ref, warn_before=field != 'callTime')
    elif settled:
        day = {'day': settled, 'label': 'day cell', 'basis': times.fmt_day(settled) + ' (day cell)',
               'warning': None, 'invalid': False}
    elif written:
        day = times.parse_day(written, ref, warn_before=field != 'callTime')  # written but never resolved: read it now, once
    else:
        day = {'day': None, 'label': '', 'basis': '', 'warning': None, 'invalid': False}
    if not (row.get(raw_col) or '').strip():
        if day['day'] or day['warning']:
            return dict(day, when=None, basis=day['basis'] + ' — no time yet')
        return {'when': None, 'day': None, 'basis': '', 'warning': None, 'invalid': False}
    got = times.parse(row.get(raw_col), ref, label, day=day['day'], day_label=day['label'],
                      warn_past=field != 'callTime')
    # a date written inside the time cell ('13/9 0630') fills the day cell too
    got['day'] = day['day'] or (got['when'].date() if got['when'] else None)
    if day['warning'] and not got['warning']:
        got['warning'] = day['warning']
        got['basis'] += ' — ' + day['warning']
    got['invalid'] = got['invalid'] or day['invalid']
    return got


def _record_identifier(cur, logon_id, kind, value, previous, user, now, source=None):
    """Every distinct value heard for an identifier is its own row (DAT-5); a change supersedes the last one (IDV-3).
    `source` says where it came from, because a value applied from an earlier trip corroborates nothing (IDV-1)."""
    if (value or None) == (previous or None):
        return
    cur.execute('UPDATE Identifiers SET isActive = 0 WHERE logOnId = %s AND kind = %s AND isActive = 1', (logon_id, kind))
    if value:
        cur.execute('INSERT INTO Identifiers (logOnId, kind, raw, normalized, source, capturedBy, capturedAt, isActive) '
                    'VALUES (%s, %s, %s, %s, %s, %s, %s, 1)',
                    (logon_id, kind, value, normalize(kind, value), source or ('corrected' if previous else 'call'), str(user), _s(now)))


def verification(cur, row):
    """Recomputed from the evidence as it stands now, never edited by hand (IDV-3)."""
    return identity.verify(cur, row, identifiers(cur, row['id']))


def _verify_sets(cur, row, sets):
    """The stored outcome that goes with this change (IDV-4). Verification follows the evidence."""
    got = verification(cur, dict(row, **sets))
    return {'verifyOutcome': got['outcome'], 'verifyBasis': got['basis'][:255]}


def set_field(cur, logon_id, field, value, user, now, version=None):
    """One field, in any order, on any open record (CAP-3, CAP-13). Returns what was stored and what to show
    beside the field: {'field', 'value', 'when', 'basis', 'warning', 'version', 'gaps'}."""
    if field not in FIELDS:
        raise Refused('No such field: %s' % field)
    row = _open_row(cur, logon_id, version)
    value = value.strip() if isinstance(value, str) else ('' if value is None else str(value))
    out = {'field': field, 'value': value or None, 'when': None, 'basis': None,
           'warning': None, 'invalid': False}
    if field in TIME_FIELDS or field in DAY_FIELDS:
        tf = DAY_FIELDS.get(field, field)
        day_raw_col, day_date_col, raw_col, when_col, basis_col = TIME_FIELDS[tf]
        if len(value) > 64:
            raise Refused('%s: more than 64 characters' % LABELS[field])
        after = dict(row, **{column(field): value or None})
        got = interpret(after, tf, resolve_day=field in DAY_FIELDS)
        sets = {column(field): value or None, day_date_col: _sd(got['day']),
                when_col: _s(got['when']), basis_col: got['basis'] or None}
        out.update(when=got['when'], basis=got['basis'], warning=got['warning'], invalid=got['invalid'])
        if field in DAY_FIELDS:      # the box stops showing the word and shows the date it meant
            out['display'] = times.fmt_day(got['day']) if got['day'] else value
        # CAP-5: an ETA before the departure is information, shown beside the field, never a refusal.
        after[when_col] = got['when']
        if after['eta'] and after['departureTime'] and after['eta'] < after['departureTime'] and not out['warning']:
            out['warning'] = 'ETA %s is before the departure time %s.' % (times.fmt_time(after['eta']), times.fmt_time(after['departureTime']))
    else:
        if field == 'channel' and value and value not in CHANNELS:
            raise Refused('Channel must be one of: ' + ', '.join(CHANNELS))
        if len(value) > (65535 if field == 'notes' else 255):
            raise Refused('%s: too long to store' % LABELS[field])
        if field == 'mobile':
            value, out['invalid'] = written_mobile(value)
            out['value'] = value or None
        sets = {field: value or None}
        if field in NUMBER_FIELDS and value and not re.match(r'^\d+(\.\d+)?$', value):
            out['warning'] = 'Not a %s; kept as heard.' % NUMBER_FIELDS[field]
            out['invalid'] = True
        if field in IDENT_FIELDS:
            _record_identifier(cur, logon_id, field, value, row[field], user, now)
            sets.update(_verify_sets(cur, row, sets))
    out['version'] = _bump(cur, row, sets, user, now)
    out['gaps'] = gaps(dict(row, **sets))
    return out


def open_for_vessel(cur, unit, row):
    """The accepted log on this unit already holds for this vessel, if there is one (ACC-6).
    A vessel is either out or it is not; two open log ons mean the same call twice, or a trip
    that was never closed."""
    key = identity.vessel_key(row)
    if not key:
        return None
    cur.execute("SELECT * FROM LogOns WHERE isActive = 1 AND unit = %s AND watchStatus = 'loggedOn' AND id <> %s",
                (unit, row['id']))
    for other in [_row(r) for r in cur.fetchall() or []]:
        if identity.vessel_key(other) == key:
            return other
    return None


def acceptance(cur, row, user, now):
    """What a save adds to take the watch (ACC-3): Draft -> Watching, recorded against the saving
    operator and time. Empty while the record stays as it is: not a draft, short of the mandatory set
    (ACC-1), or its vessel already out on another log on (ACC-6, the draft keeps everything). Deadlines
    count from this save, so a return time already past is overdue at once (ACC-4)."""
    if row['watchStatus'] != 'draft' or missing(row) or open_for_vessel(cur, row['unit'], row):
        return {}
    return {'watchStatus': 'loggedOn', 'acceptedAt': _s(now), 'acceptedBy': str(user)}


def accept(cur, logon_id, user, now, version=None):
    """Take the watch on a stored record now, or say why not. The form never calls this: its save
    applies `acceptance` in the same update. This is the same transition for the logic's own tests
    and tools, with the reason spelled out when it is refused."""
    row = _open_row(cur, logon_id, version)
    if row['watchStatus'] == 'loggedOn':
        raise Refused('This log on is already accepted and being watched')
    short = missing(row)
    if short:
        raise Refused('Not enough to accept a log on yet. Still needed: %s.' % '; '.join(m['label'] for m in short))
    other = open_for_vessel(cur, row['unit'], row)
    if other:
        raise Refused('%s is already logged on as %s. Open that record instead, or log it off first '
                      'if that trip has ended.' % (identity.vessel_label(row), reference(other)))
    return _bump(cur, row, acceptance(cur, row, user, now), user, now)


def discard(cur, logon_id, user, now, reason, version=None):
    """Throw away a draft that was never a log on (ACC-7): begun in error, or abandoned before
    anything identifying was given. An accepted log on can never be discarded; it is logged off.
    The record stays, searchable and auditable, and counts as evidence of no vessel or person."""
    row = _open_row(cur, logon_id, version)
    if row['watchStatus'] == 'loggedOn':
        raise Refused('This is an accepted log on. A log on that happened is logged off, not discarded.')
    reason = (reason or '').strip()
    if not reason:
        raise Refused('Discarding needs a reason: what makes this not a log on?')
    if len(reason) > 255:
        raise Refused('Discard reason: too long to store')
    return _bump(cur, row, {'watchStatus': 'discarded', 'discardedAt': _s(now), 'discardReason': reason}, user, now)


def reopen(cur, logon_id, user, now, reason, version=None):
    """Correct a closure made in error (§3.3). The closure event is preserved, not erased: the record
    goes back on the queue under this unit's watch, and a deadline that has already passed is overdue
    again from this moment, because time did not stop while the record was shut."""
    row = get(cur, logon_id, lock=True)
    if not row:
        raise Refused('No such log on')
    if row['watchStatus'] in OPEN:
        raise Refused('This log on is already open')
    reason = (reason or '').strip()
    if not reason:
        raise Refused('Reopening needs a reason: what was wrong with the closure?')
    if len(reason) > 255:
        raise Refused('Reopening reason: too long to store')
    if version is not None and int(version) != row['version']:
        raise Stale('Changed by someone else since you loaded it (now version %d, you had %s).' % (row['version'], version))
    # A reopened record goes back to being watched: whoever reopens it is taking it on. A discarded
    # one returns as a draft, because discarding said it was never a log on.
    back = 'draft' if row['watchStatus'] == 'discarded' else 'loggedOn'
    if back == 'loggedOn':
        other = open_for_vessel(cur, row['unit'], row)
        if other:
            raise Refused('%s is already logged on as %s, so this one cannot be reopened as a watch.'
                          % (identity.vessel_label(row), reference(other)))
    return _bump(cur, row, {'watchStatus': back, 'reopenedAt': _s(now), 'reopenReason': reason}, user, now)


def log_off(cur, logon_id, user, now, note, reason='returned', version=None):
    """End the watch on an accepted log on, with the time, the evidence and the reason: the paper's
    'Time Arrived or Return' (§3.3, WAT-7). Every reason ends this way, the vessel having returned
    or never departed, because a log on that happened is logged off."""
    row = _open_row(cur, logon_id, version)
    if row['watchStatus'] != 'loggedOn':
        raise Refused('This is a draft, not a log on. Finish and accept it, or discard it.')
    reason = (reason or 'returned').strip()
    if reason not in dict(CLOSE_REASONS):
        raise Refused('Log off reason must be one of: ' + ', '.join(k for k, _ in CLOSE_REASONS))
    note = (note or '').strip()
    if len(note) > 255:
        raise Refused('Log off note: too long to store')
    return _bump(cur, row, {'watchStatus': 'loggedOff', 'loggedOffAt': _s(now),
                            'loggedOffNote': note or None, 'closeReason': reason}, user, now)


def apply_profile(cur, logon_id, key, user, now, version=None):
    """Put what the unit already knew about this boat or person onto the call in progress (SRCH-6).

    Only empty fields are filled, so nothing the caller just said is overwritten, and no trip fact
    is ever taken from an earlier trip. Applied identifiers are marked as coming from a profile, so
    they cannot corroborate the ones the caller supplied (IDV-1)."""
    row = _open_row(cur, logon_id, version)
    fields, trips = identity.profile(cur, row['unit'], key, logon_id)
    if not fields:
        raise Refused('Nothing known about that yet')
    sets, filled = {}, []
    for field, value in fields.items():
        if field in FIELDS and not row.get(field):
            sets[field] = value
            filled.append(LABELS.get(field, field))
            if field in IDENT_FIELDS:
                _record_identifier(cur, logon_id, field, value, row[field], user, now, source='profile')
    if not sets:
        raise Refused('Everything it knows is already on this record')
    sets.update(_verify_sets(cur, row, sets))
    return {'version': _bump(cur, row, sets, user, now), 'filled': filled, 'fromTrips': trips[:5]}
