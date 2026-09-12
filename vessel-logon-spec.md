# Vessel Log On — Functional Specification

**Version:** 0.4 (draft)
**Status:** For review
**Domain:** Marine rescue vessel log on, watch, and log off
**Audience:** Anyone implementing or evaluating a system that performs this function

---

## 1. Purpose and scope

### 1.1 Purpose

This document specifies the required behaviour of a system that records vessels departing
under the watch of a marine rescue unit, monitors their safe return, and escalates when
they do not return.

It is written to be implementation-independent. It names no product and assumes no
technology. It is equally usable as a build specification and as an evaluation checklist
for an existing system.

### 1.2 The primary safety objective

All requirements in this document derive from one objective:

> **PSO.** If a vessel does not return when it said it would, the unit shall know, and
> the unit shall be able to find it.

Where any two requirements appear to conflict, the one that better serves PSO prevails.

### 1.3 Scope

**In scope:** capture of log on details across all channels; identification and
verification of vessels and persons; search across unit records; monitoring of active
log ons; overdue detection and escalation; log off; amendment; record retention and
audit.

**Out of scope:** conduct of the search or rescue itself; asset and crew management;
member administration and billing; incident management beyond the point of escalation.

### 1.4 Priority

Requirements carry a priority reflecting current operational need, not importance:

| Priority | Meaning |
|---|---|
| **P1** | Primary focus. Capture and verification of radio log ons — §5, §6, §7. |
| **P2** | Required, but adequately served by existing practice — §8, §9. |
| **P3** | Required for completeness; lowest urgency. |

### 1.5 Requirement language

**Shall** — mandatory. **Should** — strongly recommended; deviation requires
justification. **May** — optional.

---

## 2. Definitions

| Term | Definition |
|---|---|
| **Log on** | A record that a vessel has departed under the unit's watch, with a stated intention to return by a stated time. |
| **Log off** | The act of closing a log on because the vessel has returned or otherwise ended its trip. |
| **Operator** | A person, usually a volunteer, receiving log ons at a unit. |
| **Unit** | A marine rescue base holding the watch for a geographic area. |
| **Member** | A person with a standing record held by the organisation. |
| **Public user** | A person without a standing record, logging on as a non-member. |
| **Identifier** | Any value that resolves to a stored record: member number, vessel registration, mobile number, vessel name. |
| **Verification** | Confirmation that captured identifying data corresponds to a real, correct record. |
| **Cross-verification** | Verification achieved by two independent identifiers resolving to the same record. See §7. |
| **Draft** | A log on that has been created and persisted but not yet completed. |
| **Active** | A log on for a vessel currently out, before its ETA. |
| **Overdue** | An active log on whose ETA has passed without log off. |
| **Escalated** | An overdue log on for which the escalation sequence has begun. |
| **ETA** | The time by which the vessel states it will return or report. Drives overdue detection. |
| **POB** | Persons on board. |
| **Enrichment** | Addition of detail to an existing log on after its initial creation. |
| **Airtime** | Occupancy of a shared radio channel. A finite, contended resource. |

---

## 3. Domain model

### 3.1 Entities

| Entity | Description | Key attributes |
|---|---|---|
| **LogOn** | The central record. One per trip. | state, channel, operator, unit, departure point, departure time, destination, ETA, POB, verification state, created/updated timestamps |
| **Vessel** | A boat known to the system. | registration, name, length, hull colour, type (power/sail/other), make, model, AIS identifier |
| **Member** | A person with a standing record. | member number, name, contact numbers, associated vessels |
| **PublicUser** | A person without a standing record. | name, contact numbers, associated vessels |
| **OnboardContact** | A person aboard or ashore who can be reached. | name, relationship, contact number |
| **Identifier** | A captured identifying value and its resolution outcome. | type, value as captured, resolved record, verification state |
| **EscalationStep** | One action taken against an overdue log on. | action, timestamp, operator, outcome |
| **Location** | A departure or destination point. | name, coordinates (optional), free-text flag |
| **Operator** | The person taking the call. | identity, unit, shift |

