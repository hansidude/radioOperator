# Vessel Log On — Functional Specification

**Version:** 1.1 (draft)<br>
**Revised:** 14 September 2026 (AEST)<br>
**Status:** For operational review; not an approved operating procedure<br>
**Domain:** Marine rescue vessel log on, watch, and log off<br>
**Audience:** Anyone implementing or evaluating a system that performs this function

<!-- contents:start -->
## Table of contents

- [1. Purpose and scope](#section-1-purpose-and-scope)
    - [1.1 Purpose](#section-11-purpose)
    - [1.2 The primary safety objective](#section-12-the-primary-safety-objective)
    - [1.3 Scope](#section-13-scope)
    - [1.4 Priority](#section-14-priority)
    - [1.5 Requirement language](#section-15-requirement-language)
- [2. Definitions](#section-2-definitions)
- [3. Domain model](#section-3-domain-model)
    - [3.1 Entities](#section-31-entities)
    - [3.2 Relationships](#section-32-relationships)
    - [3.3 Draft, log on, logged off](#section-33-draft-log-on-logged-off)
    - [3.4 Log on variants and obligations](#section-34-log-on-variants-and-obligations)
    - [3.5 The process, ideal and otherwise](#section-35-the-process-ideal-and-otherwise)
- [4. Operating context](#section-4-operating-context)
- [5. Requirements — Capture (P1)](#section-5-requirements-capture-p1)
    - [5.1 Capture performance](#section-51-capture-performance)
    - [5.2 Persistence, interruption and concurrent work](#section-52-persistence-interruption-and-concurrent-work)
    - [5.3 Acceptance — the gate between a draft and a watch](#section-53-acceptance-the-gate-between-a-draft-and-a-watch)
- [6. Requirements — Data (P1)](#section-6-requirements-data-p1)
    - [6.1 Field priority classes](#section-61-field-priority-classes)
- [7. Requirements — Identification, verification and search (P1)](#section-7-requirements-identification-verification-and-search-p1)
    - [7.1 Cross-verification](#section-71-cross-verification)
    - [7.2 Tolerant resolution](#section-72-tolerant-resolution)
    - [7.3 Search](#section-73-search)
- [8. Requirements — Watch and overdue (P2)](#section-8-requirements-watch-and-overdue-p2)
- [9. Requirements — Record and audit (P2)](#section-9-requirements-record-and-audit-p2)
- [10. Acceptance criteria](#section-10-acceptance-criteria)
    - [10.1 Capture](#section-101-capture)
    - [10.2 Verification and search](#section-102-verification-and-search)
    - [10.3 Watch, record and audit](#section-103-watch-record-and-audit)
    - [10.4 Adoption and release acceptance](#section-104-adoption-and-release-acceptance)
    - [10.5 Interrupted and exceptional operation](#section-105-interrupted-and-exceptional-operation)
    - [10.6 Operational release gate](#section-106-operational-release-gate)
- [Appendix A — Justification from current practice](#section-appendix-a-justification-from-current-practice)
- [Appendix B — Letter confusion set](#section-appendix-b-letter-confusion-set)
- [Appendix C — Traceability from version 0.3](#section-appendix-c-traceability-from-version-03)
- [Appendix D — Open questions](#section-appendix-d-open-questions)
- [Appendix E — Revision history](#section-appendix-e-revision-history)
    - [Version 1.1 — changes from 1.0](#section-version-11-changes-from-10)
    - [Version 1.0 — changes from 0.9](#section-version-10-changes-from-09)
    - [Version 0.9 — changes from 0.8](#section-version-09-changes-from-08)
    - [Version 0.8 — changes from 0.7](#section-version-08-changes-from-07)
    - [Version 0.7 — changes from 0.6](#section-version-07-changes-from-06)
    - [Version 0.6 — changes from 0.5](#section-version-06-changes-from-05)
    - [Version 0.5 — changes from 0.4](#section-version-05-changes-from-04)
- [Appendix F — Evidence figures](#section-appendix-f-evidence-figures)
    - [Figure 1 — Active log on list](#section-figure-1-active-log-on-list)
    - [Figure 2 — Validation error block](#section-figure-2-validation-error-block)
    - [Figure 3 — Capture form scrolled](#section-figure-3-capture-form-scrolled)
    - [Figure 4 — Trip-detail defaults](#section-figure-4-trip-detail-defaults)
    - [Figure 5 — Paper radio log](#section-figure-5-paper-radio-log)
<!-- contents:end -->

---

<a id="section-1-purpose-and-scope"></a>

## 1. Purpose and scope

<a id="section-11-purpose"></a>

### 1.1 Purpose

This document specifies the required behaviour of a system that records vessels departing
under the watch of a marine rescue unit, monitors their safe return, and escalates when
they do not return.

It is written to be implementation-independent. It names no product and assumes no
technology. It is equally usable as a build specification and as an evaluation checklist
for an existing system.

<a id="section-12-the-primary-safety-objective"></a>

### 1.2 The primary safety objective

All requirements in this document derive from one objective:

> **PSO.** If a vessel does not return when it said it would, the unit shall know, and
> the unit shall be able to find it.

PSO expresses the intended outcome; software cannot guarantee that a vessel will be found.
Its testable contribution is to preserve the information received, expose missing or
uncertain information, detect missed obligations, and retain an accountable watch owner.

Conflicting requirements shall be resolved explicitly during review, with the decision
recorded against PSO. Implementers shall not silently waive a requirement by invoking PSO.

One such conflict is resolved in this version and is stated here because it is the most
consequential decision in the document. **Nothing is watched until the log on is accepted**
(§5.3). A vessel that gave a return time into a call that was never finished is therefore not
being counted down. That is the unit's decision, and it is deliberate: a watch the unit cannot
act on is not a watch, and acceptance, the save that completes the required details, is the moment
the unit tells the vessel it is logged on.
The cost is a new failure mode — an unfinished draft, forgotten, while the vessel believes it is
under watch. PSO is served against that not by monitoring an incomplete record but by making an
unaccepted draft impossible to ignore (ACC-5, WAT-9). If that chase is weak, this decision is
unsafe, and the deployment has not met this specification.

<a id="section-13-scope"></a>

### 1.3 Scope

**In scope:** capture of log on details across all channels; identification and
verification of vessels and persons; search across unit records; monitoring of active
log ons; overdue detection and escalation; log off; amendment; record retention and
audit.

**Out of scope:** conduct of the search or rescue itself; asset and crew management;
member administration and billing; incident management beyond the point of escalation.

<a id="section-14-priority"></a>

### 1.4 Priority

Requirements carry a priority reflecting current operational need, not importance:

| Priority | Meaning |
|---|---|
| **P1** | Primary focus. Capture and verification of radio log ons — §5, §6, §7. |
| **P2** | Required, but adequately served by existing practice — §8, §9. |
| **P3** | Required for completeness; lowest urgency. No requirement in this revision carries P3. |

P2 means lower change urgency in the existing operation, not an optional release gate.
A replacement capture system shall demonstrate a functioning path into the existing watch
or implement the required watch behavior before it is relied on operationally. A saved
record alone is not evidence that anyone is monitoring it.

<a id="section-15-requirement-language"></a>

### 1.5 Requirement language

**Shall** — mandatory. **Should** — strongly recommended; deviation requires
justification. **May** — optional.

---

<a id="section-2-definitions"></a>

## 2. Definitions

| Term | Definition |
|---|---|
| **Log on** | An accepted record that a vessel has departed under the unit's watch, with a stated intention to return by a stated time. Until it is accepted there is a draft, not a log on. |
| **Log off** | The act of closing a log on because the vessel has returned or otherwise ended its trip. |
| **Operator** | A person, usually a volunteer, receiving log ons at a unit. |
| **Unit** | A marine rescue base holding the watch for a geographic area. |
| **Member** | A person with a standing record held by the organisation, and a member number issued to that record. A log on is a member's only when its Member No. is selected from those records (CAP-24). |
| **Public user** | A person logging on without a member record: any log on with no member selected. For a public user the vessel is the standing record (a public vessel, carrying its owner's contact details). |
| **Identifier** | A captured identifying value, whether or not it resolves: member number, vessel registration, mobile number, vessel name, person name. |
| **Verification** | Evidence that independently supplied identifiers consistently identify a stored person/vessel association; not proof of the caller or trip facts. |
| **Cross-verification** | Comparison of independently captured identifiers and their candidate associations. See §7. |
| **Draft** | A saved but unaccepted record: the mandatory set (ACC-1) is not yet complete. A draft preserves what was heard and nothing more. It is not a log on, it is not watched, and no time in it is monitored. The vessel has not been told it is logged on. |
| **Accepted** | The mandatory set is complete and saved, and with that save the operator has taken the watch. Acceptance is recorded against the saving operator and time, and is what the unit tells the vessel. There is no separate accept action (ACC-3). |
| **Mandatory set** | The values a log on cannot be accepted without (ACC-1). Absent, capture continues as a draft; nothing is refused or discarded. |
| **Watched** | The unit is counting down to an accepted log on's deadlines and will raise them as approaching and then overdue. Only accepted log ons are watched. |
| **Discard** | Throw away a draft that was never a log on: a record begun in error, or one the caller abandoned before anything identifying was given (ACC-7). An accepted log on can never be discarded; it is logged off. |
| **Active** | An accepted log on that is being watched: the vessel is out and the unit holds it. |
| **Open watch queue** | The owning unit's list of every accepted log on being watched, with its deadline condition, escalation status and verification outcome. Also called the active list. Unaccepted drafts appear alongside it, plainly marked as not watched, and are never mixed into it (WAT-1). |
| **Approaching** | A usable deadline is within the approved approaching window and current time is strictly earlier than its due time (WAT-2). |
| **Overdue** | Current time is at or after the due time of an unsatisfied effective obligation. Internal follow-up misses are labeled separately from vessel-return/report misses. |
| **Escalated** | An open escalation exists against an accepted log on. Independent of deadline amendment. |
| **ETA / ETR** | A supplied expected return (or report) day-or-date and time, represented by a timed obligation. The paper radio log heads this column "ETA/ETR" (estimated time of arrival / return). |
| **Obligation** | An expected return, position report, crossing completion, or operator follow-up, with its own status and deadline. |
| **Watch owner** | The unit accountable for the open record, including unresolved capture and pending transfer. |
| **Acknowledgment** | An operator records seeing an alert or accepting a transfer; neither action implies the vessel has returned. |
| **POB** | Persons on board. |
| **Enrichment** | Addition of detail to an existing draft or log on after its initial creation. |
| **Airtime** | Occupancy of a shared radio channel. A finite, contended resource. |

---

<a id="section-3-domain-model"></a>

## 3. Domain model

<a id="section-31-entities"></a>

### 3.1 Entities

| Entity | Description | Key attributes |
|---|---|---|
| **LogOn** | One trip record, with independent capture and watch states. | capture status, watch status, watch owner, channel, operator, call time, departure point/time, destination, POB, verification outcome, created/updated timestamps |
| **Vessel** | A boat known to the system: a member's vessel, or a public vessel standing for a public user. | registration, name, length, hull colour, type, make, model, AIS identifier; for a public vessel, owner name, phone and email |
| **Member / PublicUser** | A member is a standing record; a public user is a log on without one. Membership is not a prerequisite to capture. | member number, name, address, phone, email; emergency contacts, vessels, trailers and cars |
| **OnboardContact** | A reachable person aboard or ashore; location/role explicitly recorded. | name, aboard/ashore, relationship, number, source and confirmation time |
| **Identifier** | An independently captured value and its resolution history. | type, raw value, normalized value, source, captured time, candidates, match basis, selected record, outcome |
| **Obligation** | One expected event or internal follow-up. | kind, due date/time, raw time expression, interpretation basis/timezone, status, satisfaction/amendment evidence |
| **EscalationStep** | An action under the unit's approved escalation procedure. | procedure version, action, timestamp, actor, outcome, disposition |
| **WatchTransfer** | A request and acknowledgment of a change in owning unit. | source/target, requester, requested time, record version, accepting operator/time, outcome |
| **Location** | A departure/destination/report point. | name, optional coordinates, free-text flag, source |
| **Operator** | The authenticated person taking an action. | identity, unit, shift |

This is a conceptual model; it does not prescribe separate database tables for each row.
Automated events record a system actor and responsible unit, rather than inventing an operator.

<a id="section-32-relationships"></a>

### 3.2 Relationships

- A LogOn references at most one Member, and only by selecting an existing member record
  (CAP-24); with none it is a public user's log on. It may reference one Vessel record, and
  either may remain unknown even after capture is complete. Additional people are contacts.
  Logging on does not require creating a standing record, but a reference is always to a real one.
- A LogOn retains zero or more captured Identifiers, contacts, obligations, and
  escalation steps. It retains every transfer attempt and ownership change.
- Vessels and people have many-to-many associations. A phone number or name need not
  be unique. Registration/identifier namespaces and validity periods must be respected.
- Stored profile changes do not rewrite historical trip evidence. A log on retains the
  values, source and verification basis used at the time, alongside links to current profiles.

<a id="section-33-draft-log-on-logged-off"></a>

### 3.3 Draft, log on, logged off

There are three states a record can be in, and one gate between the first two.

**Draft.** Saved, owned by the capturing unit, and not watched. A draft exists from the first
keystroke and holds any subset of what was heard, including nothing (CAP-1, CAP-2). It is not a
log on. No time in it is monitored, no deadline in it can become overdue, and the interface
shall never imply otherwise. A draft is either finished and accepted, or discarded because it
was never a log on (ACC-7). It is never left alone: an unaccepted draft is chased under ACC-5,
because the caller may be at sea believing the opposite.

**Logged on** (stored `loggedOn`). The mandatory set is complete and an operator has saved it, which accepts the log on
(ACC-1, ACC-3). This is the moment the unit takes the watch and the moment the vessel is told it is
logged on. Deadlines are evaluated from this instant, so a return time already in the past is
overdue immediately (ACC-4). One vessel has one open log on; a vessel already being watched
cannot be accepted again (ACC-6).

**Logged off.** The watch has ended, by explicit operator action with the time and the evidence
(WAT-7). Every reason ends this way, whether the vessel returned, never departed, or the trip
ended some other way: a log on happened, so it is logged off. There is no separate cancellation
of an accepted log on. The reason is recorded and distinguishes a real trip from one that never
sailed, which matters because identity is built from past trips (§7).

Ownership is not a state. The capturing unit owns the record from creation, draft included, and
keeps it until log off or an acknowledged transfer. When shared creation is unavailable, CAP-19
and CAP-20 require an explicit local-only state and the approved fallback; a local capture shall
never be shown as present in the shared record.

**Deadline condition**, for accepted log ons only: Not yet due, Approaching, or Overdue.
Approaching applies within the approved window and strictly before the due instant; at the due
instant the condition is Overdue (WAT-2). Alert delivery remains subject to WAT-3 latency. An
accepted log on always has a usable return deadline, because one is in the mandatory set, so
"no usable deadline" is a draft condition and not a watch condition. Unresolved replacement
input does not silently remove an existing deadline (WAT-10).

**Escalation status:** None, Open, or Closed. An open escalation remains open after an ETA
change until an authorized operator records its disposition. Alert acknowledgment, further
capture and transfer do not close it.

| Action | Preconditions and result |
|---|---|
| Begin capture | Create a Draft owned by the capturing unit. Not watched. Visible and chased under ACC-5. |
| Enrich | Add or amend any value on a draft or an accepted log on, in any order, at any time (CAP-3, CAP-13). |
| Save with the mandatory set complete | Accepts the log on in the same save (ACC-3), unless another open log on holds this vessel (ACC-6), when it stays a draft and keeps everything. Draft → Logged on; record the saving operator and time; evaluate deadlines immediately (ACC-4). |
| Discard | A draft only, and only one that was never a log on: begun in error, or abandoned before anything identifying was given. Record actor, time and reason (ACC-7). |
| Deadline passes | An accepted log on becomes Overdue for that obligation; alert under WAT-3. |
| Amend obligation | Retain the previous deadline and its reason and source; recompute the condition. An existing escalation requires explicit disposition. |
| Begin escalation | Record the approved procedure and actor. May precede a deadline where that procedure authorizes it. |
| Log off | Explicit operator action on an accepted log on, with the time, the evidence and the reason. Resolve each open obligation and escalation explicitly; do not silently mark them fulfilled. |
| Request transfer | Keep source ownership and monitoring; record the transfer pending. |
| Accept transfer | Change owner to the receiving unit through the acknowledged protocol (WAT-8); preserve every open condition. |
| Correct a mistaken closure | Authorized reopen with a reason, restoring ownership and evaluating unsatisfied deadlines immediately; preserve the closure event. |

Closed and discarded records remain searchable and auditable. Corrections are appended with an
explicit reason; they never silently resume or stop monitoring. There is no terminal
"Transferred" state: transfer changes ownership, not whether the trip is open.

<a id="section-34-log-on-variants-and-obligations"></a>

### 3.4 Log on variants and obligations

| Variant | Obligations |
|---|---|
| **Standard** | Expected return, plus any agreed follow-up. |
| **Long term** | Individually tracked position-report deadlines and, where known, expected return. A report does not log off the trip. |
| **Bar crossing** | Its own crossing-completion deadline, optionally within the same trip as a later return deadline. Completing the crossing does not satisfy the return obligation. |

Variants use the same trip model. Each missed obligation remains independently visible;
fulfilling one does not fulfill another. Report schedules, tolerance and escalation policy
must be confirmed by the unit before operational use (Appendix D). Internal operator
follow-up deadlines are labeled as such and are never presented as caller-supplied ETAs.

---

<a id="section-35-the-process-ideal-and-otherwise"></a>

### 3.5 The process, ideal and otherwise

The ideal call is short and this specification barely matters to it. Everything hard in the
document is about the calls that are not ideal, and there are more of those than of the other
kind. This section names them, so that no requirement below looks arbitrary.

**The ideal call.** The vessel calls. The operator takes identity, persons on board, departure
point, where they are going, and when they will be back. The mandatory set is complete, so the
operator's save logs it on, and the operator tells the vessel so: *"Vessel Sea Dog, you are logged on, back
by fifteen hundred."* The unit is now counting down. The vessel returns and calls. The operator
logs it off. Nothing in the ideal call needs a draft, a warning or a follow-up.

**Everything else.** In rough order of how often it is reported:

| What happens | What the system must do |
|---|---|
| The caller rings off before giving everything, or the channel is lost | Keep what was heard as a draft. Do not claim a watch. Chase it (ACC-5): the caller may believe they are logged on. |
| A priority call interrupts capture | Suspend and resume without loss; several drafts open at once (CAP-6). |
| Identity arrives late, on this call or a later one | Accept nothing until it does; the save that adds it accepts and evaluates the deadline at once, so a return time already past is overdue immediately (ACC-4, OC-6). |
| The caller gives one identifier only | Not acceptable; the second is the unit's accuracy check (ACC-1, A.8). |
| Two identifiers disagree | Show the conflict, do not resolve it silently, and let the operator clarify (IDV-2, IDV-3). |
| A registration is misheard | Offer the near match with the substituted character named, never as a match (IDV-6). |
| The return time is ambiguous, unreadable, or a day without a time | No deadline, so not acceptable. Keep the words, say why, and ask (CAP-23, REC-6). |
| The vessel is already logged on | Refuse a second log on and take the operator to the one that is open (ACC-6). |
| The previous trip was never logged off, and the vessel calls again | The same refusal, which is how the stale record gets found and closed. |
| The operator begins a record by accident | Discard it; nothing was logged on (ACC-7). |
| The trip is abandoned before departure | If it was accepted, log it off with that reason. If it was still a draft, discard it. |
| The shift ends with drafts open | Handover presents and acknowledges every draft as well as every watch, because a draft monitors nothing and only a person carries it (WAT-6). |
| The vessel does not return | Overdue, alert, and the approved escalation procedure (WAT-3, WAT-4). |
| The vessel returns and does not call | Identical to the above from the unit's side, which is why escalation begins with contact rather than with search. |
| The vessel reports in on a long trip | A report satisfies that obligation and not the return (§3.4). |
| Nobody has a browser open | Deadline evaluation continues regardless (WAT-3). This is the requirement most easily left unbuilt and least survivable. |
| The save fails, or the connection drops | Say so plainly, never claim a shared record that does not exist, and recover what was typed (CAP-19, CAP-20). |
| Two operators work the same record | Preserve both, resolve conflicts explicitly, never silently overwrite (CAP-22). |
| A closure was wrong | Reopen with a reason, keep the closure, re-evaluate the deadline (§3.3). |

The pattern across all of them is the same. Keep what was heard, state what is missing, never
invent, and never let the interface imply a watch the unit does not hold.

---

<a id="section-4-operating-context"></a>

## 4. Operating context

Context that constrains the requirements. Stated as fact, not as complaint.

**OC-1.** Log ons arrive by marine radio, telephone, in person, and self-service. Radio
is reported as dominant at the observed unit and drives the capture design. Other channels
require their own acceptance checks; self-service submissions require a defined unit
acceptance/acknowledgment path and shall not imply an established watch merely by submitting.

**OC-2.** A radio log on is an interview, not a dictation. The caller states a rough
intention; the operator elicits the remaining detail by asking. Field order is arbitrary
and varies per call.

**OC-3.** Local observations report varying caller information and operator interview
order. The system shall not assume a consistently followed script. This does not establish
that no organisational procedure exists; applicable procedures must be identified and
represented accurately, particularly for escalation and handover.

**OC-4.** Airtime is contended. Every question the operator asks occupies a shared
channel that other vessels are waiting on. The system shall treat operator questions as
a cost to be minimised.

**OC-5.** Local observations report inconsistent phonetic use and recurring letter
confusions. Letters and digits can both be misheard. Appendix B is an initial candidate
matching heuristic to validate against observed errors, not a guarantee of identity or
a substitute for clarification and approved radio procedures.

**OC-6.** Identifying detail — vessel registration, mobile number — typically arrives
late in a call or only when asked, and sometimes on a later call. It shall not be
required early.

**OC-7.** A requirement for a computer record has been reported locally. Its legislative,
policy or contractual basis, permitted media, retention period and evidentiary requirements
are **not yet established by this specification**. Appendix D question 5 must be resolved
before claiming compliance. Immediate durable capture is justified operationally regardless.

**OC-8.** Calls arrive in bursts. Peak load is a period of good weather, which is also
when the greatest number of vessels are at sea.

**OC-9.** The unit's paper radio log (Figure 5, transcribed in A.1) is the primary operational
record and the first thing filled out for every call. A paper row is not a log on: a vessel is
logged on only when the system has it logged on (ACC-9). A paper row exists from the first pen
stroke with whatever cells are known, is completed across the call in whatever order the
caller supplies, and is the reference a system record is checked against. Any system that
performs this function shall fit the paper log, not the other way round: its columns, their
headings and their order are the unit's standard (DAT-6).

---

<a id="section-5-requirements-capture-p1"></a>

## 5. Requirements — Capture (P1)

**CAP-1.** The system **shall** persist a log on record containing any subset of fields,
including an empty subset, from the moment capture begins. Shared persistence requires
the acknowledgment in CAP-19; during an outage CAP-20 governs recovery, and the interface
shall not imply that an unacknowledged capture is shared or monitored.
*Rationale: retaining partial information prevents a missing operational record. Legal
sufficiency remains subject to OC-7. Persistence and failure semantics are defined in §5.2.*

**CAP-2.** The system **shall not** require any field to be populated in order to create,
save, or retain a log on.
*Rationale: any mandatory field is a point at which capture can fail entirely (PSO).*

**CAP-3.** The system **shall** accept field entry in any order, with every field
reachable and editable from the keyboard without pointing-device interaction.
*Rationale: OC-2. Entry order is dictated by the caller.*

**CAP-4.** Unsupplied trip facts **shall** remain empty. The system **shall not** invent
POB, destination, departure time or ETA. It **may** record authenticated operator, unit,
entry time and reliably known channel as system metadata, visibly distinct from reported
facts. Previously stored details **shall** be offered with source/age and confirmation
status; applying them shall retain that provenance, not imply fresh caller confirmation.
*Rationale: a known system fact is not a guessed trip fact. Reuse must not conceal uncertainty.*

**CAP-5.** Where the system detects an inconsistency — for example an ETA preceding the
departure time — it **shall** present the warning adjacent to the field concerned, at the
time of entry, and **shall** permit the record to be saved regardless.
*Rationale: inconsistency is information; preventing the save discards the record to
protect the field.*

**CAP-6.** The system **shall** permit multiple log ons to be in Draft simultaneously, and
**shall** permit an operator to suspend and resume capture of any Draft without loss.
*Rationale: a priority radio call may interrupt capture at any point.*

**CAP-7.** The open watch queue, and the count of unaccepted drafts beside it, **shall** remain
visible during capture of a new log on (WAT-1).
*Rationale: situational awareness is the operator's primary function; capture must not
suspend it.*

**CAP-8.** The system **shall** accept time input in the forms operators speak and write,
including 24-hour (`1500`), 12-hour (`3pm`), and relative (`+2h`).
*Rationale: format conversion is cognitive load during a timed task.*

**CAP-9.** The system **shall** accept free text for departure point and destination, and
**shall** offer known locations as suggestions without restricting entry to them.
*Rationale: callers name places that exist in local usage and in no list.*

**CAP-10.** The system **shall** display, during capture, which fields remain unpopulated.
*Rationale: the visible gap list supports an interrupted interview; it does not replace
approved operating procedures (OC-3).*

**CAP-11.** The system **shall** rank unpopulated fields by the priority in §6.1, giving
greatest prominence to fields serving PSO and least to vessel description.
*Rationale: OC-4. Undifferentiated prompting spends airtime on low-value fields.*

**CAP-12.** Prompting under CAP-10 and CAP-11 **shall** be advisory. It **shall not** prevent
anything from being captured, saved, retained or amended, and **shall not** be the mechanism by
which acceptance is withheld. Acceptance is gated by the mandatory set alone (ACC-1), which is a
stated rule rather than a prompt, and gates nothing else.
*Rationale: the operator, not the system, judges what is worth a transmission. What the operator
cannot judge away is the minimum the unit has agreed it needs before undertaking a watch.*

**CAP-13.** The system **shall** permit any field of an existing log on in any open state
to be populated or amended, with the same interaction cost as initial capture.
*Rationale: OC-6. Late-arriving detail is the normal case.*

**CAP-14.** Capture of a log on for a person without a standing record **shall** proceed
without first classifying the caller, and **shall not** require vessel description fields
before the log on is created.
*Rationale: classification is a decision the operator cannot make until identity is
known, which is late (OC-6). Volunteered description or contact details may be captured
at any point, including while identity remains unknown (CAP-3).*

**CAP-15.** Where vessel or contact detail has been captured previously for the same
vessel or person, the system **shall** offer it rather than requesting it again.
*Rationale: OC-4. Re-asking known detail spends airtime for no information gain.*

<a id="section-51-capture-performance"></a>

### 5.1 Capture performance

**CAP-16.** For a caller whose identifiers resolve to an existing record, and who supplies
all requested detail without repetition, a complete log on **shall** meet the
**30-second 95th-percentile target**, keyboard only, under CAP-18.

**CAP-17.** For a caller with no existing record, a complete log on **shall** meet the
**90-second 95th-percentile target** under CAP-18.

**CAP-18.** Simulation **shall** be used before operational trials; it is not sufficient
for final performance acceptance. Final evaluation **shall** observe authorized real-call
use under peak load without compromising the existing watch. The approved measurement
protocol shall define a complete capture, timing start/end, operator experience, sample
size, peak-load conditions and interruptions. Report median, 95th percentile, maximum,
error/correction rate and live-entry proportion separately for known and unknown callers.
The 30/90-second targets apply to the 95th percentile of eligible calls; no field may be
fabricated or warning hidden to meet them. Record excluded/interrupted calls separately.
Report both end-to-end elapsed capture time and operator interaction time; do not count
only keystrokes while excluding normal caller speech from the elapsed measure.

<a id="section-52-persistence-interruption-and-concurrent-work"></a>

### 5.2 Persistence, interruption and concurrent work

**CAP-19.** Begin capture **shall** immediately attempt durable creation and subsequent
edits **shall** be retained automatically without a final Save dependency. The interface
shall distinguish Saving, Saved to the shared record, and Not saved to the shared record.
It shall claim Saved only after durable acknowledgment. Any local recovery copy must be
labeled separately; local storage alone does not establish a shared watch.

**CAP-20.** Loss of connectivity, rejected saves and unavailable shared monitoring **shall**
be conspicuous. Captured edits shall be recoverable after interrupted browser sessions
on the same supported workstation, subject to the approved recovery envelope. Recovery
shall preserve raw input, original capture time and pending actions. Cross-workstation
availability shall be stated honestly. The operational fallback and recovery envelope
(including workstation/power loss) require approval before live use; no claim of zero loss
may be made without demonstrated coverage.

**CAP-21.** Retrying creation, edits or queued recovery actions **shall not** duplicate
trips, obligations, transfer acceptance or closure events. Reconnection shall reconcile
pending work without silently overwriting later shared edits. Suspected duplicate calls
shall be shown for operator review; uncertain identities shall not trigger automatic merging.

**CAP-22.** Concurrent changes **shall** preserve both operators' evidence. Conflicting
changes, especially ETA, identity, ownership and closure, shall be presented for explicit
resolution; stale edits shall not silently replace current values. Operators shall see
that another operator is working on the same open record.

**CAP-23.** Unknown, explicitly unavailable, not applicable, and inconsistent values
**shall** remain distinguishable. Unparsed or implausible input shall be retained as
captured with a warning rather than silently discarded, rounded or converted into a
credible-looking operational value. Only a usable, explicitly interpreted deadline can
drive vessel overdue detection; unresolved time input invokes WAT-9. When amending an
existing deadline, saving unresolved input is distinct from replacing the effective
monitored deadline (WAT-10). A reference to a standing record is not a captured value; CAP-24
governs what happens to one that does not resolve.

**CAP-24.** The Member No. of a log on **shall** only ever hold an existing member record, chosen
from the unit's members. A member number heard that names no member **shall not** be stored as
the Member No.: the box is left blank, the number heard is kept in the log on's notes, and the
log on is a public user's. It is not refused and nothing else captured is lost (ACC-8).
*Rationale: database integrity. A Member No. that points at nobody looks like a member's log on
and is not one; the next operator reads it as verified membership. What the caller said is still
evidence, so it is kept where it cannot be mistaken for a record: in the notes.*

---

<a id="section-53-acceptance-the-gate-between-a-draft-and-a-watch"></a>

### 5.3 Acceptance — the gate between a draft and a watch

**ACC-1.** A log on **shall not** be accepted until its mandatory set is complete. The mandatory
set is: **at least two of** member number (a member record, CAP-24), vessel name, vessel registration and mobile number;
**and** persons on board, departure point, where the vessel is going, and a usable return
day and time. Two identifiers rather than all four, because agreement between two independently
supplied values is the unit's accuracy check (A.8, IDV-1). A usable return time, because without
one there is nothing to count down and therefore nothing to accept. Once accepted, a save
**shall not** empty or make unreadable any value of the mandatory set: the save is refused, nothing
is written, and the values it would lose are named (WAT-10).
*Rationale: this is the existing platform's mandatory set as observed (A.10) and the paper log's
row (A.1), with the identity columns read the way the paper reads them: a couple of them, not all.*

**ACC-2.** An unaccepted draft **shall not** be watched. No time in a draft shall be monitored,
raised as approaching, or raised as overdue, and no part of the interface shall present a draft
as being under watch. A draft **shall** be labeled as not a log on wherever it appears.
*Rationale: a watch the unit cannot act on is not a watch, and a record that looks watched and
is not is worse than one that plainly is not. The consequence is ACC-5, without which this
requirement is unsafe (§1.2).*

**ACC-3.** Saving a draft whose mandatory set is complete and valid **shall** accept it, in that
same save, recording the saving operator and the time. There **shall not** be a separate accept
action. The save **shall** be the point at which the unit undertakes the watch, and the operator's
acknowledgment to the vessel corresponds to it (ACC-9). A save that leaves the set incomplete keeps a
draft; a save refused acceptance under ACC-6 keeps a draft with everything captured.
*Rationale: the operator fills in the required details because the vessel is logging on; once they
are there, the unit has accepted it. A second confirmation adds a step and a way to leave a
complete record unwatched. Nothing is accepted by filling in a box, only by saving.*

**ACC-4.** On acceptance the system **shall** evaluate every deadline immediately. A return
time already in the past **shall** be overdue at once, not at the next transition or refresh.
*Rationale: OC-6. Identity arrives late, so acceptance often follows the stated return time
by a long way, and on a late entry the trip may already be overdue before the watch begins.*

**ACC-5.** Every unaccepted draft **shall** have accountable follow-up under the unit's
approved policy: a named duty role, an interval, a reminder and an escalation if it remains
unresolved, surviving operator interruption and shift end (WAT-6, WAT-9). The follow-up
**shall** be labeled as internal and never presented as a vessel deadline. Drafts **shall**
be counted and shown persistently, not only on the page where they were created.
*Rationale: the caller may be at sea believing they are logged on. Nothing else in this
specification is watching them. This requirement is what makes ACC-2 tolerable, and a
deployment that implements ACC-2 without it is less safe than one that implements neither.*

**ACC-6.** A vessel with an open log on **shall not** be given a second one. Where a vessel is
identified on a draft and that vessel already holds an open log on at this unit, the system
**shall** refuse acceptance, name the open record, and offer it to the operator instead. The
refusal **shall not** discard what was captured.
*Rationale: a vessel is either out or not. Two open log ons for one vessel means either the
same call written down twice, or a previous trip never closed; both are found by refusing here.
Cross-unit duplication is bounded by transfer (WAT-8) and remains an open question (Appendix D).*

**ACC-7.** A draft **shall** be discardable: a record begun in error, or abandoned before
anything identifying was captured, was never a log on and shall not have to be closed as
though a vessel had sailed. Discarding **shall** record actor, time and reason, and the record
**shall** remain searchable and auditable. An accepted log on **shall not** be discardable; it
is logged off (WAT-7). A discarded record **shall not** count as evidence of a vessel or a
person (§7).
*Rationale: a log on that happened is logged off. A record that was never a log on is neither
watched nor closed as if it had sailed; pretending otherwise puts a trip in the history that
never took place.*

**ACC-8.** Where the mandatory set is incomplete, the system **shall** say which values are
missing and **shall not** refuse, discard or alter anything already captured (CAP-1, CAP-2).
Acceptance is the only thing withheld.

**ACC-9.** The operator **shall** end the call by telling the vessel it is on the log only when the
system shows it logged on: the save has accepted it. A paper row, a draft, or details still being
typed are not a log on, and a vessel **shall not** be told it is logged on on the strength of them.
*Rationale: the only log on that exists is the one on the computer log. Telling a vessel it is
logged on before then is telling it something untrue, and it is exactly the failure §1.2 names:
a vessel at sea believing it is under a watch that nobody is keeping.*

---

<a id="section-6-requirements-data-p1"></a>

## 6. Requirements — Data (P1)

<a id="section-61-field-priority-classes"></a>

### 6.1 Field priority classes

| Class | Purpose | Fields |
|---|---|---|
| **A** | Locate the vessel | ETA, POB, destination, departure point, departure time |
| **B** | Identify and verify | Member number, vessel registration, mobile number |
| **C** | Reach the vessel | Radio channel monitored, onboard/shore contact, AIS identifier |
| **D** | Describe the vessel | Length, hull colour, type, make, model |

The paper log (A.1) already holds classes A, B and D: Class A as *POB · Departure Point ·
Going to · ETA/ETR (Return Day or Date · Time)*, Class B as the three shaded mandatory columns
*Member No. OR Vessel Name · Vessel Rego. No. · Mobile Phone Number*, Class D as *Vessel
Details*. Class C is not on the paper log; it is additional (DAT-6).

**DAT-1.** Class A fields **shall not** be a gate on saving, retaining or amending anything;
a record holding any subset of them persists (CAP-1). Most of Class A is, however, in the
mandatory set that gates acceptance (ACC-1): persons on board, departure point, destination and
a usable return time. A record short of it stays a draft, is plainly not watched, and is chased
under ACC-5. Class C and Class D gate nothing.

**DAT-2.** The mobile number **shall** be treated as both a Class B identifier and a
Class C contact, and prioritised accordingly.
*Rationale: it serves double duty — it identifies the caller and is the first action on
overdue.*

**DAT-3.** Previously stored Class D fields **shall not** be routinely requested again
solely to populate the form. They shall be offered with provenance under CAP-4/CAP-15.
The operator may clarify stale or conflicting details or use description to distinguish
candidates (IDV-7), and may retain volunteered corrections without blocking capture.

**DAT-4.** The system **shall** retain Class D detail captured for a person without a
standing record, and associate it with the vessel for reuse.

**DAT-5.** Every captured identifier **shall** be stored as captured, independently of
whatever record it resolves to. A member number that resolves to no member is kept in the
notes rather than as the Member No. (CAP-24).
*Rationale: the value the operator heard is evidence; overwriting it with the resolved
value destroys the ability to detect a mis-resolution later.*

**DAT-6.** The capture view and the open watch queue **shall** carry every *trip* column of the
unit's paper radio log (A.1 columns 1 to 12), under the same headings and in the paper log's
order, so that a paper row and a system record correspond cell for cell. Fields the paper log
does not have (Class C, and system metadata) follow after the paper columns and are visibly
additional. The return day-or-date **shall** be its own field beside the return time, as on paper.

Columns 13 to 15 are **not** trip columns and **shall not** be reproduced as though they were.
They record the transcription of the paper row into a separate computer system: its trip number,
a tick that the row was entered, and an initial that the log off was entered. A system performing
this function cannot know them about itself, and answering them with its own record number, entry
time and operator makes three cells silently mean something other than what the heading says.
Such a system **shall** instead show its own reference plainly, marked as its own, and **shall**
state what those three paper columns are for. Whether they survive at all is Appendix D question 15.
*Rationale: OC-9. The paper log is what operators already fill out and check against; a
screen laid out the same way costs nothing to learn and makes transcription and
reconciliation a one-to-one read. A dedicated return-day field is what makes REC-6's
day-rollover clarification a normal question rather than an exception.*

---

<a id="section-7-requirements-identification-verification-and-search-p1"></a>

## 7. Requirements — Identification, verification and search (P1)

<a id="section-71-cross-verification"></a>

### 7.1 Cross-verification

**IDV-1.** The system **shall** support two or more independently supplied identifiers.
Repeated entry of the same identifier, a normalized duplicate, or a value populated from
the first match shall not count as independent corroboration. Record whether each value
was supplied on this call, imported, selected from a profile, or corrected after clarification.

**IDV-2.** Resolution **shall** operate over compatible person/vessel associations, with
explicit handling of non-unique identifiers. The following decision order shall yield
exactly one outcome: Conflict first; otherwise Unverified when fewer than two independent
identifiers are supplied or none resolve exactly; otherwise Verified if its conditions
hold; otherwise Partial. Candidate detail remains visible under every outcome.

| Outcome | Condition |
|---|---|
| **Verified** | At least two independent supplied identifiers have exact normalized matches whose intersection uniquely identifies one person/vessel association; no captured identifying evidence contradicts it or remains unresolved. |
| **Conflict** | Exact resolving evidence has incompatible candidate associations, or retained evidence explicitly contradicts the selected association. |
| **Partial** | At least two independent identifiers are supplied, at least one resolves exactly, no conflict exists, and Verified is not established because evidence is unmatched/approximate or the association remains ambiguous. Display the reason. |
| **Unverified** | Fewer than two independent identifiers, or no exact evidence resolves. |

Conflict takes precedence over other outcomes. A member with several vessels is not a
conflict merely because there are several associations. Shared numbers and names do not
prove uniqueness. A vessel identified without a person may be selected and watched, but
does not meet the stated Verified person/vessel criterion. The display shall explain
which person, vessel and evidence are matched rather than show a badge alone.

**IDV-3.** Conflict **shall** be shown prominently immediately. The operator shall be able
to inspect all captured values and match bases, request clarification, append a correction,
select a provisional association with a reason, or leave identity unresolved. A provisional
selection shall not dismiss the conflict or relabel it Verified. Explicitly superseded
incorrect values remain in history; verification is recomputed from current evidence.

**IDV-4.** The outcome, evidence, match method and selected association **shall** be stored
and shown on the open watch queue and record. Changes shall be versioned. Later profile
edits shall not silently change what was verified at the time of the call.

**IDV-5.** An outcome other than Verified **shall not** block creation, saving, completion,
or watch acceptance. Verified refers only to consistency with stored identity associations;
it does not authenticate the caller, validate trip facts, confirm contact reachability,
or establish a vessel's current location.


<a id="section-72-tolerant-resolution"></a>

### 7.2 Tolerant resolution

**IDV-6.** Resolution **shall** offer labeled near-match candidates in addition to exact
matches, using Appendix B as an initial heuristic. Exact candidates shall be ranked first;
matched/substituted characters and match basis shall be visible. Selecting a near match
shall not make the raw captured value exact or establish Verified. Clarification may
append a corrected supplied value while retaining the original.
*Rationale: tolerate plausible capture errors while keeping uncertainty visible (OC-5).*

**IDV-7.** Resolution results **shall** include sufficient descriptive detail — vessel
name, length, hull colour, type, associated member — to allow the operator to confirm
identity by description.
*Rationale: descriptive detail offers another route to clarification. Its reliability
relative to readback is not established by this specification.*

**IDV-8.** Multiple candidates **shall** be presented in one comparison view, without
silently selecting the first. Large sets may be paginated with visible counts and no
hidden truncation. Profile freshness and uncertainty shall be visible.

**IDV-9.** Normalization rules and identifier namespaces **shall** be explicit and tested.
Formatting normalization may yield an exact match; character substitution is approximate.
Neither normalization nor profile selection shall overwrite the value as captured.

<a id="section-73-search"></a>

### 7.3 Search

**SRCH-1.** The system **shall** provide a single search input that returns results across
all record types: members, public users, vessels, drafts, accepted log ons, and
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

**SRCH-6.** Every applicable search result **shall** offer one action to apply its identity
or offered profile detail to the current capture. Show what will be applied. A historical
trip shall not supply current ETA, POB, destination or departure facts; selecting an open
trip shall offer resumption rather than silently create a duplicate. Permission boundaries
shall apply across all search types (REC-7).

---

<a id="section-8-requirements-watch-and-overdue-p2"></a>

## 8. Requirements — Watch and overdue (P2)

**WAT-1.** The system **shall** display the persistent open watch queue: every accepted log on
this unit is watching, with its next deadline, every missed obligation and any open escalation.
Overdue and escalated records **shall not** be hidden by a deadline-order sort. Age, watch owner
and synchronization health **shall** remain visible.

Unaccepted drafts **shall** be shown persistently alongside the queue and **shall not** be mixed
into it. Their count **shall** be visible wherever the queue is, with the values each is missing
and the age of each, so that a draft cannot be mistaken for a watch and cannot be quietly lost
(ACC-2, ACC-5).

**WAT-2.** The system **shall** indicate log ons approaching their ETA before that ETA
passes. The approaching window is an approved configuration value, not a constant of this
specification (Appendix D question 9). For effective due time D, current time T, and
approved window W, Approaching means D − W ≤ T < D; an unsatisfied obligation is Overdue
when T ≥ D. An approaching indication shall be distinct from a missed-obligation alert
under WAT-3. The next-deadline display shall cover report and crossing obligations as
well as return, without hiding an already-missed obligation.

**WAT-3.** A missed obligation on an accepted log on **shall** produce an alert independent of
the operator observing a list change. Drafts have no obligations to miss; their follow-up is
ACC-5, which has the same independence requirement. Deadline evaluation shall continue without an open capture page
or browser. The approved deployment shall define detection/delivery latency, notification
recipients, acknowledgment, repeat/unacknowledged-alert behavior and monitoring-health
failure notification. On restart or reconnect, already-missed obligations shall be
reconciled and surfaced, not postponed until another state transition. Acknowledgment
records attention; it neither satisfies the obligation nor closes escalation.

**WAT-4.** The system **shall** present the owning unit's approved escalation procedure,
including its version, and record attempted actions with time, actor, outcome and any
authorized deviation. The procedure, responsibilities and contact paths must be approved
before live use. Software shall not invent rescue policy from a generic checklist.

**WAT-5.** On transition to Overdue, the system **shall** surface the log on's verification
outcome (IDV-2).
*Rationale: personnel about to act on the record need to know which parts of it are
verified.*

**WAT-6.** Shift handover **shall** present and acknowledge all open records, including
incomplete/unresolved capture, pending saves, missed obligations, pending transfers and
open escalation. Record outgoing/incoming operators and outstanding responsibilities
without re-keying. Unit ownership and monitoring shall persist through shift change.

**WAT-7.** A record **shall** leave the owning unit's open queue only through explicit,
authorized log off, cancellation or acknowledged transfer under §3.3. Record actor, time,
reason/evidence and disposition of obligations/escalation. Alerts, refreshes, time passage
and further capture shall not silently remove it.

**WAT-8.** Transfer **shall** preserve the complete record without re-keying. The source
unit remains responsible until the receiving unit explicitly accepts the current transfer
and durably receives the current open obligations/escalation state. Acceptance shall make
one authoritative ownership change, visible to both units, without a monitoring gap.
Stale acceptance shall require review of intervening changes. Rejected, timed-out, retried
or disconnected transfer attempts shall retain source responsibility until reconciled;
the transfer itself shall never fulfill a deadline or close escalation.

**WAT-9.** Every unaccepted draft, and every accepted log on with an unresolved deadline
amendment, **shall** have accountable follow-up under the owning unit's approved policy (ACC-5).
The policy **shall** name the responsible duty role, the interval, the recipient, the reminder
and the escalation, including operator interruption and shift end. Unit responsibility
**shall not** depend on the operator who began the record coming back to it.

A draft's follow-up is the only thing standing between an unfinished call and a vessel nobody
is counting down. It **shall** therefore be treated as a safety function and not as a tidiness
reminder: its interval, its escalation and its delivery are subject to the same approval and the
same demonstrated reliability as WAT-3.

Label the follow-up and any missed follow-up alert as internal, not as a caller-supplied
ETA or evidence that the vessel has failed to return. Vessel deadlines continue to be
monitored independently. Accepting the record resolves only the acceptance follow-up;
missing-deadline or unresolved-amendment follow-up remains until explicitly resolved.

**WAT-10.** Each obligation **shall** retain its own fulfillment/amendment evidence.
A later report or revised ETA shall not erase a previous miss. An ETA change following
escalation shall retain the open escalation until explicit authorized disposition.
A new effective due time shall be shown with its source and the previous due time accessible.
Saving a blank, unparsed or ambiguous replacement retains that input and its warning but
shall not silently cancel or replace the last effective deadline. Show both the effective
monitored deadline and the unresolved proposed change. Replacing or withdrawing the
effective deadline requires an explicit operator action with source/reason; a valid past
replacement is evaluated immediately. If a deadline is explicitly withdrawn without a
usable replacement, retain the miss/history and invoke the no-usable-deadline follow-up
under WAT-9. Withdrawing a deadline never implicitly closes an open escalation.

---

<a id="section-9-requirements-record-and-audit-p2"></a>

## 9. Requirements — Record and audit (P2)

**REC-1.** The system **shall** support durable records, retention, integrity and export.
The responsible organisation shall identify and approve the applicable legal/policy basis,
retention schedule, access, disposal and export obligations before claiming the system is
its compliant official record (OC-7). This draft does not itself establish compliance.

**REC-2.** Every log on and subsequent action **shall** record actor, unit, event/entry
time and available channel/source. Automated events shall identify the system actor;
unknown channels remain unknown. Reported call time and departure time shall remain
separate from automatic entry time. Late entries shall retain both event and entry times.

**REC-3.** Amendments **shall** be appended. Prior values **shall** remain retrievable.
*Rationale: post-incident review requires knowing what was known at each point in time,
not only the final state.*

**REC-4.** Verification outcomes and raw identifiers (DAT-5) **shall** remain part of the
audit record for the approved retention period, including superseded interpretations.

**REC-5.** The system **shall** report on operational measures including call volume by
period, overdue frequency, escalation outcomes, and **the proportion of log ons captured
during the call versus entered afterwards**.
*Rationale: the latter measures whether capture is keeping pace with the radio. The
measurement protocol shall establish call start/end or a recorded live/late/unknown
classification; entry timestamps alone cannot establish when the call occurred.*

**REC-6.** Interpreted times **shall** include full date, time and timezone. Preserve raw
time input and the reference instant for relative expressions. `+2h` shall use the displayed,
recorded reference (normally the call time when known, otherwise the entry time), not be
recalculated on reload. Ambiguous day rollover, past-date entry and timezone interpretation
shall require clarification or remain unresolved; never silently shift an elapsed deadline
to tomorrow. Changes append a new interpretation. Time-source health and acceptable clock
error shall be defined in the approved monitoring configuration.

**REC-7.** Access **shall** be authenticated and authorized by role/unit for search, edit,
export, closure, reopening, transfer and escalation. Record access-relevant administrative
actions. Session expiry shall not silently lose capture or stop shared monitoring. Public
self-service shall not expose other people's records or grant operator privileges.

**REC-8.** Recovery **shall** be demonstrated by restoring representative records,
identifiers, histories, ownership and obligations into an isolated environment. The approved
recovery-time and data-loss limits shall be documented, including reconciliation of changes
made during outage. Restored missed deadlines shall be evaluated before resuming live watch;
a backup file existing is not evidence that recovery works.

**REC-9.** Each record **shall** carry a Trip ID No., issued when the record is first saved from one
running sequence, unique, and never reused or changed. It **shall** be what the interface shows and what
alerts, reports and exports quote. Any internal identifier **shall not** be the thing an operator is asked
to read out. A list's position numbers (1, 2, 3 down what is on screen) are not a record's number.
*Rationale: the paper log already has a Trip ID No. column (Appendix F, figure 5, column 13), so the Trip
ID No. is what a paper row and a system record have in common when someone reads one to the other. A
second number counting from one each day overlapped it, skipped where drafts were discarded, and left
open when a day starts (withdrawn question 21).*

---

<a id="section-10-acceptance-criteria"></a>

## 10. Acceptance criteria

Each criterion is a pass/fail test against a running system. Criterion identifiers are stable
across revisions: criteria added after version 0.4 take the next free number, so numbering
within a section is not always contiguous.

<a id="section-101-capture"></a>

### 10.1 Capture

| # | Test | Pass condition |
|---|---|---|
| **AC-1** | Begin a log on, enter nothing, save. | Record persists and is retrievable. |
| **AC-2** | Enter only POB and destination. Save. Close the session. Reopen. | Record persists with those two fields. |
| **AC-3** | Inspect a new capture and apply offered profile details. | Trip facts remain empty; automatic metadata and reused/unconfirmed profile values are visibly distinguished and retain provenance. |
| **AC-4** | Enter an ETA earlier than the departure time. Save. | Warning shown beside the field; save succeeds. |
| **AC-5** | Begin a log on, start a second, return to the first. | Both retained, neither altered. |
| **AC-6** | Capture a log on while the active list is on screen. | Active list remains visible throughout. |
| **AC-7** | Complete a full log on using keyboard only. | Achievable; no pointing device required. |
| **AC-8** | Enter `1500`, `3pm`, `+2h`; include midnight rollover and late entry. | Raw values retained; full interpreted date/time, timezone and reference shown; ambiguity is clarified or visibly unresolved; reload does not move a relative deadline. |
| **AC-9** | Enter a destination not present in any list. | Accepted as entered. |
| **AC-10** | Measure eligible known-caller captures under the approved peak-load protocol. | 95th percentile ≤ 30 seconds; sample, maximum, errors and exclusions reported (CAP-16, CAP-18). |
| **AC-11** | Measure eligible unknown-caller captures under the approved peak-load protocol. | 95th percentile ≤ 90 seconds with the same reporting (CAP-17, CAP-18). |
| **AC-12** | Add a registration to a log on created an hour earlier. | Same interaction cost as initial capture. |
| **AC-40** | Begin a log on and populate only Class D fields. | Unpopulated fields are listed, ranked with Class A most prominent and Class D least; nothing captured is refused; the record stays a draft because the mandatory set is short, and says which values are missing (CAP-10 to CAP-12, ACC-8). |
| **AC-41** | Begin an unclassified caller capture with no description, then receive a hull colour before an identifier. | Record retained in the owning unit's open queue; classification/description never gate creation, and the volunteered colour is retained immediately while identity remains unknown (CAP-3, CAP-14). |
| **AC-42** | Record POB as unknown, mobile number as explicitly unavailable, and an ETA of `25:70`. | The three states are distinguishable from each other and from empty; the implausible time is retained as captured with a warning, no deadline is fabricated, and WAT-9 follow-up applies (CAP-23). |
| **AC-48** | Lay a filled paper log row (A.1) beside the capture view and the queue row for the same trip. | Every trip column (1 to 12) has a field with the same heading, in the same order; return day-or-date and return time are separate fields; additional fields are visibly after the paper columns (DAT-6). |
| **AC-49** | Look for the paper's Trip ID No., Entered in Noggin and Logged off in Noggin on the capture view. | No field claims to be them; the system's own reference, entry and closure are shown as its own, and what those three paper columns record is stated (DAT-6). |
| **AC-50** | Complete every mandatory value except one, repeatedly, one value at a time. | Each save keeps a draft and names what is missing; nothing captured is refused, altered or lost; the save that completes the set logs it on (ACC-1, ACC-8). |
| **AC-51** | Save a draft with the mandatory set complete; separately, fill the last value without saving. | The save logs it on, recorded against that operator and time, with no separate accept action; filling a value without saving accepts nothing (ACC-3). |
| **AC-52** | Capture a return time that has already passed, then complete the mandatory set and save. | The log on is overdue at the moment of acceptance, without waiting for a refresh, a state change or another edit (ACC-4). |
| **AC-53** | Identify, on a new draft, a vessel that already holds an open log on at this unit. | Acceptance is refused, the open record is named and offered, and nothing captured on the draft is discarded (ACC-6). |
| **AC-54** | Discard a draft begun in error; then attempt to discard an accepted log on. | The draft is discarded with actor, time and reason, remains searchable, and counts as evidence of no vessel or person; the accepted log on refuses and must be logged off (ACC-7). |
| **AC-55** | View the queue on a screen other than the one that created a draft, with several drafts open. | Every draft is counted and visible, each with the values it is missing and its age, plainly separate from the watched log ons (WAT-1, ACC-5). |
| **AC-56** | Create records across a day boundary and read the numbers. | Each record's Trip ID No. runs on from the last across days and units, is never reused or changed, and is what every page, alert, report and export quotes (REC-9). |
| **AC-57** | Capture a member number that is a member, then one that names no member, then save. | The first ties the log on to that member record; the second leaves Member No. blank, is kept word for word in the notes, the save is not refused, and the log on reads as a public user's everywhere it is shown (CAP-24). |
| **AC-58** | Read the capture view before and after the save that completes the mandatory set. | Before: a draft, with nothing an operator could read back to the vessel as logged on; after: logged on, the moment the operator may say so (ACC-9, ACC-2). |

<a id="section-102-verification-and-search"></a>

### 10.2 Verification and search

| # | Test | Pass condition |
|---|---|---|
| **AC-13** | Independently enter exact identifiers uniquely identifying one person/vessel association. | Verified with evidence shown. Duplicate/autofilled evidence does not independently corroborate. |
| **AC-14** | Enter exact identifiers with disjoint person/vessel candidate associations. | Outcome shown as **Conflict**, prominently; shared-vessel associations alone do not produce a false conflict. |
| **AC-15** | Enter a registration one character wrong within Appendix B; select a suggested match. | Correct vessel offered with substitution marked; selection alone never becomes exact or Verified. |
| **AC-16** | Inspect any resolution result. | Includes vessel name, length, colour, type, associated member. |
| **AC-17** | Search a registration for a vessel currently logged on. | Vessel returned, marked as currently logged on. |
| **AC-18** | Search a member number, a registration, a mobile number and a vessel name in the same input. | All return results without changing search mode. |
| **AC-19** | Save a log on with a **Conflict** outcome. | Save succeeds; conflict remains visible on the record. |
| **AC-20** | View the active watch list. | Verification outcome visible per row. |
| **AC-43** | Type the first characters of a registration; apply the result for a historical trip, then for an open trip. | Results return on partial input; the historical trip supplies identity and profile detail only, never current trip facts; the open trip offers resumption, not a duplicate (SRCH-5, SRCH-6). |
| **AC-44** | Resolve an identifier with several candidates, including a set larger than one result page. | Candidates accessible in one comparison view, with match basis, freshness and visible counts; pagination has no hidden truncation and no candidate is pre-selected (IDV-8). |

<a id="section-103-watch-record-and-audit"></a>

### 10.3 Watch, record and audit

| # | Test | Pass condition |
|---|---|---|
| **AC-21** | Allow an ETA to pass. | Overdue alert raised without operator action. |
| **AC-22** | Trigger an overdue on an unverified record. | Verification state surfaced with the alert. |
| **AC-23** | Amend an ETA, then inspect history. | Both original and amended values retrievable. |
| **AC-24** | Perform a shift handover with an unresolved Draft, a pending transfer and an open escalation present. | All open records, missed obligations, pending saves/transfers and escalation history are presented and acknowledged without re-entry; outgoing and incoming operators recorded; monitoring continues throughout (WAT-6). |
| **AC-25** | Run the operational report. | Proportion of live-captured versus later-entered log ons is reported. |
| **AC-47** | Evaluate a return, report and crossing deadline just before, at and after D − W and D using the approved clock/window. Include another already-overdue obligation. | Approaching exactly when D − W ≤ T < D; Overdue at T ≥ D; missed-obligation alerts meet WAT-3 limits and remain distinguishable from approach indications; existing misses remain visible (WAT-1, WAT-2). |

<a id="section-104-adoption-and-release-acceptance"></a>

### 10.4 Adoption and release acceptance

**AC-26.** During an approved operational trial, routine double entry into a parallel paper
log ceases because the system supports the work, rather than because operators are told
to stop. Measure duplicate-entry proportion and delay against the baseline. Approved
outage/contingency records are evaluated separately.

This is an adoption outcome, not a sufficient safety test. Passing it cannot substitute
for deadline, persistence, recovery and handover acceptance. Failure requires investigation
of workflow, policy and trust rather than assuming operator resistance.

<a id="section-105-interrupted-and-exceptional-operation"></a>

### 10.5 Interrupted and exceptional operation

| # | Test | Pass condition |
|---|---|---|
| **AC-27** | Capture a return time, POB and destination but only one identifier, so the mandatory set is short. Let the return time pass. | No deadline is monitored and no overdue is raised; the record is plainly shown as a draft and not a log on; its ACC-5 follow-up fires and is labeled internal (ACC-1, ACC-2). |
| **AC-28** | Begin an empty draft; interrupt the operator until the approved follow-up deadline passes. | The draft has a named owner; internal follow-up alerts without fabricating a vessel deadline; the draft is counted and visible away from the page that created it (ACC-5, WAT-9). |
| **AC-29** | Fail a save, disconnect, close/reopen the browser, reconnect and retry. | Status never falsely claims shared persistence; recovery meets the approved envelope; no duplicate trip or silent loss/overwrite. |
| **AC-30** | Two operators amend ETA or identity from the same version; one closes the record while the other is editing. | Stale/conflicting changes require explicit resolution; both evidence histories remain; closure is not silently undone. |
| **AC-31** | Test one exact identifier, two independently supplied identifiers with one exact/unmatched, two exact but ambiguous, uniquely corroborating exact evidence, and incompatible exact evidence; include shared phones/multi-vessel members. | Respectively Unverified, Partial, Partial, Verified and Conflict; exactly one outcome per current evidence set; candidate detail and raw inputs retained (IDV-2). |
| **AC-32** | Request transfer, pass ETA before acceptance, retry after disconnect, then accept after an intervening edit. | Source remains responsible until current-state acceptance; alert is delivered without a gap; one ownership change; stale state cannot silently be accepted. |
| **AC-33** | Miss a position report on a long-term trip with a later return ETA; complete a nested bar crossing. | Missed report remains visible/alerted; crossing completion does not fulfill report or return obligations. |
| **AC-34** | Change ETA on an escalated trip and acknowledge its alert. | Old miss and actions remain; escalation closes only through explicit authorized disposition. |
| **AC-35** | Close all browsers and pass a deadline; restart monitoring with already-missed obligations; leave an alert unacknowledged. | Detection, delivery, health failure and repeat behavior meet approved limits; acknowledgment does not log off a vessel. |
| **AC-36** | Log off, cancel a duplicate, and correct a mistaken closure with appropriate roles. | Reasons/evidence retained; obligations/escalations receive explicit disposition; reopen evaluates missed deadlines; unauthorized actions refused. |
| **AC-37** | Expire a session, attempt cross-unit/private search/export without permission, and submit through self-service. | Capture recovery and shared monitoring persist; access boundaries enforced; submission does not falsely acknowledge watch acceptance. |
| **AC-38** | Restore a backup and reconcile outage records in isolation. | REC-8 recovery limits met; audit and ownership preserved; pending/missed obligations recovered without duplicate actions. |
| **AC-39** | Change a vessel/person profile after a completed call. | Historical identifiers, applied details and verification evidence remain as known at the call; current profile changes are distinguishable. |
| **AC-45** | Leave a draft whose only missing value is the second identifier, well past its ACC-5 follow-up deadline. | The owning duty role is followed up on time, without implying a vessel-return failure; supplying the identifier and accepting resolves that follow-up and starts the watch, and does not resolve unrelated follow-ups (ACC-5, WAT-9). |
| **AC-46** | Amend an effective ETA with blank, `25:70`, or ambiguous text; let the original deadline pass. Then explicitly withdraw it without a replacement while escalation is open. | Raw proposal and warning saved; original deadline still monitored/alerted until explicit withdrawal; withdrawal reason/history retained, no-usable-deadline follow-up starts, and escalation remains open (CAP-23, WAT-9, WAT-10). |

<a id="section-106-operational-release-gate"></a>

### 10.6 Operational release gate

Before operational reliance, the unit shall approve the unresolved policy/configuration
items in Appendix D that affect this deployment, and record a traceability checklist for
all applicable requirements. In particular, define measurable alert latency, clock error,
follow-up intervals, escalation/transfer authority, recovery limits and trial metrics.
These values are not invented by this functional specification.

All applicable acceptance criteria shall pass on the intended deployment, including its
existing-watch integration if P2 functions are retained elsewhere. Simulation and isolated
failure/recovery tests precede a supervised live trial with continuity of the established
watch. Unsupported variants/channels shall be explicitly declared and excluded from the
initial rollout; they shall not appear available without their monitoring behavior.

---

<a id="section-appendix-a-justification-from-current-practice"></a>

## Appendix A — Justification from current practice

Evidence that the requirements above address real conditions rather than hypothetical
ones. Recorded from a unit operating a commercial resilience-management platform
alongside a handwritten radio log.

**A.1 The paper radio log is the working record.** Figure 5 is the unit's blank *Limited
Coast Station Radio Log*, a spiral-bound pad kept on the radio desk. It is the first thing
filled out for every call (OC-9). Its columns, verbatim and in order:

| # | Column heading | Notes |
|---|---|---|
| 1 | Date __/__ | date of the call |
| 2 | Time 00:00 | time of the call, 24-hour |
| 3 | Member No. OR Vessel Name | **shaded: mandatory** |
| 4 | Vessel Rego. No. | **shaded: mandatory** |
| 5 | Mobile Phone Number | **shaded: mandatory** |
| 6 | Vessel Details | free text |
| 7 | POB | persons on board |
| 8 | Departure Point | free text |
| 9 | Going to | free text |
| 10 | ETA/ETR — Return Day or Date | one column of a two-column group |
| 11 | ETA/ETR — Time 00:00 | the other |
| 12 | Time Arrived or Return | the log off time |
| 13 | Trip ID No. | pre-printed "T-"; the computer system's trip number is written in after transcription |
| 14 | Entered in Noggin ✓ | ticked when transcribed into the computer system (Noggin is the platform currently in use) |
| 15 | Logged off in Noggin — Initial | operator initials when the log off is transcribed |

Three things follow. First, columns 13 to 15 are decisive, and they are of a different kind
from the twelve before them: those twelve record the trip, these three record **the transcription
of the row into a separate computer system**. **The paper log tracks the computer system as an
outstanding task.** The operational record is paper; the computer
record is a downstream transcription, cross-referenced by the trip number written back onto
the paper row. The computer record therefore lags the operational one; its legal status
remains subject to confirmation under OC-7. AC-26 exists to detect when this has been
reversed.

Second, a paper row is a record from the first pen stroke, with any subset of cells filled,
completed across the call in whatever order the caller gives the information. That is
CAP-1, CAP-2 and CAP-3 as the unit already practises them.

Third, the form's three mandatory columns are exactly the Class B identifiers (§6.1). On
paper, *mandatory* means "obtain this before the call ends", and the row exists and is
watched regardless. The existing computer system reads the same word as "required before
the record can be saved" (A.3). The difference between those two readings is most of this
specification.

**A.2 All-or-nothing saving produces the backlog.** The current system cannot persist an
incomplete log on. An operator who has captured half the detail has nothing to save, so
the entry stays on paper until there is time to complete it — and the backlog grows
fastest precisely under peak load (OC-8), when it is least affordable. CAP-1 and CAP-2
address this directly.

The draft is the answer to it, and the draft is why this specification needs §5.3. Allowing a
half-finished record to be saved removes the reason to keep it on paper, but it creates a
record that looks like a log on and is not one. The unit's decision is that such a record is
not watched (ACC-2), which means the draft solves the backlog and hands back a new problem:
an unfinished call nobody is counting down. ACC-5 is that problem's only answer.

**A.3 Mandatory fields are the fields that arrive last.** Registration and mobile number
are required before a record can be saved, and are the two fields that typically arrive
last in a call or on a later call (OC-6). The form demands first what the conversation
surrenders last. The paper log marks the same fields mandatory and yet accepts the row
without them (A.1); the software does not. CAP-2, CAP-13 and CAP-14 address this.

**A.4 Default values that fail validation.** The observed new-log-on form pre-populates
departure time and ETA with the same value, then rejects the record on the grounds that
the ETA must be later than the departure. The form's initial state fails its own
validation: the operator must correct the time relationship before that validation can
pass. The screenshots do not establish that both time fields must be edited; changing the
ETA alone could resolve the shown time errors if it is later than departure and current
time. Other displayed validation errors still require resolution. The
screenshots show this rejection only on the new-log-on path. Whether other paths (amendment,
import, self-service) accept the paired defaults, and how the overdue engine would then treat
a zero-duration trip, is not established by the screenshots and requires a runtime check.
CAP-4 and CAP-5 address this.

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
number. The paper log institutionalises this: its three shaded mandatory columns are member
number or vessel name, registration and mobile (A.1). Agreement provides corroboration; disagreement signals a possible error. This is
not a guarantee of identity, and shared, stale or correlated identifiers require the
ambiguity rules in §7. The practice is undocumented and unsupported by
software, and is performed by eye across the partitioned searches described in A.7.
IDV-1 to IDV-5 formalise it.

**A.9 Phonetic discipline is not reliable under load.** Requesting a phonetic repeat costs
a transmission on a contended channel. Local observations report that repeats are sometimes omitted under load.
IDV-6 supports recovery from plausible mishearing; it does not justify abandoning approved
radio procedures or necessary clarification.

**A.10 The existing platform's mandatory set, and its own disagreement about it.** Figures 2
and 3 are its new log on form. Its first tab is headed *Vessel Log On details (mandatory)*, and
these fields carry its asterisk:

| Section | Marked mandatory |
|---|---|
| Log on details | Radio channel · known vessel or existing member · Vessel |
| Trip details | Number of persons on board · Departure date and time · Estimated date and time of arrival/return · Returning to the same location as departure |

Four observations follow.

**The asterisks and the validation disagree.** *Departure point* and *Going to* carry no
asterisk, and the validation block in Figure 2 nonetheless rejects the save with "Departure
point should be entered" and "Going to field should be entered". The form states one minimum and
enforces a larger one, which is most of why the error block is a surprise at the point of save
(A.5). ACC-1 therefore states the mandatory set once, plainly, as a rule rather than as a
scattering of marks, and ACC-8 requires the missing values to be named before the save is tried.

**The observed mandatory set is close to the paper row.** Identity, persons on board, departure
point, destination and a return time, which is the paper log's trip columns (A.1). This is the
evidence for ACC-1, and for reading the paper's shaded identity columns the way the paper reads
them: a couple of them, not all.

**Departure point is a picker**, labelled "list of popular locations", not a free text field.
Callers name places that are in local usage and in no list, which CAP-9 requires be accepted.

**Its Vessel field is already one search input**, covering public user name, phone, membership
ID, vessel registration and vessel name. So the platform can match on any identifier within
that one field. What it cannot do is search across record types, which is the actual failure in
A.7; SRCH-1 is about the partition, not about typing a registration.

---

<a id="section-appendix-b-letter-confusion-set"></a>

## Appendix B — Letter confusion set

The following initial groups reflect reported confusion patterns, not validated error
probabilities. IDV-6 shall use them to suggest candidates, subject to field-specific
identifier formats and namespaces. They shall never establish an exact match.

| Group | Members |
|---|---|
| Rhyming ("E-set") | B · C · D · E · G · P · T · V · Z · 3 |
| Nasal | M · N |
| Sibilant | F · S · X · 6 |
| Long-A | A · J · K · 8 |
| Letter/digit collision | 0 ↔ O · 1 ↔ I ↔ L · 5 ↔ S · 2 ↔ Z |

Digits shown in the table participate in those candidate substitutions. Other digit
errors remain possible and shall be preserved for clarification rather than presumed
reliable. Evaluate candidate recall and false suggestions against representative calls;
clarify local pronunciations (including Z) and identifier formats before tuning rankings.

---

<a id="section-appendix-c-traceability-from-version-03"></a>

## Appendix C — Traceability from version 0.3

Identifiers introduced in version 0.4 are retained unchanged in later revisions. Later
revisions add identifiers; they do not renumber.

| 0.3 | 0.4 and later |
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

<a id="section-appendix-d-open-questions"></a>

## Appendix D — Open questions

1. On a **Conflict** outcome (IDV-2), what clarification does the operator perform today?
   Validate the IDV-3 workflow against that practice and define acceptable evidence for
   correction or an explicitly unresolved/provisional association.
2. Is a logged-on vessel excluded from vessel search by query construction or by data
   model? Determines the difficulty of SRCH-3.
3. What is the typical transcription backlog — count of entries, and elapsed time from
   call to computer entry? Establishes the baseline for REC-5 and AC-26.
4. Which identifier pair is most commonly used: member number with registration, or
   registration with mobile number? Determines what IDV-2 optimises for.
5. What legal, policy or contractual instrument underlies the reported computer-record
   obligation (OC-7)? Identify the authority, permitted record media, retention period and
   integrity obligations under REC-1; do not presume a legislative basis.
6. For long term log ons (§3.4), what reporting schedule is expected, and what constitutes
   a missed report?
7. Which approved procedures govern escalation, early escalation, alert acknowledgment,
   closure/reopening and handover? Who may authorize deviations and which version applies?
8. Which duty role at the owning unit receives pending-acceptance, missing-deadline and
   unresolved-amendment follow-ups? What intervals, recipients and unacknowledged-alert
   behavior apply, including when an ETA is present but no operator has accepted?
9. What detection/delivery latency, approaching window, clock-error bounds, monitoring-health notification,
   recovery-time and data-loss limits can the intended deployment demonstrate?
10. How do source and receiving units accept transfers, including after hours, refusal,
    connectivity loss and changes while acceptance is pending?
11. What identifier namespaces, shared-number patterns, stale records and person/vessel
    associations occur? What clarification evidence may supersede a conflicting raw value?
12. What sampling protocol establishes live-call timing and transcription delay? Define
    peak load, sample size, start/end, complete capture, interruptions and privacy handling.
13. Which channels and variants are included at initial release? What existing watch
    integration remains authoritative, and how will its acknowledgment/failure be shown?
14. What access, retention, disposal, export and contingency-record policies apply?
    Identify the document/authority and approver for each release-affecting answer.
15. Does the paper radio log (A.1) remain the primary record after a replacement system is
    trusted, become the contingency record, or be retired? Who decides, and what does the
    system need to show before that decision (AC-26)?
16. **Is the mandatory set in ACC-1 the unit's set?** In particular: are two identifiers enough,
    and which two; does departure time belong in it, as the existing platform requires and the
    paper log does not; does the monitored radio channel belong in it, as the existing platform
    requires; and is "returning to the same location" wanted at all.
17. **What follow-up does an unaccepted draft get** (ACC-5)? Interval, duty role, recipient,
    reminder, escalation, and what happens at shift end. This is the answer on which the safety
    of ACC-2 rests, so it is the single most important unresolved item in this document.
18. Who may accept a log on, and what exactly is said to the vessel at that moment (ACC-3)?
    Is the acknowledgment scripted, and is it recorded?
19. When an operator discards a draft (ACC-7), what reasons are permitted, who may do it, and
    is any authority needed beyond being on watch?
20. How is ACC-6 applied across units? A vessel logged on at one unit and calling another is
    not a duplicate within a unit; whether it is permitted at all, and how it is reconciled,
    depends on the transfer answers (question 10).
21. *Withdrawn in version 1.1:* there is no daily number; REC-9 uses the Trip ID No.

---

<a id="section-appendix-e-revision-history"></a>

## Appendix E — Revision history

<a id="section-version-11-changes-from-10"></a>

### Version 1.1 — changes from 1.0

- **A Member No. is a member record** (CAP-24, 14 September 2026). The unit keeps member records
  (member number issued by the system, contact details, emergency contacts, vessels, trailers, cars)
  and public vessels, the standing record for a public user. A log on's Member No. is selected from the
  members; a number heard that names no member is left out of Member No. and kept in the notes, and the
  log on is a public user's. This narrows CAP-23 and DAT-5 for that one value. The glossary, §3.1, §3.2,
  ACC-1 and AC-57 follow.
- **The vessel is told it is on the log only when the computer log has it** (ACC-9). A paper row or a
  draft is not a log on (OC-9). AC-58 follows. This bears on Appendix D question 15: a call written on
  paper and entered later is not a log on until it is entered.
- **Saving a complete draft logs it on** (§5.3 ACC-3). Version 1.0 required a separate, explicit accept
  action after the mandatory set was complete. The unit's position: the required details are filled
  because the vessel is logging on, so the save that completes them is the acceptance. The save is
  recorded against the operator and time; ACC-1, ACC-4 and ACC-6 are unchanged. §1.2, the glossary,
  §3.3 and its actions table, the ideal call, AC-50, AC-51 and AC-52 follow.
- The logged-on state is named **Logged on** (stored `loggedOn`, logged off `loggedOff`), replacing
  Watching (`watching`, `loggedoff`). Existing records are converted.
- ACC-1 states that a save on a log on cannot empty or make unreadable its mandatory set (it was
  implied by §3.3 and WAT-10, and the implementation had allowed it).
- **A record's number is its Trip ID No.** (REC-9, 14 September 2026). Version 0.9 added a number
  counting from one each day; the unit's position is that it duplicated the Trip ID No. column the paper
  log already has. REC-9 and AC-56 now name the Trip ID No.; Appendix D question 21 is withdrawn.

<a id="section-version-10-changes-from-09"></a>

### Version 1.0 — changes from 0.9

This version reverses the central decision of version 0.5. It is a unit decision, recorded as
such, and the reasoning and the cost are in §1.2 rather than buried here.

- **Nothing is watched until the log on is accepted** (§5.3 ACC-2). Versions 0.5 to 0.9 held
  that capture completeness must never gate monitoring, so that a draft carrying a return time
  was counted down. The unit's position is that a log on is a log on once the required details
  are there, and that a half-finished record is saved paperwork rather than a watch. Accepted.
- **Section 5.3 is new**: the mandatory set (ACC-1), the gate (ACC-2), acceptance as one
  explicit operator action and as what is said to the vessel (ACC-3), immediate evaluation on
  acceptance so a late entry is overdue at once (ACC-4), the draft chase (ACC-5), one open log
  on per vessel (ACC-6), discarding a draft that was never a log on (ACC-7), and naming what is
  missing without refusing anything (ACC-8).
- **The mandatory set is stated from evidence**, not asserted: the existing platform's observed
  requirements plus its own validation, transcribed in the new A.10, read against the paper
  row in A.1. Two of the four identity values rather than all four, because that is how the
  paper's shaded block reads and it is the two-identifier check operators already perform.
- **The cost is stated.** ACC-2 creates a failure mode the earlier versions did not have: an
  unfinished call, forgotten, while the vessel believes it is logged on. ACC-5 and WAT-9 are
  that mode's only mitigation, and WAT-9 now says plainly that a draft's follow-up is a safety
  function held to the same standard as WAT-3. A deployment that gates the watch without
  building the chase is less safe than one that does neither.
- **The states collapse to three**: draft, watching, logged off. Pending acceptance is gone,
  because acceptance is now the transition out of draft rather than a state beside it. The
  separate cancellation of an accepted log on is gone too: a log on that happened is logged off,
  with the reason recorded, and only a draft can be discarded (§3.3, ACC-7).
- **§3.5 is new**: the ideal call in a paragraph, and a table of the twenty situations that are
  not ideal, which is where every requirement in the document comes from.
- **REC-9 is new**: a number counting from one each day, because operators say "log on fifty
  yesterday" and not a database key.
- Revised for the gate: CAP-12 (prompting is advisory and is not the gate), DAT-1 (Class A gates
  nothing, though most of it is in the mandatory set), WAT-1 (drafts shown beside the queue and
  never in it), WAT-3 (scoped to accepted log ons), WAT-9 (the draft chase). AC-27, AC-28 and
  AC-45 inverted; AC-50 to AC-56 added. Appendix D gains questions 16 to 21, of which 17 is the
  one this version's safety depends on.

<a id="section-version-09-changes-from-08"></a>

### Version 0.9 — changes from 0.8

- Split A.1's fifteen columns into the twelve that record the trip and the three that record
  transcription into a separate computer system. DAT-6 now requires only the first twelve and
  forbids reproducing the other three, because a system cannot honestly answer them about
  itself; answering them with its own record number and timestamps makes three cells mean
  something other than their headings say. Added AC-49.
- The prototype built against v0.8 had done exactly that, which is how the distinction surfaced.

<a id="section-version-08-changes-from-07"></a>

### Version 0.8 — changes from 0.7

- Added Figure 5, the unit's blank paper radio log, and rewrote A.1 from it. The previous
  transcription was wrong: the log has member number *or vessel name*, registration and
  mobile as three shaded mandatory columns, a Vessel Details column, ETA/ETR as return
  day-or-date plus time, a Time Arrived column, a pre-printed trip number, and separate
  entered and logged-off columns for the computer system.
- Stated the paper log as the primary record and the first thing filled out (OC-9), and
  required the capture view and queue to carry its columns under its headings in its
  order (DAT-6, AC-48), with return day-or-date as its own field.
- Mapped the paper columns to the §6.1 classes; noted that Class C is not on paper.
- Recorded that "mandatory" on paper means obtained before the call ends, while the
  existing system reads it as required before saving (A.1, A.3), and that the paper log
  institutionalises the two-identifier practice (A.8).
- Added Appendix D question 15 on the paper log's future.

<a id="section-version-07-changes-from-06"></a>

### Version 0.7 — changes from 0.6

- Accepted the v0.6 direction: ownership clarity, approaching-state configuration, stable
  IDs and AC-40–44 coverage are retained. This is acceptance of specification changes,
  not approval of operational readiness; Appendix D decisions remain open.
- Made IDV-2 outcomes mutually exclusive with an explicit decision order and strengthened
  AC-31. A lone exact identifier stays Unverified while its useful candidate remains visible.
- Aligned AC-41 with free-order capture; volunteered description may arrive before identity.
  DAT-3 now permits necessary clarification of stale/conflicting stored descriptions.
  AC-44 preserves the permitted pagination rule. CAP-10 no longer calls its gap list a procedure.
- Extended WAT-9 to pending acceptance even with a usable ETA, and unresolved amendments.
  Internal follow-up misses are distinguishable from missed vessel obligations (AC-45).
- Kept an effective deadline monitored while an unresolved replacement is saved; explicit
  withdrawal retains history and starts follow-up without closing escalation (AC-46).
- Defined approaching/overdue boundary instants and added AC-47 for all vessel obligation
  kinds. Corrected A.4: the screenshots do not prove both time fields must be edited.
- Updated the index and regenerated the linked PDF with the existing four evidence figures.

<a id="section-version-06-changes-from-05"></a>

### Version 0.6 — changes from 0.5

- Clarified that unit ownership begins at creation and that Pending acceptance records the
  absence of an accepting operator, not the absence of an owner (§3.3).
- Defined the open watch queue and the Approaching condition. The approaching window is an
  approved configuration value and is distinct from a WAT-3 alert (§2, WAT-2, Appendix D).
- Corrected A.4, which asserted both that the form rejects its own defaults and that they
  could be saved unnoticed. The runtime question is now stated as open.
- Added AC-40 to AC-44 for ranked advisory gap prompting, unclassified public callers,
  distinguishable unknown/unavailable/implausible values, partial-input search with
  apply/resume, and multi-candidate comparison; these requirements previously had no
  acceptance criterion. Strengthened AC-24 to match WAT-6.
- Recorded that no requirement carries P3 and that identifiers are stable across revisions
  (§1.4, §10, Appendix C).
- Editorial: person name added to the Identifier definition; SRCH-1 refers to open and
  historical log ons rather than active and draft; Appendix D numbering and Appendix A
  wrapping repaired.

<a id="section-version-05-changes-from-04"></a>

### Version 0.5 — changes from 0.4

- Separated capture completeness, watch acceptance/ownership, deadline condition and
  escalation. Drafts with usable deadlines are monitored; unresolved records get internal
  follow-up. Transfers retain ownership until explicit current-state acceptance.
- Represented return, position-report and crossing deadlines as independent obligations.
- Added persistence acknowledgment, recovery, retry, concurrent-edit and duplicate handling.
- Distinguished system metadata, supplied facts and reused profile data; preserved time
  expressions, interpretation basis, call time and entry time.
- Defined independent evidence, ambiguous associations, conflict precedence and approximate
  candidates. Verified no longer implies caller authentication or confirmed trip facts.
- Added approved alert/escalation configuration, access control and demonstrated recovery.
- Corrected the unsupported equal-time/never-overdue claim and qualified unverified legal,
  procedural and phonetic assertions. Adoption is now separate from safety acceptance.
- Retained requirement IDs, revised their wording where necessary, and added CAP-19–23,
  IDV-9, WAT-9–10, REC-6–8 and AC-27–39. CAP-16/17 targets are interpreted by revised CAP-18.
- Added a linked table of contents and included the existing evidence figures in the
  formatted specification. The figures contain operational/contact data; sharing beyond
  the authorized audience requires an appropriately redacted copy.

<a id="section-appendix-f-evidence-figures"></a>

## Appendix F — Evidence figures

Figures 1 to 4 are supplied screenshots of the existing platform, not proposed interface
designs. Figure 5 is the paper radio log itself.
Static images evidence visible layout/defaults; search exclusions, persistence behavior,
and overdue behavior require observations or runtime checks beyond a screenshot.

<a id="section-figure-1-active-log-on-list"></a>

### Figure 1 — Active log on list

![Current platform: active log on list and navigation](figures/figure-1-active-log-on-list.png)

Supports the visible dashboard/navigation observations in A.6–A.7. Does not independently
prove that an active vessel is excluded from a search query.

<a id="section-figure-2-validation-error-block"></a>

### Figure 2 — Validation error block

![Current platform: validation messages separated from fields](figures/figure-2-validation-error-block.png)

Supports A.3–A.5: required controls and errors remote from affected fields.

<a id="section-figure-3-capture-form-scrolled"></a>

### Figure 3 — Capture form scrolled

![Current platform: scrolled capture form and trip details](figures/figure-3-capture-form-scrolled.png)

Supports A.4 and A.6: trip fields/defaults and capture occupying the screen.

<a id="section-figure-4-trip-detail-defaults"></a>

### Figure 4 — Trip-detail defaults

![Current platform: departure and return fields with identical defaults](figures/figure-4-trip-details-defaults.png)

Supports A.4: identical displayed departure/return values. No claim about the actual
runtime overdue calculation can be established from this image alone.

<a id="section-figure-5-paper-radio-log"></a>

### Figure 5 — Paper radio log

![The unit's blank Limited Coast Station Radio Log](figures/figure-5-paper-radio-log-blank-form.jpeg)

The primary record (OC-9), transcribed column by column in A.1. Shading marks the three
mandatory columns; the last three columns track transcription into the computer system.
