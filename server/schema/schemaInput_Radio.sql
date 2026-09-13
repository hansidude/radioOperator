-- Vessel log on (vessel-logon-spec.md). The host applies this file: in quackit, Admin -> Database
-- management generates these tables plus their history tables and triggers; standalone runs the
-- same CREATEs on SQLite or MariaDB without triggers. No foreign keys out of LogOns: memberId and vesselId are
-- links to current records, and the trip keeps the values it was given (§3.2).

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
  -- One state, not two (§3.3): a draft is saved and not watched; accepting it is what starts the
  -- watch and what the unit tells the vessel; it then ends by log off. A draft that was never a
  -- log on is discarded instead (ACC-7).
  `watchStatus` VARCHAR(16) NOT NULL DEFAULT 'draft',         -- draft | loggedOn | loggedOff | discarded (renamed from watching / loggedoff 2026-09-13)
  `dayNumber` INT DEFAULT NULL,                               -- counts from 1 each day: what operators say out loud (REC-9)
  `dayDate` DATE DEFAULT NULL,                                -- the day that number belongs to
  -- Paper column 'Trip ID No.', pre-printed 'T-' (spec A.1). One running sequence, not per day:
  -- this is the record's key, the day number is only what the operator says out loud. The state-wide
  -- system issues these across every unit; this branch allocates its own and the width leaves room
  -- to re-key behind a branch prefix if the ranges are ever divided up.
  `tripRef` VARCHAR(16) DEFAULT NULL,                         -- 'T-00042'; NULL until the first save that passes the draft minimum
  `acceptedAt` DATETIME DEFAULT NULL,                         -- the moment the unit took the watch (ACC-3)
  `acceptedBy` VARCHAR(255) DEFAULT NULL,
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
  -- The member and vessel records this trip is tied to. A new or changed Member No. must be a real
  -- member; with no member the log on is a public user's (owner, 2026-09-14).
  `memberId` INT DEFAULT NULL,                                -- Members.id; NULL = a public user log on
  `vesselId` INT DEFAULT NULL,                                -- Vessels.id, when the rego names exactly one known vessel
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
  `closeReason` VARCHAR(16) DEFAULT NULL,                     -- returned | notdeparted | other: a trip that happened or did not
  -- A draft that was never a log on: begun in error, or abandoned before anything identifying (ACC-7).
  `discardedAt` DATETIME DEFAULT NULL,
  `discardReason` VARCHAR(255) DEFAULT NULL,
  -- Superseded by v1.0 and no longer written. Cancelling an accepted log on is gone (a log on that
  -- happened is logged off), and duplicates cannot be created at all (ACC-6). Kept, not dropped,
  -- because the rows that used them are still auditable.
  `cancelledAt` DATETIME DEFAULT NULL,
  `cancelReason` VARCHAR(255) DEFAULT NULL,
  `duplicateOf` INT DEFAULT NULL,
  -- A closure made in error is corrected, not erased: the closure event stays and this records the undo.
  `reopenedAt` DATETIME DEFAULT NULL,
  `reopenReason` VARCHAR(255) DEFAULT NULL,
  `version` INT NOT NULL DEFAULT 0,                           -- +1 per saved change; a save sends the version it saw (CAP-22)
  `createdBy` VARCHAR(255) NOT NULL DEFAULT '',
  `createdAt` DATETIME DEFAULT NOW(),                         -- the entry time
  `updatedBy` VARCHAR(255) NOT NULL DEFAULT '',
  `updatedAt` DATETIME DEFAULT NOW(),
  `isActive` BOOL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS `idx_logons_open` ON `LogOns`(`unit`, `watchStatus`, `isActive`);
-- One number per unit per day (REC-9). Note: quackit's migration generator emits this as a plain
-- CREATE INDEX, dropping the uniqueness, so the allocation in logons.create() locks rather than
-- relying on this constraint. Standalone on SQLite does get the constraint.
CREATE UNIQUE INDEX IF NOT EXISTS `uniq_logons_daynumber` ON `LogOns`(`unit`, `dayDate`, `dayNumber`);
-- One trip reference, ever (REC-9). Same caveat as above: on quackit this arrives as a plain index,
-- so logons._next_number() locks and retries rather than trusting it. NULL repeats freely, which is
-- what an unsaved draft needs.
CREATE UNIQUE INDEX IF NOT EXISTS `uniq_logons_tripref` ON `LogOns`(`tripRef`);

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

