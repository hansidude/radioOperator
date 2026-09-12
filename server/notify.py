"""
Getting an alert in front of a person who is not looking at the screen.

The specification refuses to choose a channel, and rightly: what reaches a volunteer at three in
the morning is the unit's decision, not this file's (Appendix D question 17). What this file does
is make that decision configuration rather than code, and make a channel that has stopped working
visible rather than silent. A pager nobody notices has stopped is worse than no pager.

Three channels, none of them on unless configured:

  webhook   an HTTP POST of the alert as JSON, which is how nearly anything downstream is reached:
            a phone-notification service, a chat room, an SMS gateway, a siren on the bench
  email     plain SMTP, for a unit that has a mail server and a duty address
  log       always on; the application log is a record, not a delivery

A fourth lives in the browser: while a page is open it sounds an alarm and changes the tab title.
That is real delivery to somebody in the room and no delivery at all to anybody else, so it is
labelled that way on the page and counts towards nothing on its own.
"""
import json
import logging
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

log = logging.getLogger('radio.notify')
TIMEOUT = 8


class Undelivered(Exception):
    """No configured channel accepted the alert. The reason is kept against the alert."""


def webhook(url, alert, timeout=TIMEOUT):
    body = json.dumps({k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in alert.items()}).encode()
    request = urllib.request.Request(url, data=body, method='POST',
                                     headers={'Content-Type': 'application/json', 'User-Agent': 'vessel-log-on'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status >= 300:
            raise Undelivered('webhook returned %s' % response.status)


def email(config, alert, timeout=TIMEOUT):
    message = EmailMessage()
    message['Subject'] = alert['message'][:120]
    message['From'] = config['from']
    message['To'] = config['to']
    message.set_content('%s\n\nRaised %s. This is an automatic message from the vessel log on.\n'
                        % (alert['message'], alert.get('at')))
    server = (smtplib.SMTP_SSL if config.get('ssl') else smtplib.SMTP)(config['host'], int(config.get('port') or 25),
                                                                      timeout=timeout)
    try:
        if config.get('starttls'):
            server.starttls()
        if config.get('username'):
            server.login(config['username'], config.get('password') or '')
        server.send_message(message)
    finally:
        try:
            server.quit()
        except Exception:
            pass


def channels(config):
    """The delivery callables a configuration asks for, as (name, send) pairs."""
    out = []
    if config.get('webhook'):
        out.append(('webhook', lambda alert: webhook(config['webhook'], alert)))
    if config.get('email', {}).get('host') and config['email'].get('to'):
        out.append(('email', lambda alert: email(config['email'], alert)))
    return out


def deliver(config, alert):
    """Send to every configured channel. Returns (delivered_names, error_or_None).

    A channel that fails does not stop the others, and failing every channel is not an exception
    the caller has to catch: it is a fact recorded against the alert and shown on the page."""
    wired = channels(config)
    if not wired:
        log.debug('%s (no delivery channel is configured)', alert.get('message'))
        return [], 'No delivery channel is configured'
    sent, failures = [], []
    for name, send in wired:
        try:
            send(alert)
            sent.append(name)
        except Exception as e:
            failures.append('%s: %s' % (name, e))
            log.error('alert delivery failed on %s: %s', name, e)
    if not sent:
        return [], '; '.join(failures)[:255]
    return sent, ('; '.join(failures)[:255] or None)
