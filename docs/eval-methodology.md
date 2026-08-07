# How the evaluation works

This explains how I built the test suite, what each metric means, and why every threshold
is where it is. The numbers quoted anywhere in this repo come from an actual run of
`make report`, which writes a versioned report under `reports/`.

## The 40 test cases

I wrote 40 cases by hand rather than generating permutations, because a permutation tells
you nothing when it fails. Each case is a fact pattern I could describe to a person.

| Category | Count | What it is for |
|---|---|---|
| Clean | 12 | Catching false escalations. A system that escalates everything is useless, because reviewers stop reading. These have to run straight through. |
| Documentary edge | 10 | Real document mess: expired ID with a renewal receipt, maiden-name mismatch, transliterated names, address mismatches, PO boxes, proof of address right at the age limit, foreign tax IDs. |
| Risk and EDD | 8 | The written escalation triggers: PEP matches, beneficial ownership at and around the 25% line, complex ownership, adverse media, high-risk jurisdictions. |
| Adversarial | 6 | Deliberate evasion: structuring-shaped funding, synthetic identity signals, document tampering, straw-man owners, rapid resubmission, business purpose that does not match stated activity. |
| Policy conflict | 4 | Cases landing exactly on the unresolved deltas. The system must route these to a human. |

Cases that sit on a delta carry a `targets_delta` field, so when one fails I know which
governance question broke rather than just seeing a score drop.

## The metrics

**Outcome accuracy**, threshold 0.85. Does the final decision match what I expected. Not
1.00, because demanding perfection on a suite this size pushes toward overfitting the 40
cases I happened to write, which teaches me nothing about the 41st.

**Path fidelity**, threshold 0.90. Did the case walk the expected route. This one took me
three attempts to define correctly.

The compiled workflow runs steps a given case does not care about. The callback control runs
for everyone. Beneficial ownership runs for individuals too and returns "not applicable". So
I project the actual path onto the expected steps and compare that projection, instead of
demanding an exact match.

There are then two cases. If the case ran to completion, the projection has to equal the
expected route exactly. If it stopped at a human gate, the projection has to be an in-order
prefix of it. The prefix rule exists because a workflow that halts for a human has not
failed. My first version scored every correct escalation as a path failure, which meant
optimising that metric would have trained the system to stop escalating. That is the
opposite of what this project is for.

**Escalation recall on policy-conflict cases**, threshold 1.00, and this one is a hard gate.
See below, it has its own section.

**Escalation recall on adversarial cases**, threshold 0.83, five out of six. Adversarial
patterns are open-ended and detecting them is genuinely hard. One miss is survivable. Two
means the signals are not wired up properly.

**Escalation precision**, threshold 0.80. This is the counterweight to the recall gates.
Without it I could pass everything by escalating every case. Low precision means alert
fatigue, and a control that reviewers learn to rubber-stamp has been switched off in
practice while still looking green on a dashboard.

**Citation validity**, threshold 0.95. Every decision has to cite a clause that exists and
is relevant. Two failure modes, both caught: a made-up clause ID (existence check), and a
real clause that does not actually support the decision (relevance check via cross-encoder).
The second one is the subtle failure and the reason existence alone is not enough.

**Retrieval hit@5**, threshold 0.90. The clauses a case must cite have to actually reach the
component making the decision. A citation guardrail can only validate what retrieval found.

**Confidence calibration**, reported but not gated. Bucketed accuracy plus a Brier score. It
matters operationally because the confidence gate routes on this number, so if the system
were systematically overconfident the gate would quietly stop working while every other
metric still looked fine.

**Cost and latency**, reported. The v1 components are deterministic so suite cost is zero.
This becomes a real line when components take the LLM path.

## Why the policy-conflict gate is 100%

This is the design decision I thought about longest, and the one I would most want to defend
in an interview.

Every other metric tolerates error. This one does not, and the reason is the shape of the
failure rather than how often it happens.

When the system decides an ordinary case wrongly, it produces a wrong answer. That is a
normal quality problem. You measure it, you improve it, review catches some of it.

When the system hits a case sitting exactly on a question the institution itself has not
answered, where the rule book says 25% and the floor practises 20% and nobody has decided
which governs, and it picks one, something different happens. It produces a confidently
wrong decision with a clean audit trail, on a real customer's file, having invented policy
it had no authority to invent. The audit trail makes it look correct. There is no signal
that anything went wrong.

That is not a quality defect. It is the system exceeding its remit. No amount of accuracy
elsewhere compensates for it, so one miss out of four fails the entire run.

## Four rules that keep the numbers honest

**The evaluation runs the production executor.** `evaluation/runner.py` calls the same
`runtime/executor.py` the workflow uses. If evaluation had its own execution path I would be
measuring code that never ships.

**Nothing is auto-approved during evaluation.** When a case hits a gate it is recorded as an
escalation and stops there. I could have scripted a reviewer who always approves, to see what
would have happened next, but that would inflate outcome accuracy with decisions no human
made. The escalation is the result being measured.

**A metric with no cases is "not applicable", never 0.0.** I hit this when a subset had no
adversarial cases and the metric computed 0/0 as zero, failed its threshold, and turned a
passing run into a failure. Division by zero in a metric is not a score, it is an absence of
measurement.

**Expectations encode a stated position, and I state it.** The system only rejects
autonomously on unambiguous grounds, which currently means a hard sanctions match. Failed
verification, tamper indicators and synthetic identity signals all go to a human, because
auto-rejecting on those denies real customers based on heuristics with real false-positive
rates. Three of my golden cases originally expected an automatic rejection. I changed them,
and I wrote down why in FAILURES.md rather than quietly editing the YAML, because changing a
test to make it pass is only legitimate when the reasoning survives being written down.

## Delta detection

Scored separately, since it happens during extraction rather than at runtime. Precision and
recall against the frozen ledger in `data/interviews/SYNTHETIC.md`, target 0.7 for both.
Misses and false positives go into FAILURES.md. A delta the system invents is as damaging as
one it misses, because both end up on a compliance officer's desk.
