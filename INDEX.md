# Vessel Log On — Functional Specification, v1.0

## Table of contents

- [Files](#files)
- [Figures](#figures)
- [Reading order](#reading-order)
- [Revision 1.0](#revision-10)
- [Updating the documents](#updating-the-documents)

## Files

| File | Description |
|---|---|
| `vessel-logon-spec.pdf` | The specification, formatted, with linked contents and all five evidence figures. |
| `vessel-logon-spec.md` | The same document in Markdown source. |
| `figures/` | Screen captures of the current system and the paper radio log, evidencing Appendix A. |

## Figures

Screen captures taken from the resilience-management platform currently in use at the
unit. Each supports one or more observations in **Appendix A — Justification from current
practice**.

| Figure | Shows | Evidences |
|---|---|---|
| `figure-1-active-log-on-list.png` | Unit dashboard: active and overdue counts, active log on list, separate navigation entries for vessel search, member search and logged-on vessels. | **A.6** (capture occludes this list), **A.7** (search is partitioned across separate destinations) |
| `figure-2-validation-error-block.png` | New log on form. Four validation errors presented as a block at the top of the form, referring to fields in other sections and tabs. | **A.3** (mandatory fields), **A.4** (initial state fails validation), **A.5** (errors remote from their fields) |
| `figure-3-capture-form-scrolled.png` | Same form scrolled: "Known Public User" and "Trip Details" sections, each field a picker control. Full-screen modal with Cancel/Save. | **A.4**, **A.6** (modal conceals the active list) |
| `figure-4-trip-details-defaults.png` | Trip Details with departure time and estimated return time pre-populated to the identical value. | **A.4** (identical departure/return defaults and associated validation errors; runtime overdue behavior is not established by the screenshot) |
| `figure-5-paper-radio-log-blank-form.jpeg` | The unit's blank Limited Coast Station Radio Log: 15 columns, three shaded mandatory, trip number and transcription columns at the right. The primary record. | **OC-9**, **A.1** (columns transcribed verbatim), **A.3**, **A.8**, **DAT-6** |

## Reading order

1. §1 — purpose and the primary safety objective.
2. §3 — domain model, independent capture/watch states, ownership and obligations.
3. §5–§7 — capture, data and verification requirements. This is the current focus.
4. §10 — acceptance criteria.
5. Appendix A with the figures alongside, for why the requirements are as they are.

## Revision 1.0

Reverses the central decision of revision 0.5: **nothing is watched until the log on is
accepted**. New §5.3 defines the mandatory set that gates acceptance, taken from the existing
platform's observed requirements (new A.10) read against the paper row, and requires two of the
four identity values rather than all four. Acceptance is what the unit tells the vessel; since
v1.1 it is the save that completes the mandatory set, with no separate accept action. States collapse to draft, watching, logged off; a draft can be discarded,
an accepted log on can only be logged off; one vessel has one open log on. The cost of gating
the watch is stated in §1.2: an unfinished call nobody is counting down, whose only mitigation
is the draft follow-up in ACC-5 and WAT-9. New §3.5 sets out the ideal call and the twenty
situations that are not ideal. New REC-9 numbers records from one each day. Since v1.1 a log on's Member No. is a
member record, a number heard that names no member is kept in the notes and the log on is a public
user's (CAP-24), and the vessel is told it is on the log only once the computer log has it (ACC-9).

## Updating the documents

This section is specification publishing only. For app development and testing,
follow the host Quackit's `DEVELOPMENT.md`; never use the rendering venv as a test
environment or as evidence that Quackit integration passed.

Keep a linked table of contents at the start of the Markdown and PDF. Update the Markdown
source, then regenerate the PDF and verify that contents links, tables and all figures render.
The renderer refreshes explicit heading anchors and the Markdown contents automatically.

```sh
python3 -m venv .venv-render
.venv-render/bin/pip install -r tools/requirements-render.txt
.venv-render/bin/python -m playwright install chromium
.venv-render/bin/python tools/render_spec.py
```

`tools/render_spec.py` embeds local images, adds page numbers, and checks contents targets
and image loading. It needs no running application. Python dependencies and a Chromium
installation are needed for rendering; after installation, the document uses local assets.
Commit the Markdown, regenerated PDF and index together. The supplied figures contain
operational/contact details; the PDF is for the same authorized audience as the source images.
