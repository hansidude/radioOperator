# House Rules — working on my codebase

## Authoritative workflow (2026-09-13)

Read the host Quackit's `DRY-CATALOG.md` and follow `DEVELOPMENT.md`; in the mounted
checkout these are `../DRY-CATALOG.md` and `../DEVELOPMENT.md`. Radio development
happens in Quackit's `radio/` submodule. These documents own the environment,
verification and rollout procedure; do not maintain alternatives here.
User authorisation covers routine steps within the requested task; the plan/approval
rules below do not require repeated permission for that same work.

Follow every rule below. At the end of each task, paste the **End-of-task report**
(bottom of this file) filled in, so every rule is provably addressed — not just promised.

The core problem these fix: jumping to a solution and inventing a new thing, instead of
finding what already exists, making the smallest change, and confirming before building.

---

## 0. STOP — check the LAST LINE before you send (read this every message)

The single most-broken rule is the closing line. There is a reflex to tack a friendly
"…just say go when you want X" / "want me to do Y?" onto the end of a message. That is a
**question buried in prose**, which violates rule 7. Before sending, look at your final line:

- If it asks for, or invites, any input/decision → it MUST be a **numbered list**.
- Otherwise it must be a plain **statement** (or a numbered list of options).
- **Never** end on a trailing offer, "let me know", or a prose question. Ever.
- On a task turn, the **End-of-task report is the last thing** — nothing comes after it.

If you catch yourself writing a closing pleasantry, delete it or convert it to a numbered list.

---

## 1. Recon before proposing
- Before suggesting *any* solution, locate the existing macro, route, template, or pattern
  that already does this job (or the closest one), and quote the actual lines back with
  **file + line numbers**.
- Check whether the existing thing already supports the request via a flag, mode, or param.
- If past work is referenced, search past chats **first** and report what was found.
- **Violation =** proposing or writing code before showing the existing thing.
- **Report:** "Existing thing found: `<file:lines>` — `<what it is>`. Already covers this? `<yes/no + why>`."

## 2. Extend, don't invent
- Default action is to **modify the existing thing**. A new file / macro / table / endpoint /
  CSS-class system is the **last** resort.
- Build new only after showing, concretely, why the existing one can't be extended — **and**
  getting an explicit "go".
- No parallel systems that do nearly the same job as something that already exists.
- **Violation =** any new artifact created without explicit sign-off.
- **Report:** "Change type: [extended existing `<X>`] or [new `<Y>` — approved at `<point>` because `<reason>`]."

## 3. Plan in two lines, then wait
- State the change as: "I'll change `<X>` in `<file>` so it `<does Z>`." Max two lines. Then **stop
  and wait** for "go".
- Do not start editing in the same message as the plan unless "go" was already given for that
  exact change.
- **Violation =** building before the specific change was greenlit.
- **Report:** "Plan stated at `<point>`; approved at `<point>`."

## 4. No scope creep
- The change stays the size of the problem. A three-line fix is a three-line fix.
- Do not bundle migrations, refactors, or "while I'm here" cleanups. A bigger refactor is named
  as a **separate** item to decide on later — never inside the current task.
- **Violation =** touching files or systems the task didn't require.
- **Report:** "Files touched: `<list>`. Each required because `<reason>`. No extra scope added."

## 5. Verify before "done"
- Before handing anything over, check the output against whatever it's meant to match — by
  rendering, diffing, or running it — and state how it was verified.
- Verification must cover the **real runtime path**, not just isolated logic. If you can only
  test a piece in isolation, say so plainly and hand me the exact one-step check to run.
- Never declare "done" and rely on the user to catch the gap.
- **Violation =** "done" with no verification, or the user finding a defect that was catchable.
- **Report:** "Verified by `<method>`. Result matched reference: `<evidence>`. Couldn't verify: `<what + how I told you to check>`."

## 6. Search history on reference
- Any time prior work, decisions, or "the thing we built" is referenced, search before acting,
  and report what was found (or that nothing was found).
- **Report:** "History searched: `<query>` → `<found / not found + what>`."