-- What the unit has been told, and when. An alert is a durable fact rather than a colour on a page:
-- it is raised by the checker whether or not anyone has a browser open (ACC-5, WAT-3), it survives a
-- restart, and acknowledging it records attention only. It is resolved when the thing that caused it
-- is resolved, never by looking at it.
CREATE TABLE IF NOT EXISTS `Alerts` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `unit` VARCHAR(64) NOT NULL DEFAULT '',
  `logOnId` INT NOT NULL,
  `kind` VARCHAR(24) NOT NULL,                                -- draftfollowup (internal) | overdue (the vessel)
  `dueAt` DATETIME NOT NULL,                                  -- the moment it became due
  `raisedAt` DATETIME NOT NULL,                               -- the moment the checker noticed
  `notifiedAt` DATETIME DEFAULT NULL,                         -- last time it was put in front of someone
  `notifyCount` INT NOT NULL DEFAULT 0,
  `deliveredAt` DATETIME DEFAULT NULL,                        -- last time a channel accepted it
  `deliveryError` VARCHAR(255) DEFAULT NULL,                  -- why it did not: a silent pager is worse than none
  `acknowledgedAt` DATETIME DEFAULT NULL,                     -- attention, not resolution
  `acknowledgedBy` VARCHAR(255) DEFAULT NULL,
  `resolvedAt` DATETIME DEFAULT NULL,
  `resolvedReason` VARCHAR(64) DEFAULT NULL,                  -- the record's status when the alert stopped: draft | loggedOn | loggedOff | discarded | withdrawn
  `isActive` BOOL DEFAULT 1,
  FOREIGN KEY (`logOnId`) REFERENCES `LogOns`(`id`)
);
CREATE INDEX IF NOT EXISTS `idx_alerts_open` ON `Alerts`(`unit`, `resolvedAt`, `kind`);

-- Whether anything is actually watching. One row, holding the lease that keeps several web workers
-- from each running the checker, and the last time a pass completed. A monitor that has died and a
-- monitor with nothing to report look identical unless this is shown (WAT-3).
CREATE TABLE IF NOT EXISTS `WatchHealth` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `name` VARCHAR(32) NOT NULL DEFAULT 'checker',
  `holder` VARCHAR(64) DEFAULT NULL,
  `leaseUntil` DATETIME DEFAULT NULL,
  `lastRunAt` DATETIME DEFAULT NULL,
  `lastError` VARCHAR(255) DEFAULT NULL,
  `runs` INT NOT NULL DEFAULT 0
);

-- The unit's standing records (spec §3.1 Member / PublicUser and Vessel). A member holds any number of
-- emergency contacts, vessels, trailers and cars. A vessel with no member is a public vessel: for a
-- public user the vessel is the record, so its owner's contact details are on it.
-- Member numbers are issued here: 'm00001', one running sequence. Same caveat as the trip reference:
-- quackit's generator drops the uniqueness, so members.save_member() allocates under a lock.
CREATE TABLE IF NOT EXISTS `Members` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `unit` VARCHAR(64) NOT NULL DEFAULT '',
  `memberNumber` VARCHAR(16) NOT NULL,
  -- name and phone until 2026-09-14: split into first and last name, and phone renamed mobile (the log on's rule)
  `firstName` VARCHAR(128) NOT NULL,
  `lastName` VARCHAR(128) NOT NULL,
  `address` VARCHAR(255) DEFAULT NULL,
  `mobile` VARCHAR(32) DEFAULT NULL,                          -- 10 digits, written 0412 345 678
  `email` VARCHAR(255) DEFAULT NULL,
  `version` INT NOT NULL DEFAULT 0,
  `createdBy` VARCHAR(255) NOT NULL DEFAULT '',
  `createdAt` DATETIME DEFAULT NOW(),
  `updatedBy` VARCHAR(255) NOT NULL DEFAULT '',
  `updatedAt` DATETIME DEFAULT NOW(),
  `isActive` BOOL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS `uniq_members_number` ON `Members`(`memberNumber`);

CREATE TABLE IF NOT EXISTS `EmergencyContacts` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `memberId` INT NOT NULL,
  `name` VARCHAR(255) NOT NULL,
  `relationship` VARCHAR(64) DEFAULT NULL,
  `phone` VARCHAR(32) DEFAULT NULL,
  `email` VARCHAR(255) DEFAULT NULL,
  `version` INT NOT NULL DEFAULT 0,
  `createdBy` VARCHAR(255) NOT NULL DEFAULT '',
  `createdAt` DATETIME DEFAULT NOW(),
  `updatedBy` VARCHAR(255) NOT NULL DEFAULT '',
  `updatedAt` DATETIME DEFAULT NOW(),
  `isActive` BOOL DEFAULT 1,
  FOREIGN KEY (`memberId`) REFERENCES `Members`(`id`)
);
CREATE INDEX IF NOT EXISTS `idx_contacts_member` ON `EmergencyContacts`(`memberId`, `isActive`);