### 3.2 Relationships

- A **LogOn** references at most one **Vessel** and at most one **Member** or
  **PublicUser**. All three may be absent in a Draft.
- A **LogOn** holds zero or more **Identifier** records — one per identifying value
  captured, retaining the value **as captured** alongside its resolution.
- A **LogOn** holds zero or more **OnboardContact** records.
- A **LogOn** holds zero or more **EscalationStep** records, ordered by time.
- A **Vessel** may be associated with zero or more **Members** and **PublicUsers**, and
  vice versa.

### 3.3 States and transitions

```
            create
              │
              ▼
         ┌─────────┐  complete   ┌──────────┐  ETA passes  ┌──────────┐
         │  DRAFT  │ ──────────▶ │  ACTIVE  │ ───────────▶ │ OVERDUE  │
         └─────────┘             └──────────┘              └──────────┘
              │                    │      ▲                  │      │
              │ cancel             │      │ amend ETA        │      │ begin
              │                    │      └──────────────────┘      │ escalation
              ▼                    │                                ▼
         ┌───────────┐             │                          ┌────────────┐
         │ CANCELLED │             │                          │ ESCALATED  │
         └───────────┘             │                          └────────────┘
                                   │                                │
                    log off        ▼            log off             ▼
                            ┌────────────────────────────────────────────┐
                            │                LOGGED OFF                   │
                            └────────────────────────────────────────────┘
```

| Transition | Trigger | Notes |
|---|---|---|
| → Draft | Operator begins capture | Persisted immediately (CAP-1) |
| Draft → Active | Operator marks complete, or ETA and POB present and operator confirms | Draft may remain Draft indefinitely |
| Draft → Cancelled | Vessel did not depart | |
| Active → Overdue | ETA passes without log off | Automatic, system-driven |
| Active → Active | Amendment of ETA, destination, POB | Appends, does not overwrite (REC-3) |
| Overdue → Active | Vessel makes contact, new ETA agreed | |
| Overdue → Escalated | Escalation sequence begun | |
| Any → Logged off | Vessel returns or trip ends | Explicit operator action only (WAT-7) |
| Active → Transferred | Another unit assumes the watch | Record moves without re-keying |

A **Draft** is a valid, legally-held, searchable record in every state-dependent
behaviour except overdue detection, which requires an ETA.

### 3.4 Log on variants

| Variant | Difference |
|---|---|
| **Standard** | Single departure, single ETA. |
| **Long term** | Multi-day passage. ETA replaced by a schedule of expected position reports; overdue triggers on a missed report. |
| **Bar crossing** | Short, high-risk watch over a specific hazard. Short ETA. May be nested within a standard log on. |

All variants are the same entity with different ETA semantics. They shall not be modelled
as separate record types.

---

## 4. Operating context

Context that constrains the requirements. Stated as fact, not as complaint.

**OC-1.** Log ons arrive by marine radio, telephone, in person, and self-service. Radio
is the dominant channel and the most constrained; the system shall be designed for radio
and will thereby satisfy the others.

**OC-2.** A radio log on is an interview, not a dictation. The caller states a rough
intention; the operator elicits the remaining detail by asking. Field order is arbitrary
and varies per call.

**OC-3.** There is no published procedure instructing callers what to say, and no
enforced script instructing operators what to ask. Operators are volunteers of varying
experience and each works differently. The system shall not assume procedural
consistency.

**OC-4.** Airtime is contended. Every question the operator asks occupies a shared
channel that other vessels are waiting on. The system shall treat operator questions as
a cost to be minimised.

**OC-5.** Phonetic alphabet use is inconsistent, by callers and operators alike. Spoken
digits are reliable, because the operator controls the conversation and can request a
repeat. **Spoken letters are not**, and confuse along the predictable set in Appendix B.

