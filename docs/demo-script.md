# Demo video script (3 minutes)

Record with OBS or the Windows Game Bar (Win+G). Terminal at ~16pt, browser at 110% zoom.
Do a silent dry run first — the beats are tight.

**Setup before recording:** `make up` healthy, `make seed` done, `make api` running in one
terminal, `make worker` in another, a third terminal free.

---

**0:00–0:20 — the problem.** Camera on the README diagram.
> "Two things are true in every regulated bank: the written procedure and what people
> actually do. They are never the same document. Deploying an agent against either one
> alone is how automated compliance fails. This system finds the gap, then governs it."

**0:20–1:00 — Demo 1, the delta explorer.** Browser at `localhost:8000/explorer`.
Toggle *diff mode* — the graph collapses to deltas and the steps they touch. Click **D1**.
> "The rule says identify beneficial owners at twenty-five percent. Analysts apply full
> scrutiny from twenty for high-risk jurisdictions. The system found that in the interviews,
> confirmed it in eleven of sixty historical cases, and kept it as a first-class node — with
> the clause on one side and the practitioner evidence on the other."

Click **D10**.
> "This one is a conflict *between practitioners*. QA rejects PO-box addresses; the frontline
> accepts them with an extra document. Same facts, opposite outcomes. Most pipelines average
> that away during extraction. Averaging it away is how you ship an undocumented rule."

**1:00–1:50 — governed runtime, live.** Terminal:
```
make run-case CASE=GC-037
```
> "This applicant has a beneficial owner at twenty-one percent in a high-risk jurisdiction —
> exactly the unresolved question. Watch what it does *not* do."

Show the halt and the reason. Switch to `localhost:8000/approvals`.
> "It stopped, with full context: the clause, the practised threshold, the evidence, and why
> it refused to decide. The confidence gate isn't what stopped it — the delta guard did, and
> confidence can't override that. A machine must not pick a side of a question the
> institution hasn't answered."

`POST` the approval, show the case resuming and completing.

**1:50–2:20 — durability.** Terminal: `make demo-durability`.
> "Kill the worker mid-case. Restart. Temporal replays history, activity results are read
> back rather than recomputed, and the case picks up at the same step. The audit trail has
> no gap and no duplicate — the writes are idempotent on case and step."

Show the replay output and the intact hash chain.

**2:20–2:50 — Demo 2, the readiness report.** `make report`, then open the HTML.
> "Forty golden cases. Verdict at the top, thresholds underneath. Note the asymmetry:
> outcome accuracy passes at eighty-five percent, but escalation recall on policy-conflict
> cases is a hard gate at one hundred. Getting an ordinary case wrong is a quality problem.
> Silently resolving a policy question nobody has resolved produces a confidently-wrong
> decision with a clean audit trail. That one gates the release."

Scroll to the calibration table.
> "Calibration is reported because the confidence gate routes on it — systematic
> overconfidence would disable the gate while every other number still looked green."

**2:50–3:00 — close on the audit log.** `make replay CASE=GC-037`.
> "Every decision, its citations, its confidence, who decided it — reconstructed from an
> append-only hash chain. That's the difference between an agent that works and an agent you
> can deploy."
