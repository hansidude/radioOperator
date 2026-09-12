"""
Times the way operators say and write them, read against a stated reference instant.

`parse` never guesses (CAP-4, CAP-8, CAP-23, REC-6). What it cannot read stays raw with the
reason. **A day is never assumed**: a time with no day is a time, not an instant, and says so —
blank does not silently mean today. An hour that could be morning or afternoon is read as
24-hour and says so. A resolved day is a date from that moment on, so "tomorrow" written on
Saturday stays Sunday when the row is read on Monday.

Forms read: `1500` `15:00` `3pm` `3:30pm` `0730 tomorrow` `12/9 1500` `2026-09-12 15:00`
and, relative to the reference, `+2h` `+90m` `+2h30` `+1:30`.
"""
import re
from datetime import date, datetime, timedelta

_H = r'(?:h|hr|hrs|hour|hours)'
_M = r'(?:m|min|mins|minute|minutes)'
_REL_H = re.compile(r'^\+\s*(\d{1,3})\s*' + _H + r'\s*(?:(\d{1,2})\s*' + _M + r'?)?$')
_REL_M = re.compile(r'^\+\s*(\d{1,4})\s*' + _M + r'$')
_REL_HM = re.compile(r'^\+\s*(\d{1,2})[:.](\d{2})$')
_DATE_ISO = re.compile(r'(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)')
_DATE_DMY = re.compile(r'(?<!\d)(\d{1,2})/(\d{1,2})(?:/(\d{2}|\d{4}))?(?!\d)')
_T_HM = re.compile(r'^(\d{1,2})[:.](\d{2})\s*(am|pm)?$')
_T_DIGITS = re.compile(r'^(\d{3,4})\s*(am|pm)?$')
_T_H = re.compile(r'^(\d{1,2})\s*(am|pm)$')
_T_BARE = re.compile(r'^\d{1,2}$')

FMT = '%a %d %b %H:%M'


def _no(raw, why):
    return {'when': None, 'basis': 'Not understood: %s. Kept as typed: "%s".' % (why, raw),
            'warning': 'Not understood: ' + why, 'invalid': True}


_WEEKDAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


def fmt_day(day, this_year=None):
    """A resolved day as the day box and the queue show it: 'Sun 13/9', with the year when it differs.
    This is what replaces the word the operator typed, so nothing relative is ever stored or re-read."""
    if day is None:
        return ''
    out = '%s %d/%d' % (day.strftime('%a'), day.day, day.month)
    return out if this_year is None or day.year == this_year else out + '/%02d' % (day.year % 100)


