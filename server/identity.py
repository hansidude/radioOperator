"""
Who is this? Section 7 of the spec: cross-verification, tolerant matching, one search.

There is no membership register to check against. The unit's vessel and member records live in a
system this app has no access to, so identity is derived from the unit's own trip history, which
§3.1 allows ("a conceptual model; it does not prescribe separate database tables for each row").

  a vessel      every past trip carrying the same registration, else the same vessel name
  a person      every past trip carrying the same member number, else the same mobile
  an association the two of them appearing on one trip

Putting a real register behind this changes `associations()` and `known()` and nothing else.
That is weaker than a register in one specific way, stated plainly rather than hidden: a value
misheard the same way twice looks corroborated. The evidence shown always says how many past
trips a match rests on, so the operator can judge it.
"""
import re
from datetime import datetime

# Appendix B: reported radio confusions, a candidate heuristic only. Never an exact match (IDV-6).
CONFUSIONS = (
    set('BCDEGPTVZ3'),      # the rhyming "E-set"
    set('MN'),              # nasal
    set('FSX6'),            # sibilant
    set('AJK8'),            # long-A
    set('0O'), set('1IL'), set('5S'), set('2Z'),   # letter/digit collisions
)
KINDS = ('memberNumber', 'registration', 'mobile', 'vesselName')
VESSEL_KINDS = ('registration', 'vesselName')
PERSON_KINDS = ('memberNumber', 'mobile')
# IDV-1: only what the caller supplied on this call corroborates. A value applied from a match does not.
INDEPENDENT = ('call', 'corrected')
OUTCOMES = ('verified', 'conflict', 'partial', 'unverified')


def normalize(kind, raw):
    """The comparable form of an identifier (IDV-9): formatting only, never a character substitution."""
    if kind == 'mobile':
        return re.sub(r'\D', '', raw or '')
    if kind == 'vesselName':
        return re.sub(r'\s+', ' ', raw or '').strip().lower()
    return re.sub(r'[\s\-]', '', raw or '').upper()


def variants(value):
    """Values one radio mishearing away from this one (IDV-6). Each is {value, position, from, to}."""
    out = []
    for i, ch in enumerate(value):
        for group in CONFUSIONS:
            if ch.upper() in group:
                for other in sorted(group):
                    if other != ch.upper():
                        out.append({'value': value[:i] + other + value[i + 1:], 'position': i, 'from': ch, 'to': other})
    return out


# ---------- the unit's own history, read as identity ----------

def vessel_key(row):
    """The vessel a record stands for, or None when nothing identifying has been said yet."""
    if row.get('registration'):
        return 'rego:' + normalize('registration', row['registration'])
    if row.get('vesselName'):
        return 'name:' + normalize('vesselName', row['vesselName'])
    return None


def vessel_label(row):
    """What to call that vessel in a message to an operator."""
    return row.get('registration') or row.get('vesselName') or 'This vessel'


def _keys(row):
    """The vessel and person this past trip stands for, or None where it said nothing."""
    vessel, person = vessel_key(row), None
    if row.get('memberNumber'):
        person = 'member:' + normalize('memberNumber', row['memberNumber'])
    elif row.get('mobile'):
        person = 'mobile:' + normalize('mobile', row['mobile'])
    return vessel, person


def past(cur, unit, exclude_id=None, discarded=False):
    """Every earlier trip of this unit, newest first. The register this app has instead of a register.

    A discarded record was never a log on, so it is not evidence of a boat or a person and is left
    out by default. It stays searchable and auditable, which is why `discarded` exists. A log on
    that never departed is kept: the boat and the caller were real, only the trip was not."""
    from . import logons                 # loaded by now; one definition of how a stored row is typed
    cur.execute('SELECT * FROM LogOns WHERE isActive = 1 AND unit = %s AND id <> %s'
                + ('' if discarded else " AND watchStatus NOT IN ('discarded', 'cancelled')") + ' ORDER BY id DESC',
                (unit, int(exclude_id or 0)))
    rows = [logons._row(r) for r in cur.fetchall() or []]
    for r in rows:
        r['vesselKey'], r['personKey'] = _keys(r)
    return rows