**OC-6.** Identifying detail — vessel registration, mobile number — typically arrives
late in a call or only when asked, and sometimes on a later call. It shall not be
required early.

**OC-7.** The organisation is under a legislative obligation to hold a computer record of
log ons. A record held only on paper does not discharge that obligation.

**OC-8.** Calls arrive in bursts. Peak load is a period of good weather, which is also
when the greatest number of vessels are at sea.

---

## 5. Requirements — Capture (P1)

**CAP-1.** The system **shall** persist a log on record containing any subset of fields,
including an empty subset, from the moment capture begins.
*Rationale: a record that exists partially is operationally and legally superior to one
that exists only on paper (OC-7). Blocking creation converts a survivable gap into a
missing record.*

**CAP-2.** The system **shall not** require any field to be populated in order to create,
save, or retain a log on.
*Rationale: any mandatory field is a point at which capture can fail entirely (PSO).*

**CAP-3.** The system **shall** accept field entry in any order, with every field
reachable and editable from the keyboard without pointing-device interaction.
*Rationale: OC-2. Entry order is dictated by the caller.*

**CAP-4.** The system **shall** leave unpopulated fields empty, and **shall not**
pre-populate any field with a value that has not been supplied.
*Rationale: an unsupplied value that looks supplied produces a record that appears
correct and is not — the most dangerous output of the system.*

**CAP-5.** Where the system detects an inconsistency — for example an ETA preceding the
departure time — it **shall** present the warning adjacent to the field concerned, at the
time of entry, and **shall** permit the record to be saved regardless.
*Rationale: inconsistency is information; preventing the save discards the record to
protect the field.*

**CAP-6.** The system **shall** permit multiple log ons to be in Draft simultaneously, and
**shall** permit an operator to suspend and resume capture of any Draft without loss.
*Rationale: a priority radio call may interrupt capture at any point.*

**CAP-7.** The list of active and overdue log ons **shall** remain visible to the operator
during capture of a new log on.
*Rationale: situational awareness is the operator's primary function; capture must not
suspend it.*

**CAP-8.** The system **shall** accept time input in the forms operators speak and write,
including 24-hour (`1500`), 12-hour (`3pm`), and relative (`+2h`).
*Rationale: format conversion is cognitive load during a timed task.*

**CAP-9.** The system **shall** accept free text for departure point and destination, and
**shall** offer known locations as suggestions without restricting entry to them.
*Rationale: callers name places that exist in local usage and in no list.*

**CAP-10.** The system **shall** display, during capture, which fields remain unpopulated.
*Rationale: OC-3. In the absence of a procedure, the visible gap list is the procedure.*

**CAP-11.** The system **shall** rank unpopulated fields by the priority in §6.1, giving
greatest prominence to fields serving PSO and least to vessel description.
*Rationale: OC-4. Undifferentiated prompting spends airtime on low-value fields.*

**CAP-12.** Prompting under CAP-10 and CAP-11 **shall** be advisory, and **shall not**
prevent an operator from completing or closing a capture.
*Rationale: the operator, not the system, judges what is worth a transmission.*

**CAP-13.** The system **shall** permit any field of an existing log on in any open state
to be populated or amended, with the same interaction cost as initial capture.
*Rationale: OC-6. Late-arriving detail is the normal case.*

**CAP-14.** Capture of a log on for a person without a standing record **shall** proceed
without first classifying the caller, and **shall not** require vessel description fields
before the log on is created.
*Rationale: classification is a decision the operator cannot make until identity is
known, which is late (OC-6).*

**CAP-15.** Where vessel or contact detail has been captured previously for the same
vessel or person, the system **shall** offer it rather than requesting it again.
*Rationale: OC-4. Re-asking known detail spends airtime for no information gain.*

### 5.1 Capture performance

