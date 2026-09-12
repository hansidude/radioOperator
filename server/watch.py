"""
The thing that is actually watching.

Everything else in this app runs because a browser asked it to. This does not. A draft that nobody
finished and a log on whose return time has passed are both noticed here, on a timer, in one worker,
whether or not anyone has the site open (ACC-5, WAT-3). That is the whole point: a page that goes red
when you look at it is not a watch.

What this provides and what it does not, stated plainly because the difference matters:

  it does      evaluate deadlines on a timer with no browser involved, durably record what became
               due and when, keep raising it until the cause is resolved, resolve it only when the
               cause is resolved, and report whether it is alive
  it does not  deliver anything out of band. `Host.notify` is where a unit's approved channel is
               wired in, and until one is approved an alert reaches a person only when they look at
               the site. Appendix D question 17 is that decision, and until it is answered this
               deployment has not met ACC-5.
"""
import logging
import os
import socket
import threading
import time
from datetime import datetime, timedelta

from . import logons as L

log = logging.getLogger('radio.watch')
DT = '%Y-%m-%d %H:%M:%S'
KINDS = {'draftfollowup': 'An unfinished draft: the caller may believe they are logged on',
         'overdue': 'A vessel is overdue'}


def _s(dt):
    return dt.strftime(DT) if dt else None


def who():
    return '%s/%d' % (socket.gethostname(), os.getpid())


# ---------- what is due ----------

def due_draft_followups(cur, now, minutes):
    """Drafts that have gone unresolved past the unit's follow-up interval (ACC-5).
    Measured from creation: the caller rang off then, not when someone last typed."""
    cutoff = now - timedelta(minutes=int(minutes))
    cur.execute("SELECT * FROM LogOns WHERE isActive = 1 AND watchStatus = 'draft' AND createdAt <= %s", (_s(cutoff),))
    return [(L._row(r), r['createdAt'] + timedelta(minutes=int(minutes))) for r in cur.fetchall() or []]


def due_overdue(cur, now):
    """Accepted log ons whose return time has passed (WAT-3)."""
    cur.execute("SELECT * FROM LogOns WHERE isActive = 1 AND watchStatus = 'watching' AND eta IS NOT NULL AND eta <= %s",
                (_s(now),))
    return [(L._row(r), L._row(r)['eta']) for r in cur.fetchall() or []]


# ---------- the alert record ----------

def open_alerts(cur, unit=None, logon_id=None):
    sql = 'SELECT * FROM Alerts WHERE isActive = 1 AND resolvedAt IS NULL'
    args = []
    if unit is not None:
        sql += ' AND unit = %s'
        args.append(unit)
    if logon_id is not None:
        sql += ' AND logOnId = %s'
        args.append(int(logon_id))
    cur.execute(sql + ' ORDER BY dueAt', tuple(args))
    rows = cur.fetchall() or []
    for r in rows:
        for k in ('dueAt', 'raisedAt', 'notifiedAt', 'acknowledgedAt', 'resolvedAt'):
            r[k] = L._dt(r[k])
    return rows


def raise_alert(cur, row, kind, due, now):
    cur.execute('INSERT INTO Alerts (unit, logOnId, kind, dueAt, raisedAt, notifyCount, isActive) '
                'VALUES (%s, %s, %s, %s, %s, 0, 1)', (row['unit'], row['id'], kind, _s(due), _s(now)))
    return cur.lastrowid


def resolve(cur, alert_id, now, reason):
    cur.execute('UPDATE Alerts SET resolvedAt = %s, resolvedReason = %s WHERE id = %s', (_s(now), reason, alert_id))


def acknowledge(cur, alert_id, user, now):
    """Records that someone saw it. It does not satisfy the obligation or close anything (§2)."""
    cur.execute('UPDATE Alerts SET acknowledgedAt = %s, acknowledgedBy = %s WHERE id = %s AND resolvedAt IS NULL',
                (_s(now), str(user), int(alert_id)))


# ---------- one pass ----------

def sweep(cur, now, followup_minutes, repeat_minutes=None, notify=None):
    """Raise what has become due, resolve what no longer applies, and re-notify what is still open.

    Resolution is derived rather than remembered: an alert stands only while its cause stands, so
    accepting a draft or logging a vessel off clears its alerts on the next pass without every
    action in the app having to remember to do it."""
    repeat_minutes = followup_minutes if repeat_minutes is None else repeat_minutes
    wanted = {}
    for row, due in due_draft_followups(cur, now, followup_minutes):
        wanted[(row['id'], 'draftfollowup')] = (row, due)
    for row, due in due_overdue(cur, now):
        wanted[(row['id'], 'overdue')] = (row, due)

    raised, resolved, notified = [], [], []
    existing = {}
    for a in open_alerts(cur):
        existing[(a['logOnId'], a['kind'])] = a

    for key, alert in existing.items():
        if key not in wanted:
            row = L.get(cur, alert['logOnId'])
            reason = (row or {}).get('watchStatus') or 'withdrawn'
            resolve(cur, alert['id'], now, reason if reason in ('watching', 'loggedoff', 'discarded', 'draft') else 'withdrawn')
            resolved.append(alert['id'])

    for key, (row, due) in wanted.items():
        alert = existing.get(key)
        if alert is None:
            raised.append((raise_alert(cur, row, key[1], due, now), row, key[1]))
            continue
        last = alert['notifiedAt'] or alert['raisedAt']
        if alert['acknowledgedAt'] is None and now - last >= timedelta(minutes=int(repeat_minutes)):
            notified.append((alert, row))

    for alert_id, row, kind in raised:
        _notify(notify, cur, alert_id, row, kind, now)
    for alert, row in notified:
        _notify(notify, cur, alert['id'], row, alert['kind'], now)
    return {'raised': [a for a, _, _ in raised], 'resolved': resolved, 'renotified': [a['id'] for a, _ in notified]}