## 7. Numbered lists when input is needed
- Every time a decision, answer, or input is needed from the user, present it as a **numbered
  list**. No questions buried in prose. This includes the **closing line** — see rule 0.
- **Report:** n/a (format rule, visible in every message).

## 8. DRY approach — do not repeat code
- If we repeat something, the question **must** be asked: should this move into one place
  everyone can access? One source of truth, everyone consumes it.
- **Violation =** adding/leaving a second copy of logic that already exists somewhere.
- **Report:** "Duplication check: `<none / found <what>; consolidated into <where> or named as separate task>`."

## 9. No silent fallbacks
- Let it fail super noisily. A `try/except` that swaps in a "safe" default, or a fetch that
  returns `[]` on error, turns a loud, findable bug into a silent wrong answer.
- Get it right or fail visibly (throw, log, show an error in the UI). Wrong data is worse than no data.
- **Report:** "Fallbacks: `<none / removed <what> / kept <what> because it's a legit empty state>`."

## 10. Count how many times you've failed at this task
- Keep a running count of failed attempts on the current task. If you've failed **twice**, stop
  editing. State the count, state **why** each attempt failed (the real root cause), and
  **propose** what's different about the next attempt before you make it.
- **Report:** "Attempts this task: `<n>`. Root cause of failures: `<cause>`. What changed: `<fix>`."

## 11. Pin the reference before you touch anything
- Before editing, state exactly what the output must **match** — as "done = identical to `<X>`".
- If a thing already matches the reference, **do not touch it.**
- When I correct you on what "correct" means, treat that as the new reference immediately.
- **Report:** "Reference: `<X>`. Acceptance = `<what identical means>`. Left unchanged because already-correct: `<what>`."

## 12. Use what I already gave you
- Search the **entire** tree — recursively — before asking for a file or claiming something is missing.
- **Report:** "Looked for `<thing>` across uploads: `<found at file:line / genuinely absent after recursive search>`."

## 13. Changed how a shared thing loads or behaves? Audit every caller.
- When you change a shared function's contract or timing, `grep` **every** call site and verify
  each one still holds under the new contract before saying done.
- **Report:** "Contract changed: `<what>`. Callers grepped + audited: `<list>`. Each OK because `<reason>`."

---

## Project conventions (vessel log on)

- The reference is `vessel-logon-spec.md`. Cite the requirement id (CAP-n, WAT-n, ...) in a comment
  wherever code exists because of it; if the spec and the code disagree, say so, do not quietly pick one.
- Same shape as garageSim: `server/` is the app and quackit mounts it (`dflask/radio_host.py`).
  **Data:** never tie into quackit's own tables or session directly; the user, unit and connection
  come through `Host` (`server/host.py`), and radio's tables are its own (`schemaInput_Radio.sql`).
- **UI: DRY is king.** Before building any UI, check `quackit/DRY-CATALOG.md` and use quackit's shared
  macros, CSS and JS. No radio-only one-offs: a generic piece radio needs (list, filter, status symbol,
  column picker, table/card view) is built on quackit, added to the catalog, and consumed here.
- Must run on quackit's container: Python 3.9, Flask 1.1.2, Jinja2 2.11. No `match`, no `X | Y` types.
- Never invent a trip fact (CAP-4); keep what was heard even when it cannot be read (CAP-23); times
  are read against the call time and say how (REC-6).
- Verify using the single entry point documented in Quackit's `DEVELOPMENT.md`.

---

## End-of-task report (paste this filled in, every task)

1. **Recon:** …
2. **Extend vs invent:** …
3. **Plan + approval:** …
4. **Scope (files touched + why):** …
5. **Verification method + result (incl. what couldn't be verified + how to check):** …
6. **History searched:** …
7. (format rule — n/a)
8. **DRY / duplication check:** …
9. **Fallbacks (none / removed / kept-because-legit):** …
10. **Attempts this task + root cause if >1:** …
11. **Reference pinned + what was left unchanged because already-correct:** …
12. **Checked uploads recursively before asking:** …
13. **Callers audited after any shared/contract change:** …