**CAP-16.** For a caller whose identifiers resolve to an existing record, and who supplies
all requested detail without repetition, a complete log on **shall** be capturable in
**30 seconds or less**, keyboard only.

**CAP-17.** For a caller with no existing record, a complete log on **shall** be capturable
in **90 seconds or less**.

**CAP-18.** Capture performance **shall** be measured against real calls under peak load
(OC-8), not estimated or measured under simulation.

---

## 6. Requirements — Data (P1)

### 6.1 Field priority classes

| Class | Purpose | Fields |
|---|---|---|
| **A** | Locate the vessel | ETA, POB, destination, departure point, departure time |
| **B** | Identify and verify | Member number, vessel registration, mobile number |
| **C** | Reach the vessel | Radio channel monitored, onboard/shore contact, AIS identifier |
| **D** | Describe the vessel | Length, hull colour, type, make, model |

**DAT-1.** Class A fields **shall** be treated as the minimum useful log on. A record
lacking an ETA **shall** be visibly distinguished, since it cannot become overdue.

**DAT-2.** The mobile number **shall** be treated as both a Class B identifier and a
Class C contact, and prioritised accordingly.
*Rationale: it serves double duty — it identifies the caller and is the first action on
overdue.*

**DAT-3.** Class D fields **shall not** be requested during capture where the vessel
resolves to an existing record carrying them.

**DAT-4.** The system **shall** retain Class D detail captured for a person without a
standing record, and associate it with the vessel for reuse.

**DAT-5.** Every captured identifier **shall** be stored as captured, independently of
whatever record it resolves to.
*Rationale: the value the operator heard is evidence; overwriting it with the resolved
value destroys the ability to detect a mis-resolution later.*

---

## 7. Requirements — Identification, verification and search (P1)

### 7.1 Cross-verification

**IDV-1.** The system **shall** support the capture of two or more independent identifiers
against a single log on.
*Rationale: two identifiers resolving to the same record verify each other. This is the
unit's existing accuracy practice and the strongest verification available at no airtime
cost.*

**IDV-2.** On capture of a second identifier, the system **shall** resolve both and
**shall** display the outcome immediately, as one of:

| Outcome | Condition |
|---|---|
| **Verified** | All captured identifiers resolve to the same member and vessel |
| **Conflict** | Identifiers resolve to different records |
| **Partial** | At least one resolves, at least one does not |
| **Unverified** | Fewer than two identifiers captured, or none resolve |

**IDV-3.** A **Conflict** outcome **shall** be presented prominently at the moment of
detection.
*Rationale: a conflict is the only reliable in-call signal that a captured value is
wrong.*

**IDV-4.** The verification outcome **shall** be stored on the log on and **shall** be
displayed wherever the log on appears, including the active watch list.

**IDV-5.** A verification outcome other than **Verified** **shall not** prevent the log on
being created, saved, or activated.
*Rationale: an unverified record is still a record of a vessel at sea.*

### 7.2 Tolerant resolution

**IDV-6.** Identifier resolution **shall** return near matches in addition to exact
matches, matching across the letter confusion set in Appendix B.
*Rationale: OC-5. A registration heard once without phonetics is routinely one letter
from correct, and the error is predictable.*

**IDV-7.** Resolution results **shall** include sufficient descriptive detail — vessel
name, length, hull colour, type, associated member — to allow the operator to confirm
identity by description.
*Rationale: confirming "the white centre console, Sea Breeze" is one short transmission
and is more reliable than a phonetic readback of the registration.*

**IDV-8.** Where resolution returns more than one candidate, all candidates **shall** be
presented together.

### 7.3 Search

**SRCH-1.** The system **shall** provide a single search input that returns results across
all record types: members, public users, vessels, active log ons, draft log ons, and
historical log ons.
*Rationale: cross-verification (IDV-2) requires two identifiers resolvable in one action.
Separate searches per record type make verification cost more airtime than it saves, and
it is then not performed.*

