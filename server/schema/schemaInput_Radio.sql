-- Vessel log on (vessel-logon-spec.md). The host applies this file: in quackit, Admin -> Database
-- management generates these tables plus their history tables and triggers; standalone runs the
-- same CREATEs on SQLite or MariaDB without triggers. No foreign keys out of these two tables.

-- One row per trip (§3.1 LogOn). Every fact is a column; an unsupplied fact stays NULL (CAP-2, CAP-4).
-- `unit` is the watch owner: an opaque tag from the host ('' when there is one unit).
-- Columns follow the paper radio log (spec A.1, DAT-6): its day and time are separate cells. Each
-- time therefore keeps four things (REC-6): the day as written, the day resolved to a real date, the
-- time as spoken, and the instant the two make together, plus the basis of that reading. A day is
-- never assumed: no day cell, no instant, and the trip is not time-monitorable (DAT-1, WAT-9). Numbers that could arrive as words (POB, length) are kept as
-- heard rather than refused (CAP-23).
CREATE TABLE IF NOT EXISTS `LogOns` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `unit` VARCHAR(64) NOT NULL DEFAULT '',
  `captureStatus` VARCHAR(16) NOT NULL DEFAULT 'draft',       -- draft | complete (§3.3; never gates monitoring)
  `watchStatus` VARCHAR(16) NOT NULL DEFAULT 'pending',       -- pending | watching | loggedoff | cancelled
  `channel` VARCHAR(16) DEFAULT NULL,                         -- radio | phone | person | self (OC-1)
  `callDayRaw` VARCHAR(64) DEFAULT NULL,                      -- paper column 1 'Date', as written ('today', '12/9')
  `callDate` DATE DEFAULT NULL,                               -- that day resolved when it was written; never re-derived later
  `callTimeRaw` VARCHAR(64) DEFAULT NULL,                     -- paper column 2 'Time'
  `callTime` DATETIME DEFAULT NULL,                           -- when the call came in, as reported; createdAt is the entry time (REC-2)
  `callTimeBasis` VARCHAR(255) DEFAULT NULL,
  `etaDayRaw` VARCHAR(64) DEFAULT NULL,                       -- 'ETA/ETR Return Day or Date', as spoken: tomorrow, Sat, 13/9
  `etaDate` DATE DEFAULT NULL,                                -- resolved at the moment it was written: 'tomorrow' is a date, not a word
  `etaRaw` VARCHAR(64) DEFAULT NULL,                          -- 'ETA/ETR Time', as spoken: 1500, 3pm, +2h (CAP-8)
  `eta` DATETIME DEFAULT NULL,                                -- the interpreted return deadline; NULL = not time-monitorable (DAT-1)
  `etaBasis` VARCHAR(255) DEFAULT NULL,
  `pob` VARCHAR(32) DEFAULT NULL,                             -- persons on board, as heard
  `destination` VARCHAR(255) DEFAULT NULL,
  `departurePoint` VARCHAR(255) DEFAULT NULL,
  `departureDayRaw` VARCHAR(64) DEFAULT NULL,                 -- not on the paper log; a departure time needs a day like any other
  `departureDate` DATE DEFAULT NULL,
  `departureRaw` VARCHAR(64) DEFAULT NULL,
  `departureTime` DATETIME DEFAULT NULL,
  `departureBasis` VARCHAR(255) DEFAULT NULL,
  `memberNumber` VARCHAR(64) DEFAULT NULL,                    -- class B: the current value; every value heard is also an Identifiers row (DAT-5)
  `registration` VARCHAR(64) DEFAULT NULL,
  `mobile` VARCHAR(32) DEFAULT NULL,
  `vesselName` VARCHAR(255) DEFAULT NULL,
  `vesselDetails` VARCHAR(255) DEFAULT NULL,                  -- paper column 6, free text as heard (class D)
  `radioChannel` VARCHAR(32) DEFAULT NULL,                    -- class C
  `contactName` VARCHAR(255) DEFAULT NULL,
  `contactNumber` VARCHAR(32) DEFAULT NULL,
  `ais` VARCHAR(32) DEFAULT NULL,
  `length` VARCHAR(16) DEFAULT NULL,                          -- class D, metres, as heard
  `hullColour` VARCHAR(64) DEFAULT NULL,
  `vesselType` VARCHAR(64) DEFAULT NULL,
  `make` VARCHAR(64) DEFAULT NULL,
  `model` VARCHAR(64) DEFAULT NULL,
  `notes` TEXT DEFAULT NULL,
  `verifyOutcome` VARCHAR(16) DEFAULT NULL,                   -- verified | conflict | partial | unverified (IDV-2)
  `verifyBasis` VARCHAR(255) DEFAULT NULL,                    -- the reason in words, recomputed from current evidence (IDV-3)
  `loggedOffAt` DATETIME DEFAULT NULL,
  `loggedOffNote` VARCHAR(255) DEFAULT NULL,
  `version` INT NOT NULL DEFAULT 0,                           -- +1 per saved change; a save sends the version it saw (CAP-22)
  `createdBy` VARCHAR(255) NOT NULL DEFAULT '',
  `createdAt` DATETIME DEFAULT NOW(),                         -- the entry time
  `updatedBy` VARCHAR(255) NOT NULL DEFAULT '',
  `updatedAt` DATETIME DEFAULT NOW(),
  `isActive` BOOL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS `idx_logons_open` ON `LogOns`(`unit`, `watchStatus`, `isActive`);

-- Every identifying value as the operator heard it, kept whatever it later resolves to (DAT-5, IDV-1).
-- A corrected value supersedes the previous row for that kind; the old row stays, inactive (IDV-3).
CREATE TABLE IF NOT EXISTS `Identifiers` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `logOnId` INT NOT NULL,
  `kind` VARCHAR(16) NOT NULL,                                -- memberNumber | registration | mobile | vesselName
  `raw` VARCHAR(255) NOT NULL,
  `normalized` VARCHAR(255) NOT NULL,
  `source` VARCHAR(16) NOT NULL DEFAULT 'call',               -- call | profile | import | corrected (IDV-1)
  `capturedBy` VARCHAR(255) NOT NULL DEFAULT '',
  `capturedAt` DATETIME DEFAULT NOW(),
  `isActive` BOOL DEFAULT 1,
  FOREIGN KEY (`logOnId`) REFERENCES `LogOns`(`id`)
);
CREATE INDEX IF NOT EXISTS `idx_identifiers_logon` ON `Identifiers`(`logOnId`, `isActive`);