def associations(rows):
    """{(kind, normalized value): {(vesselKey, personKey): [trip ids]}} — what each value has meant before."""
    index = {}
    for r in rows:
        pair = (r['vesselKey'], r['personKey'])
        if pair == (None, None):
            continue
        for kind in KINDS:
            if r.get(kind):
                index.setdefault((kind, normalize(kind, r[kind])), {}).setdefault(pair, []).append(r['id'])
    return index


def known(rows):
    """The vessels and people this unit has seen, each with what it last knew about them."""
    vessels, people = {}, {}
    for r in rows:                                    # rows are newest first, so the first wins
        if r['vesselKey'] and r['vesselKey'] not in vessels:
            vessels[r['vesselKey']] = {'key': r['vesselKey'], 'kind': 'vessel', 'trips': 0,
                                       'label': r.get('registration') or r.get('vesselName'),
                                       'sublabel': r.get('vesselName') if r.get('registration') else None,
                                       'detail': r.get('vesselDetails'), 'lastTrip': r['id'], 'lastSeen': r.get('createdAt')}
        if r['personKey'] and r['personKey'] not in people:
            people[r['personKey']] = {'key': r['personKey'], 'kind': 'person', 'trips': 0,
                                      'label': r.get('memberNumber') or r.get('mobile'),
                                      'sublabel': r.get('mobile') if r.get('memberNumber') else None,
                                      'detail': r.get('contactName'), 'lastTrip': r['id'], 'lastSeen': r.get('createdAt')}
        if r['vesselKey']:
            vessels[r['vesselKey']]['trips'] += 1
        if r['personKey']:
            people[r['personKey']]['trips'] += 1
    return vessels, people


# ---------- resolution and the IDV-2 outcome ----------

def _match(index, kind, value):
    """Exact first, then one mishearing away (IDV-6). Never lets an approximate match call itself exact."""
    if not value:
        return None
    exact = index.get((kind, value))
    if exact:
        return {'how': 'exact', 'pairs': exact}
    for v in variants(value):
        near = index.get((kind, v['value']))
        if near:
            return {'how': 'near', 'pairs': near, 'heard': value, 'suggests': v['value'],
                    'position': v['position'], 'from': v['from'], 'to': v['to']}
    return None


def evidence(cur, logon, identifiers):
    """Each identifier the caller supplied, what it resolves to, and how. Values applied from a
    previous trip are listed but marked as not corroborating (IDV-1)."""
    index = associations(past(cur, logon['unit'], logon['id']))
    seen, out = set(), []
    for row in identifiers:
        if not row['isActive']:
            continue
        # The same characters in two boxes is one thing the caller said, whatever the boxes are called.
        same = row['normalized'].upper()
        independent = row['source'] in INDEPENDENT and same not in seen
        if row['source'] in INDEPENDENT:
            seen.add(same)                           # a normalized duplicate corroborates nothing
        found = _match(index, row['kind'], row['normalized'])
        out.append({'kind': row['kind'], 'raw': row['raw'], 'normalized': row['normalized'], 'source': row['source'],
                    'independent': independent, 'match': found,
                    'pairs': set(found['pairs']) if found and found['how'] == 'exact' else set(),
                    'trips': sorted({t for ids in found['pairs'].values() for t in ids}) if found else []})
    return out


def outcome(ev):
    """The single IDV-2 outcome, in the decision order the spec sets: Conflict, then Unverified,
    then Verified, then Partial. Returns (outcome, reason, the surviving associations)."""
    independent = [e for e in ev if e['independent']]
    resolving = [e for e in independent if e['pairs']]
    common = set.intersection(*[e['pairs'] for e in resolving]) if resolving else set()

    if len(resolving) >= 2 and not common:
        return 'conflict', 'Exact matches point at different boats or people: %s.' % _names(resolving), set()
    if len(independent) < 2:
        return 'unverified', ('Nothing identifying supplied on this call yet; two values that agree are the check.'
                              if not independent else
                              'Only one identifier supplied on this call; two that agree are the check.'), common
    if not resolving:
        return 'unverified', 'No identifier matches anything this unit has logged before.', set()
    if len(resolving) >= 2 and len(common) == 1 and len(resolving) == len(independent) \
            and all(e['match']['how'] == 'exact' for e in independent):
        return 'verified', '%s agree on one boat and person, seen on %d earlier trip%s.' % (
            _names(resolving), _trips(resolving), '' if _trips(resolving) == 1 else 's'), common
    if len(common) > 1:
        return 'partial', 'The identifiers agree, but %d boat and person pairings still fit.' % len(common), common
    unresolved = [e for e in independent if not e['pairs']]
    near = [e for e in independent if e['match'] and e['match']['how'] == 'near']
    why = []
    if near:
        why.append('%s only matches with a letter changed' % _names(near))
    if unresolved and not near:
        why.append('%s matches nothing logged before' % _names(unresolved))
    elif unresolved and near:
        why.append('%s matches nothing logged before' % _names([e for e in unresolved if e not in near]))
    return 'partial', ('; '.join(w for w in why if w) or 'Not enough exact evidence to confirm one boat and person') + '.', common