**SRCH-2.** Search **shall** accept any identifier type in the same input without the user
selecting a type in advance: member number, vessel registration, mobile number, vessel
name, person name.

**SRCH-3.** A vessel or person **shall** remain returnable by search regardless of whether
they currently hold an active log on.
*Rationale: an in-progress trip is the state in which lookup is most often needed.*

**SRCH-4.** Search results **shall** indicate the record type and current state of each
result, and **shall** indicate whether a returned vessel or person is currently logged on.

**SRCH-5.** Search **shall** return results on partial input.

**SRCH-6.** Every search result **shall** offer a single action to apply it to the log on
in progress.

---

## 8. Requirements — Watch and overdue (P2)

**WAT-1.** The system **shall** display a persistent list of active and overdue log ons,
ordered by proximity to ETA.

**WAT-2.** The system **shall** indicate log ons approaching their ETA before that ETA
passes.

**WAT-3.** Transition to Overdue **shall** produce an alert that does not depend on the
operator observing a change in a list.

**WAT-4.** The system **shall** present the escalation sequence as an ordered set of
actions, and **shall** record each action attempted with time, operator and outcome.
*Rationale: OC-3. Where no written procedure exists, the recorded sequence is the
procedure and the audit trail simultaneously.*

**WAT-5.** On transition to Overdue, the system **shall** surface the log on's verification
outcome (IDV-2).
*Rationale: personnel about to act on the record need to know which parts of it are
verified.*

**WAT-6.** The system **shall** transfer the complete state of all active log ons,
including escalation history, on shift handover, without re-keying.

**WAT-7.** A log on **shall** leave the active list only by explicit operator action,
recorded against that operator.

**WAT-8.** The system **shall** support transfer of an active log on to another unit,
preserving the record and its history without re-keying.

---

## 9. Requirements — Record and audit (P2)

**REC-1.** The system **shall** constitute the record of log ons for the purpose of the
organisation's legislative obligation (OC-7), including retention, integrity and
export.

**REC-2.** Every log on and every subsequent action **shall** record the operator, unit,
timestamp and channel.

**REC-3.** Amendments **shall** be appended. Prior values **shall** remain retrievable.
*Rationale: post-incident review requires knowing what was known at each point in time,
not only the final state.*

**REC-4.** Verification outcomes and the identifiers as captured (DAT-5) **shall** form
part of the permanent record.

**REC-5.** The system **shall** report on operational measures including call volume by
period, overdue frequency, escalation outcomes, and **the proportion of log ons captured
during the call versus entered afterwards**.
*Rationale: the latter is the direct measure of whether capture is keeping pace with the
radio.*

---

## 10. Acceptance criteria

Each criterion is a pass/fail test against a running system.

### 10.1 Capture

| # | Test | Pass condition |
|---|---|---|
| **AC-1** | Begin a log on, enter nothing, save. | Record persists and is retrievable. |
| **AC-2** | Enter only POB and destination. Save. Close the session. Reopen. | Record persists with those two fields. |
| **AC-3** | Open a new log on form and inspect every field. | No field holds a value that was not entered. |
| **AC-4** | Enter an ETA earlier than the departure time. Save. | Warning shown beside the field; save succeeds. |
| **AC-5** | Begin a log on, start a second, return to the first. | Both retained, neither altered. |
| **AC-6** | Capture a log on while the active list is on screen. | Active list remains visible throughout. |
| **AC-7** | Complete a full log on using keyboard only. | Achievable; no pointing device required. |
| **AC-8** | Enter `1500`, `3pm`, `+2h` into an ETA field. | All three accepted. |
| **AC-9** | Enter a destination not present in any list. | Accepted as entered. |
| **AC-10** | Time a known-member log on under peak load. | ≤ 30 seconds (CAP-16). |
| **AC-11** | Time an unknown-vessel log on under peak load. | ≤ 90 seconds (CAP-17). |
| **AC-12** | Add a registration to a log on created an hour earlier. | Same interaction cost as initial capture. |