def parse_day(raw, reference, warn_before=True):
    """The paper log's 'Return Day or Date' cell on its own:
    {'day': date or None, 'label': how it was given, 'basis', 'warning'}.

    Reads today, tomorrow, a weekday name (the next one, today included), a date (13/9, 13/9/26,
    2026-09-13), and a weekday written in front of a date ('Sun 13/9') — that last form is what the
    box shows once a day is resolved, so whatever is displayed can always be typed back in."""
    text = (raw or '').strip()
    if not text:
        return {'day': None, 'label': '', 'basis': '', 'warning': None, 'invalid': False}

    def no(why):
        return {'day': None, 'label': '', 'basis': 'Not understood: %s. Kept as typed: "%s".' % (why, text),
                'warning': 'Not understood: ' + why, 'invalid': True}

    s = re.sub(r'\s+', ' ', text.lower()).strip('.,')
    day, basis = None, ''
    if s in ('today', 'tdy'):
        day, basis = reference.date(), 'today'
    elif s in ('tomorrow', 'tmrw', 'tmw', 'tmr'):
        day, basis = reference.date() + timedelta(days=1), 'tomorrow'
    else:
        # A weekday word on its own is the day; in front of a date it only labels it ('Sun 13/9').
        m = re.match(r'^(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s*(.*)$', s)
        if m and not m.group(2).strip():
            ahead = (_WEEKDAYS.index(m.group(1)) - reference.weekday()) % 7
            day, basis = reference.date() + timedelta(days=ahead), ('today' if ahead == 0 else 'next %s' % m.group(1).capitalize())
        elif m:
            s = m.group(2).strip()
    if day is None:
        m = _DATE_ISO.fullmatch(s) or _DATE_DMY.fullmatch(s)
        if not m:
            return no('not a day or date')
        try:
            if m.re is _DATE_ISO:
                day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            else:
                year = m.group(3)
                year = reference.year if year is None else (int(year) + 2000 if len(year) == 2 else int(year))
                day = date(year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return no('not a calendar date')
        basis = 'date given'
    warning = 'Before today. Check the date.' if warn_before and day < reference.date() else None
    return {'day': day, 'label': basis,
            'basis': '%s (%s)' % (day.strftime('%a %d %b'), basis) + (' \u2014 ' + warning if warning else ''),
            'warning': warning, 'invalid': False}


def parse(raw, reference, reference_label='entry time', day=None, day_label=None, warn_past=True):
    """{'when': datetime or None, 'basis': how it was read, 'warning': what to check or None}.

    `reference` is the instant relative and time-only forms are read against (REC-6: the call
    time when known, otherwise the entry time); `reference_label` names it in the basis text.
    `day` is the paper log's separate day cell already read by `parse_day`; it wins over a day
    written inside the time."""
    text = (raw or '').strip()
    if not text:
        return {'when': None, 'basis': '', 'warning': None, 'invalid': False}
    s = re.sub(r'\s+', ' ', text.lower())

    # ---- relative: so many hours and minutes after the reference ----
    for rx, to_delta in ((_REL_H, lambda m: timedelta(hours=int(m.group(1)), minutes=int(m.group(2) or 0))),
                         (_REL_M, lambda m: timedelta(minutes=int(m.group(1)))),
                         (_REL_HM, lambda m: timedelta(hours=int(m.group(1)), minutes=int(m.group(2))))):
        m = rx.match(s)
        if m:
            delta = to_delta(m)
            if delta.total_seconds() <= 0:
                return _no(text, 'a zero interval')
            if delta > timedelta(days=14):
                return _no(text, 'more than 14 days ahead; give a date instead')
            when = reference + delta
            h, rem = divmod(int(delta.total_seconds()), 3600)
            basis = '%s after the %s %s = %s' % (('%d h %d min' % (h, rem // 60)) if rem else ('%d h' % h), reference_label, reference.strftime(FMT), when.strftime(FMT))
            warning = 'A relative time ignores the return day cell (%s).' % day_label if day is not None else None
            return {'when': when, 'basis': basis + (' — ' + warning if warning else ''),
                    'warning': warning, 'invalid': False}
    if s.startswith('+'):
        return _no(text, 'say +2h, +30m or +1:30')

    # ---- absolute: an optional day, then a time ----
    if day is not None:
        day_label = day_label or 'day given'
    elif 'tomorrow' in s:
        day, day_label = reference.date() + timedelta(days=1), 'tomorrow'
        s = s.replace('tomorrow', ' ')
    elif 'today' in s:
        day, day_label = reference.date(), 'today'
        s = s.replace('today', ' ')
    m = _DATE_ISO.search(s)
    if m:
        try:
            day = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return _no(text, 'not a calendar date')
        day_label, s = 'date given', s[:m.start()] + ' ' + s[m.end():]
    m = _DATE_DMY.search(s)
    if m and day is None:
        year = m.group(3)
        year = reference.year if year is None else (int(year) + 2000 if len(year) == 2 else int(year))
        try:
            day = date(year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return _no(text, 'not a calendar date (day/month)')
        day_label, s = 'date given', s[:m.start()] + ' ' + s[m.end():]
    s = s.strip()
    if not s:
        return _no(text, 'a date without a time')

    ampm, ambiguous = None, False
    m = _T_HM.match(s)
    if m:
        hour, minute, ampm = int(m.group(1)), int(m.group(2)), m.group(3)
        ambiguous = ampm is None and hour <= 12
    else:
        m = _T_DIGITS.match(s)
        if m:
            digits, ampm = m.group(1), m.group(2)
            hour, minute = int(digits[:-2]), int(digits[-2:])
            ambiguous = ampm is None and len(digits) == 3      # 330 could be 3:30 either way; 0330 could not
        else:
            m = _T_H.match(s)
            if m:
                hour, minute, ampm = int(m.group(1)), 0, m.group(2)
            elif _T_BARE.match(s):
                return _no(text, '"%s" alone could be %s00, %sam or %spm' % (s, s.zfill(2), s, s))
            else:
                return _no(text, 'not a time')
    if ampm:
        if not 1 <= hour <= 12:
            return _no(text, 'hour %d with %s' % (hour, ampm))
        hour = hour % 12 + (12 if ampm == 'pm' else 0)
    if hour > 23 or minute > 59:
        return _no(text, 'hour %d, minute %02d is not a time of day' % (hour, minute))

    # CAP-4: no day, no instant. Blank never means today.
    if day is None:
        return {'when': None,
                'basis': 'Read as %02d:%02d, but no day yet. Fill the day cell. Kept as typed: "%s".' % (hour, minute, text),
                'warning': None, 'invalid': False}
    when = datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)
    basis = '%s (%s)' % (when.strftime(FMT), day_label)
    warning = None
    if warn_past and when < reference:
        warning = 'Already past the %s (%s).' % (reference_label, reference.strftime('%a %d %b %H:%M'))
    elif ambiguous:
        warning = 'Read as 24-hour %02d:%02d. Say %d:%02dpm if you mean the afternoon.' % (hour, minute, hour, minute)
    if warning:
        basis += ' — ' + warning
    return {'when': when, 'basis': basis, 'warning': warning, 'invalid': False}
