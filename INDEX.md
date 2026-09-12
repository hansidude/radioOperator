# Vessel Log On — Functional Specification, v0.5

## Table of contents

- [Files](#files)
- [Figures](#figures)
- [Reading order](#reading-order)
- [Revision 0.5](#revision-05)
- [Updating the documents](#updating-the-documents)

## Files

| File | Description |
|---|---|
| `vessel-logon-spec.pdf` | The specification, formatted, with linked contents and all four evidence figures. |
| `vessel-logon-spec.md` | The same document in Markdown source. |
| `figures/` | Screen captures of the current system, evidencing Appendix A. |

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

## Reading order

1. §1 — purpose and the primary safety objective.
2. §3 — domain model, independent capture/watch states, ownership and obligations.
3. §5–§7 — capture, data and verification requirements. This is the current focus.
4. §10 — acceptance criteria.
5. Appendix A with the figures alongside, for why the requirements are as they are.

## Revision 0.5

Capture completeness no longer gates deadline monitoring. The specification now defines
unresolved-draft follow-up, acknowledged transfer, independently tracked deadlines,
verification ambiguity, durable save/recovery behavior, and failure/concurrency acceptance
criteria. Reported legal obligations and operational thresholds remain explicitly subject
to confirmation. Appendix E records the changes; Appendix D lists operational decisions.

## Updating the documents

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