### 10.2 Verification and search

| # | Test | Pass condition |
|---|---|---|
| **AC-13** | Enter a member number and a registration belonging to the same member. | Outcome shown as **Verified**. |
| **AC-14** | Enter a member number and a registration belonging to different members. | Outcome shown as **Conflict**, prominently. |
| **AC-15** | Enter a registration one letter wrong, within the Appendix B confusion set. | Correct vessel returned as a candidate. |
| **AC-16** | Inspect any resolution result. | Includes vessel name, length, colour, type, associated member. |
| **AC-17** | Search a registration for a vessel currently logged on. | Vessel returned, marked as currently logged on. |
| **AC-18** | Search a member number, a registration, a mobile number and a vessel name in the same input. | All return results without changing search mode. |
| **AC-19** | Save a log on with a **Conflict** outcome. | Save succeeds; conflict remains visible on the record. |
| **AC-20** | View the active watch list. | Verification outcome visible per row. |

### 10.3 Watch, record and audit

| # | Test | Pass condition |
|---|---|---|
| **AC-21** | Allow an ETA to pass. | Overdue alert raised without operator action. |
| **AC-22** | Trigger an overdue on an unverified record. | Verification state surfaced with the alert. |
| **AC-23** | Amend an ETA, then inspect history. | Both original and amended values retrievable. |
| **AC-24** | Perform a shift handover. | All active log ons and escalation history transfer without re-entry. |
| **AC-25** | Run the operational report. | Proportion of live-captured versus later-entered log ons is reported. |

### 10.4 System-level acceptance

**AC-26.** Operators cease maintaining a parallel paper log, without being instructed to.

*This is the single sufficient test. A system passing AC-1 to AC-25 and failing AC-26 has
met the letter of the specification and not its purpose.*

---

## Appendix A — Justification from current practice

Evidence that the requirements above address real conditions rather than hypothetical
ones. Recorded from a unit operating a commercial resilience-management platform
alongside a handwritten radio log.

**A.1 The paper log is the working record.** Its columns are: date/time of call; member
number or vessel registration; contact mobile; POB; departure point; destination; return
date; return time; *entered into the computer system*; *system record ID*; logged off.

The presence of the last-but-two and last-but-one columns is decisive. **The paper log
tracks the computer system as an outstanding task.** The operational record is paper; the
computer record is a downstream transcription. Given OC-7, the legally required record
therefore runs permanently behind the operational one. AC-26 exists to detect when this
has been reversed.

**A.2 All-or-nothing saving produces the backlog.** The current system cannot persist an
incomplete log on. An operator who has captured half the detail has nothing to save, so
the entry stays on paper until there is time to complete it — and the backlog grows
fastest precisely under peak load (OC-8), when it is least affordable. CAP-1 and CAP-2
address this directly.

**A.3 Mandatory fields are the fields that arrive last.** Registration and mobile number
are required before a record can be saved, and are the two fields that typically arrive
last in a call or on a later call (OC-6). The form demands first what the conversation
surrenders last. CAP-2, CAP-13 and CAP-14 address this.

**A.4 Default values that fail validation.** The observed new-log-on form pre-populates
departure time and ETA with the same value, then rejects the record on the grounds that
the ETA must be later than the departure. The form's initial state fails its own
validation, so every log on begins from an error condition. Worse, the paired defaults
could be saved unnoticed if validation did not object, producing a record that would
never become overdue. CAP-4 and CAP-5 address this.

**A.5 Validation errors are remote from their fields.** Errors are presented as a block at
the top of the form, referring to fields several sections away, discovered only on
attempting to save. CAP-5 addresses this.

**A.6 Capture occludes the watch.** New log on capture opens as a full-screen modal,
concealing the list of vessels currently at sea for its duration. CAP-7 addresses this.