def _names(items):
    labels = {'memberNumber': 'member number', 'registration': 'registration', 'mobile': 'mobile', 'vesselName': 'vessel name'}
    return ' and '.join(labels[i['kind']] for i in items) or 'nothing'


def _trips(items):
    return len({t for i in items for t in i['trips']})


def verify(cur, logon, identifiers):
    """The stored verification of one log on: outcome, the reason in words, and the evidence behind it."""
    ev = evidence(cur, logon, identifiers)
    name, reason, common = outcome(ev)
    return {'outcome': name, 'basis': reason, 'evidence': ev, 'associations': common}


# ---------- one search box (SRCH-1 to SRCH-6) ----------

def search(cur, unit, q, limit=25):
    """Everything this unit knows that matches `q`: boats, people, trips at sea, and past trips.
    One input, no record type to choose first, partial input, never a hidden truncation."""
    q = (q or '').strip()
    if len(q) < 2:
        return []
    rows = past(cur, unit)                      # discarded records stand for no boat and no person
    vessels, people = known(rows)
    at_sea = [r for r in rows if r['watchStatus'] == 'watching']       # a draft is not at sea
    open_ids = {r['vesselKey'] for r in at_sea} | {r['personKey'] for r in at_sea}
    needle = q.lower()
    loose = normalize('registration', q)
    hits = []
    for group in (vessels, people):
        for key, item in group.items():
            haystack = ' '.join(str(x) for x in (item['label'], item['sublabel'], item['detail']) if x).lower()
            if needle in haystack or (loose and loose in normalize('registration', haystack)):
                hits.append(dict(item, atSea=key in open_ids))
    for r in past(cur, unit, discarded=True):   # but they remain findable, marked for what they are
        text = ' '.join(str(x) for x in (r.get('registration'), r.get('vesselName'), r.get('memberNumber'),
                                         r.get('mobile'), r.get('destination'), r.get('departurePoint')) if x).lower()
        if needle in text or (loose and loose in normalize('registration', text)):
            hits.append({'kind': 'trip', 'key': 'trip:%d' % r['id'], 'id': r['id'],
                         'label': '#%d %s' % (r['id'], r.get('registration') or r.get('vesselName') or r.get('memberNumber') or ''),
                         'sublabel': r.get('destination'), 'detail': r.get('vesselDetails'),
                         'state': r['watchStatus'], 'atSea': r['watchStatus'] == 'watching',
                         'lastTrip': r['id'], 'lastSeen': r.get('createdAt'), 'trips': 1})
    hits.sort(key=lambda h: ({'vessel': 0, 'person': 1, 'trip': 2}[h['kind']], -(h.get('lastTrip') or 0)))
    return hits[:limit]


def profile(cur, unit, key, exclude_id=None):
    """What this unit last knew about a boat or a person: the values a match offers to a new call.
    Trip facts are never included — a past trip does not say where this one is going (SRCH-6)."""
    rows = past(cur, unit, exclude_id)
    if key.startswith('trip:'):
        rows = [r for r in rows if r['id'] == int(key.split(':', 1)[1])]
    else:
        rows = [r for r in rows if key in (r['vesselKey'], r['personKey'])]
    if not rows:
        return None, []
    fields = {}
    for r in rows:                                   # newest first: the most recent value of each wins
        for f in ('registration', 'vesselName', 'memberNumber', 'mobile', 'vesselDetails',
                  'length', 'hullColour', 'vesselType', 'make', 'model', 'ais', 'contactName', 'contactNumber'):
            if r.get(f) and f not in fields:
                fields[f] = r[f]
    return fields, [r['id'] for r in rows]
