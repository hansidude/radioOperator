"""Shared test fixtures."""

# The member numbers the log on tests say out loud. A Member No. has to be a member record (logons._links);
# these stand for members held before this system issued numbers, so the tests keep their numbers.
MEMBER_NUMBERS = ('1', '2', '3', '1001', '1002', '1003', '4471', '5000', '7788', '8802', '9001', '12345')


def known_members(conn, unit=''):
    cur = conn.cursor()
    for number in MEMBER_NUMBERS:
        cur.execute('INSERT INTO Members (unit, memberNumber, name) VALUES (%s, %s, %s)', (unit, number, 'Member ' + number))
    conn.commit()