**A.7 Search is partitioned, and cross-verification is thereby defeated.** Members,
vessels and active log ons are held behind separate searches. A vessel holding an active
log on is not returned by vessel search — the state in which lookup is most often needed.
Consequently, cross-verifying two identifiers requires several lookups across separate
screens, and under load it is not performed. The unit's principal accuracy mechanism
therefore stops operating exactly when accuracy matters most. SRCH-1 to SRCH-4 address
this.

**A.8 Two identifiers are the existing accuracy practice.** Operators routinely request
two identifying values — member number and registration, or registration and mobile
number. This is not redundancy but a checksum: agreement verifies, disagreement detects
an error that is otherwise invisible. The practice is undocumented and unsupported by
software, and is performed by eye across the partitioned searches described in A.7.
IDV-1 to IDV-5 formalise it.

**A.9 Phonetic discipline is not reliable under load.** Requesting a phonetic repeat costs
a transmission on a contended channel. Under peak load, operators reasonably omit it.
Registrations captured from a single unphonetic hearing are therefore routine, and
IDV-6 exists because discipline is not an available solution.

---

## Appendix B — Letter confusion set

Errors in unphonetic spoken letters are not uniformly distributed. Resolution under
IDV-6 shall treat members of each group as candidate substitutions for one another.

| Group | Members |
|---|---|
| Rhyming ("E-set") | B · C · D · E · G · P · T · V · Z · 3 |
| Nasal | M · N |
| Sibilant | F · S · X · 6 |
| Long-A | A · J · K · 8 |
| Letter/digit collision | 0 ↔ O · 1 ↔ I ↔ L · 5 ↔ S · 2 ↔ Z |

Spoken digits are excluded: the operator controls the conversation and may request a
repeat, and digit confusion is not systematic (OC-5).

---

## Appendix C — Traceability from version 0.3

| 0.3 | 0.4 |
|---|---|
| §1 safety contract | §1.2 PSO |
| §1.2 legal record | OC-7, REC-1 |
| §2.2 interview | OC-2 |
| §2.3 no procedure | OC-3 |
| §2.4 phonetics | OC-5, Appendix B |
| §3.1 tiers | §6.1 classes A–D |
| §3.2 checksum | IDV-1 … IDV-5 |
| §3.3 unified search | SRCH-1 … SRCH-6 |
| C1, C2 | CAP-1, CAP-2 |
| C3 | CAP-4 |
| C4 | CAP-5 |
| C5 | CAP-6 |
| C6 | CAP-7 |
| C7 | CAP-16 … CAP-18 |
| C8 | CAP-8, CAP-9 |
| C9, C10 | CAP-10, CAP-11, CAP-12 |
| C11 | IDV-6 … IDV-8 |
| C12 | IDV-1 … IDV-5 |
| C13 | CAP-13 |
| C14 | SRCH-1 … SRCH-6 |
| W1 … W7 | WAT-1 … WAT-8 |
| R1 … R5 | REC-1 … REC-5 |
| §7 anti-requirements | Dissolved into positive requirements; evidence moved to Appendix A |
| §8 acceptance test | AC-26 |

---

## Appendix D — Open questions

1. On a **Conflict** outcome (IDV-2), what resolution does the operator perform today?
   Determines whether IDV-3 requires a defined workflow or a flag alone.
2. Is a logged-on vessel excluded from vessel search by query construction or by data
   model? Determines the difficulty of SRCH-3.
3. What is the typical transcription backlog — count of entries, and elapsed time from
   call to computer entry? Establishes the baseline for REC-5 and AC-26.
4. Which identifier pair is most commonly used: member number with registration, or
   registration with mobile number? Determines what IDV-2 optimises for.
5. What is the legislative instrument underlying OC-7? Determines retention period and
   integrity obligations under REC-1.
6. For long term log ons (§3.4), what reporting schedule is expected, and what constitutes
   a missed report?