def _notify(notify, cur, alert_id, row, kind, now):
    cur.execute('UPDATE Alerts SET notifiedAt = %s, notifyCount = notifyCount + 1 WHERE id = %s', (_s(now), alert_id))
    message = '%s: %s %s' % (KINDS[kind], 'draft' if kind == 'draftfollowup' else 'log on', L.reference(row))
    log.warning(message)
    if notify:
        try:
            notify({'alertId': alert_id, 'kind': kind, 'unit': row['unit'], 'logOnId': row['id'],
                    'reference': L.reference(row), 'message': message, 'at': now})
        except Exception:                     # a broken delivery channel must not stop the watching
            log.exception('notify failed for alert %s', alert_id)


# ---------- the lease, so several web workers do not each run it ----------

def take_lease(cur, now, seconds, holder=None):
    holder = holder or who()
    cur.execute("SELECT * FROM WatchHealth WHERE name = 'checker'")
    row = cur.fetchone()
    until = _s(now + timedelta(seconds=seconds))
    if not row:
        cur.execute("INSERT INTO WatchHealth (name, holder, leaseUntil, runs) VALUES ('checker', %s, %s, 0)", (holder, until))
        return True
    cur.execute("UPDATE WatchHealth SET holder = %s, leaseUntil = %s WHERE name = 'checker' "
                'AND (leaseUntil IS NULL OR leaseUntil < %s OR holder = %s)', (holder, until, _s(now), holder))
    cur.execute("SELECT holder FROM WatchHealth WHERE name = 'checker'")
    return (cur.fetchone() or {}).get('holder') == holder


def mark_run(cur, now, error=None):
    cur.execute("UPDATE WatchHealth SET lastRunAt = %s, lastError = %s, runs = runs + 1 WHERE name = 'checker'",
                (_s(now), (str(error)[:255] if error else None)))


def health(cur, now, stale_seconds):
    """Whether anything is watching, in words. A dead checker and a quiet one look the same
    otherwise, so this is shown on the page rather than kept for an administrator."""
    cur.execute("SELECT * FROM WatchHealth WHERE name = 'checker'")
    row = cur.fetchone()
    if not row or not row['lastRunAt']:
        return {'ok': False, 'lastRunAt': None, 'message': 'Nothing has checked deadlines yet.'}
    last = L._dt(row['lastRunAt'])
    age = int((now - last).total_seconds())
    ok = age <= stale_seconds and not row['lastError']
    return {'ok': ok, 'lastRunAt': last, 'ageSeconds': age, 'holder': row['holder'], 'lastError': row['lastError'],
            'message': ('Checked %s ago' % (('%d s' % age) if age < 90 else ('%d min' % (age // 60))))
                       if ok else ('Deadlines have not been checked for %d min. Nothing may be watching.' % (age // 60)
                                   if not row['lastError'] else 'The deadline checker is failing: %s' % row['lastError'])}


# ---------- the timer ----------

class Checker(threading.Thread):
    """One pass every `every` seconds, in whichever worker holds the lease."""

    def __init__(self, host, every=30):
        threading.Thread.__init__(self, name='radio-watch', daemon=True)
        self.host, self.every, self.stop = host, every, threading.Event()

    def run(self):
        while not self.stop.wait(self.every):
            try:
                self.once()
            except Exception:                 # the loop outlives one bad pass; the failure is recorded
                log.exception('watch pass failed')

    def once(self, now=None):
        now = now or datetime.now().replace(microsecond=0)
        conn = self.host.background_connect()
        try:
            cur = conn.cursor()
            # A host's history triggers record who did it, and nothing here is a person. The
            # checker names itself as the system actor rather than leaving that blank, which on
            # quackit's generated triggers would reject every write it makes (REC-2).
            cur.execute('SET @user_id = %s', (self.host.system_actor(),))
            error = None
            try:
                if not take_lease(cur, now, self.every * 3):
                    conn.commit()
                    return None
                out = sweep(cur, now, self.host.draft_followup_minutes,
                            self.host.alert_repeat_minutes, getattr(self.host, 'notify', None))
            except Exception as e:
                error, out = e, None
                raise
            finally:
                try:
                    mark_run(cur, now, error)
                    conn.commit()
                except Exception:
                    log.exception('could not record the watch pass')
            return out
        finally:
            try:
                conn.close()
            except Exception:
                pass


def start(app, host, every=30):
    """Begin watching. Returns None when the host cannot give a connection outside a request, which
    is said out loud rather than silently leaving nothing watching."""
    if not hasattr(host, 'background_connect'):
        log.error('no background connection: nothing will watch deadlines unless a browser is open')
        return None
    checker = Checker(host, every)
    checker.start()
    app.config['RADIO_CHECKER'] = checker
    return checker