-- A member's vessel (memberId) or a public vessel (memberId NULL, owner details filled in).
CREATE TABLE IF NOT EXISTS `Vessels` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `unit` VARCHAR(64) NOT NULL DEFAULT '',
  `memberId` INT DEFAULT NULL,
  `vesselName` VARCHAR(255) DEFAULT NULL,                    -- the same column names as LogOns, so one set of labels
  `registration` VARCHAR(64) DEFAULT NULL,
  `length` VARCHAR(16) DEFAULT NULL,                          -- metres
  `hullColour` VARCHAR(64) DEFAULT NULL,
  `vesselType` VARCHAR(64) DEFAULT NULL,
  `make` VARCHAR(64) DEFAULT NULL,
  `model` VARCHAR(64) DEFAULT NULL,
  `ais` VARCHAR(32) DEFAULT NULL,
  `ownerName` VARCHAR(255) DEFAULT NULL,                      -- public vessel: the public user
  `ownerPhone` VARCHAR(32) DEFAULT NULL,
  `ownerEmail` VARCHAR(255) DEFAULT NULL,
  `version` INT NOT NULL DEFAULT 0,
  `createdBy` VARCHAR(255) NOT NULL DEFAULT '',
  `createdAt` DATETIME DEFAULT NOW(),
  `updatedBy` VARCHAR(255) NOT NULL DEFAULT '',
  `updatedAt` DATETIME DEFAULT NOW(),
  `isActive` BOOL DEFAULT 1,
  FOREIGN KEY (`memberId`) REFERENCES `Members`(`id`)
);
CREATE INDEX IF NOT EXISTS `idx_vessels_member` ON `Vessels`(`unit`, `memberId`, `isActive`);

CREATE TABLE IF NOT EXISTS `Trailers` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `memberId` INT NOT NULL,
  `registration` VARCHAR(64) NOT NULL,
  `make` VARCHAR(64) DEFAULT NULL,
  `model` VARCHAR(64) DEFAULT NULL,
  `colour` VARCHAR(64) DEFAULT NULL,
  `version` INT NOT NULL DEFAULT 0,
  `createdBy` VARCHAR(255) NOT NULL DEFAULT '',
  `createdAt` DATETIME DEFAULT NOW(),
  `updatedBy` VARCHAR(255) NOT NULL DEFAULT '',
  `updatedAt` DATETIME DEFAULT NOW(),
  `isActive` BOOL DEFAULT 1,
  FOREIGN KEY (`memberId`) REFERENCES `Members`(`id`)
);
CREATE INDEX IF NOT EXISTS `idx_trailers_member` ON `Trailers`(`memberId`, `isActive`);

CREATE TABLE IF NOT EXISTS `Cars` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `memberId` INT NOT NULL,
  `registration` VARCHAR(64) NOT NULL,
  `make` VARCHAR(64) DEFAULT NULL,
  `model` VARCHAR(64) DEFAULT NULL,
  `colour` VARCHAR(64) DEFAULT NULL,
  `version` INT NOT NULL DEFAULT 0,
  `createdBy` VARCHAR(255) NOT NULL DEFAULT '',
  `createdAt` DATETIME DEFAULT NOW(),
  `updatedBy` VARCHAR(255) NOT NULL DEFAULT '',
  `updatedAt` DATETIME DEFAULT NOW(),
  `isActive` BOOL DEFAULT 1,
  FOREIGN KEY (`memberId`) REFERENCES `Members`(`id`)
);
CREATE INDEX IF NOT EXISTS `idx_cars_member` ON `Cars`(`memberId`, `isActive`);
