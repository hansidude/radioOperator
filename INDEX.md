# Vessel Log On — Functional Specification, v0.4

## Contents

| File | Description |
|---|---|
| `vessel-logon-spec.pdf` | The specification, formatted. 7 pages. |
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
| `figure-4-trip-details-defaults.png` | Trip Details with departure time and estimated return time pre-populated to the identical value. | **A.4** (paired defaults that fail the form's own validation, and that would produce a record incapable of becoming overdue if saved) |

## Reading order

1. §1 — purpose and the primary safety objective.
2. §3 — domain model and state machine.
3. §5–§7 — capture, data and verification requirements. This is the current focus.
4. §10 — acceptance criteria.
5. Appendix A with the figures alongside, for why the requirements are as they are.
