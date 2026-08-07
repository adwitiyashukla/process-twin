# Demo video plan

Three minutes. Notes for what to show and roughly what to say, so I do not ramble.

Before recording: services up, seed done, the API running in one terminal, a Temporal worker
in another, and a third terminal free.

**Opening, about 20 seconds.** Show the architecture diagram.

Two things are true in every bank. There is a written procedure, and there is what people
actually do. They are never the same document. Building an agent on either one alone is how
automated compliance goes wrong. This finds the gap and then governs it.

**Demo 1, up to about a minute.** Browser at localhost:8000/explorer. Turn on diff mode, so
the graph collapses down to just the divergences and the steps they touch. Click D1.

The rule says identify beneficial owners at twenty-five percent. Analysts apply full scrutiny
from twenty for high-risk jurisdictions. The system found that in the interviews, confirmed it
in eleven of sixty historical cases, and kept it as its own node with the clause on one side
and the practitioner evidence on the other.

Click D10.

This one is a disagreement between two employees, not between policy and practice. QA rejects
PO-box addresses, the frontline accepts them with an extra document. Same customer, opposite
answers. Most pipelines would average that away during extraction, and averaging it away is
how you end up shipping an undocumented rule.

**The runtime, up to about 1:50.** Run `make run-case CASE=GC-037`.

This applicant has a beneficial owner at twenty-one percent in a high-risk jurisdiction, which
is exactly the unresolved question. Watch what it does not do.

Show the halt and the reason. Switch to localhost:8000/approvals.

It stopped with full context: the clause, the practised threshold, the evidence, and why it
refused. The confidence gate is not what stopped it, the delta guard did, and confidence
cannot override that. A machine should not pick a side of a question the bank itself has not
answered.

Post the approval, show the case resuming and finishing.

**Durability, up to about 2:20.** Run `make demo-durability`.

Kill the worker mid-case, restart it. Temporal replays the history, activity results get read
back instead of recomputed, and the case picks up at the same step. The audit trail has no gap
and no duplicate, because the writes are keyed on case and step.

Show the replay output and the intact chain.

**Demo 2, up to about 2:50.** Run `make report`, open the HTML.

Forty cases, verdict at the top, thresholds underneath. Point at the asymmetry: outcome
accuracy passes at eighty-five percent, but escalation on policy-conflict cases is a hard gate
at one hundred. Getting an ordinary case wrong is a quality problem. Silently resolving a
question nobody has resolved produces a confident wrong answer with a clean audit trail, and
that one gates the release.

Scroll to calibration.

Calibration is reported because the confidence gate routes on it. If the system were
systematically overconfident, the gate would stop working while every other number still
looked fine.

**Close, last ten seconds.** Run `make replay CASE=GC-037`.

Every decision, its citations, its confidence, who decided it, reconstructed from an
append-only hash chain. That is the difference between an agent that works and an agent you
could actually deploy.
