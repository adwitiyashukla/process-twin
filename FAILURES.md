# Things that broke

I kept this file from the start of the project. Every time something broke I wrote down
what happened, how I found it, what I changed, and what stops it happening again.

I am keeping it in the repo on purpose. A project where nothing went wrong is a project
where nobody looked. Most of the interesting engineering in this repo is in these entries
rather than in the code that worked first time.

---

## Two policy rules quietly stopped firing

**What broke.** Two test cases came back approved that should have escalated. One was a
beneficial owner holding 30% of an entity in a high-risk jurisdiction. The other was an
entity with four owners spread across four countries. Both are written EDD triggers, so both
should have gone to enhanced due diligence.

**How I found it.** The first full run of the 40-case suite. Outcome accuracy came out at
0.725 and those two were in the failure list. My unit tests had not caught it because they
tested each component on its own, where each one returned a risk score that looked perfectly
reasonable in isolation.

**What was wrong.** I had implemented both triggers as contributions to an additive risk
score. The 30% owner scored 3, which lands on "medium", and my EDD check only fired at
"high". So a rule that policy states unconditionally was silently gated behind a threshold
it never crossed.

**The fix.** `determine_edd_requirement` now evaluates the written triggers directly against
the case: is there an owner at or above 25% in a high-risk jurisdiction, is the ownership
structure complex and multi-jurisdictional. Scores still rank overall risk, but a
categorical policy rule is now a predicate on the case, never a number added to a total.

**What I learned.** If policy states a rule unconditionally, the code should state it
unconditionally too. Turning a rule into a score contribution feels more sophisticated and
quietly makes the rule optional.

---

## My evaluation metric was punishing correct behaviour

**What broke.** Path fidelity read 0.00, then 0.65 after a first attempt at fixing it. Every
other signal said the system was behaving correctly.

**How I found it.** Fourteen path failures on cases whose outcomes were all correct. When one
metric disagrees with every other metric, the metric is usually the thing that is wrong.

**What was wrong.** Two problems. My definition demanded that every expected step execute, so
a case that correctly stopped at a human gate was scored as a path failure. And the compiled
workflow legitimately runs steps a given case does not list, like the callback control which
runs for everyone, so those extra steps counted against cases that never mentioned them.

**The fix.** I project the actual path onto the expected step set, then require exact
equality for completed cases and an in-order prefix for cases that stopped early. Skipped or
reordered steps still fail. Halting correctly does not.

**What I learned.** This is the one that worried me most. If I had tried to raise that number
by changing the system instead of the metric, I would have been tuning it to stop escalating
cases, which is precisely the behaviour this project exists to prevent. A badly defined
metric does not just measure the wrong thing, it pulls the whole system in the wrong
direction.

---

## A metric with no cases reported zero and failed the run

**What broke.** A test using a small evaluation set got a NO-GO verdict because of
`escalation_recall_adversarial`, even though that set contained no adversarial cases at all.

**How I found it.** A unit test I wrote to check the hard gate behaviour failed for a
completely unrelated reason.

**What was wrong.** Zero adversarial cases meant zero divided by zero, which my code computed
as 0.0, which then failed the 0.83 threshold.

**The fix.** `compute_metrics` now takes the population size, and an empty population reports
"not applicable" rather than a score.

**What I learned.** A check has three possible states, not two: passed, failed, and not
measured. Collapsing the third into either of the other two produces a wrong answer with no
warning.

---

## Three of my own test cases encoded the wrong position

**What broke.** Three cases expected the system to reject the applicant outright: no primary
identity document, synthetic identity signals, and document tampering indicators. The system
escalated all three to a human instead, and was scored wrong for it.

**How I found it.** All three failures had the same shape, which made me stop and think about
whether the system or the expectation was wrong.

**What was wrong.** My expectations, not the system. Every one of those signals is a
heuristic with a real false-positive rate. Auto-rejecting on them means denying a real
customer an account because a document scanner was suspicious. The correct behaviour is to
put it in front of a person.

**The fix.** I updated the three cases and, more importantly, wrote the position down in
docs/eval-methodology.md: the system only rejects autonomously on unambiguous grounds, which
currently means a confirmed sanctions match. Everything else that fails goes to a human.

**What I learned.** Changing a test to make it pass is usually a bad sign. It is legitimate
only when the reasoning survives being written down where someone can disagree with it.
Recording it here rather than quietly editing the YAML is the whole point.

---

## The guardrails hid the useful explanation

**What broke.** A beneficial ownership boundary case, an owner at 22% in a high-risk
jurisdiction, escalated with the reason "confidence 0.50 < 0.7". Technically true, useless to
a reviewer.

**How I found it.** A test asserting that the escalation reason mentions the unresolved
threshold, which failed on the confidence string.

**What was wrong.** The component had a precise explanation ready, that the case sits between
the written 25% rule and the practised 20% one. The generic confidence gate ran first and
its message won.

**The fix.** Reordered the guardrails by how fundamental each problem is: delta guard,
citation validity, the component's own stated reason, then confidence as the catch-all. Low
confidence is usually a symptom of the component encoding an unresolved question, so the
component's reason should outrank it.

**What I learned.** When several checks can fail, the order determines what the human reads.
That is a design decision, not an implementation detail.

---

## My reproducibility guarantee only held on Linux

**What broke.** I have a test asserting the 60 case logs regenerate byte for byte from their
generator. It failed the first time I ran the suite on my own Windows machine:
`ground_truth_tags.json drifted from its generator`, difference at index 1, `\n` against
`\r\n`.

**How I found it.** Running the tests locally on Windows, minutes after publishing the repo.
CI had been green nine times in a row.

**What was wrong.** I wrote `cases.jsonl` through an explicit `open(..., newline="\n")` but
wrote the two JSON sidecars with `Path.write_text()`, which uses the platform default. On
Windows those two files got CRLF. So the reproducibility claim in my README was true on Linux
and false on Windows, and CI runs Ubuntu so CI was never going to tell me.

**The fix.** Every artefact write now pins `newline="\n"` explicitly.

**What I learned.** Single-OS CI cannot verify a cross-platform claim. Nine green runs proved
the code worked on Ubuntu, which was never the thing in doubt. A CI matrix is now on my
roadmap for exactly this reason.

---

## The delta detector counted mistakes as evidence

**What broke.** One of my deliberate error cases, where an analyst noted two address
mismatches and approved the file anyway with no referral, was being counted as support for
the tacit pattern that says two mismatches trigger an automatic referral.

**How I found it.** A test I wrote specifically against the seven error cases I had planted
in the synthetic data as traps.

**What was wrong.** My pattern predicates matched on the trigger alone. Having the trigger
present is not the same as the practised response happening.

**The fix.** Every pattern now requires both the trigger and the response together: mismatch
and referral, callback skipped and activity under the informal threshold.

**What I learned.** A pattern needs supporting behaviour, not just a matching condition. One
mistake is noise. Treating noise as a pattern means reporting an invented practice to a
compliance officer, which is as bad as missing a real one.

---

## The ledger claimed evidence the data did not contain

**What broke.** Two cases were tagged with delta D5 in my ground-truth file, but the
generator never wrote the actual evidence into those case records. My pattern miner found
four supporting cases where the ledger claimed six.

**How I found it.** Writing a test that mines the raw case logs alone, with no access to the
ground-truth tags, and checks that every count the ledger claims is recoverable from the data
itself. D5 came up short.

**The fix.** Added the missing branch to the generator and regenerated the corpus.

**What I learned.** Ground truth that is not derivable from the data is not ground truth, it
is a claim. The lockstep test now makes it impossible for a tag to exist without evidence
behind it.

---

## The determinism checker flagged its own documentation

**What broke.** My script that enforces the Temporal determinism rule reported the workflow
file as violating it. The "violation" was the sentence in the module docstring saying the
module contains no `datetime.now()` calls.

**How I found it.** First run of the check. The reported line number pointed at prose.

**The fix.** Rewrote it to parse the AST and inspect call targets instead of matching text.

**What I learned.** A guard over source code should analyse structure, not text, so it checks
what the code does rather than what it says. The same reasoning is why the citation guardrail
checks relevance and not just whether a clause ID exists.

---

## A verification step reported a pass for checks that never ran

**What broke.** My publish script runs lint and tests before pushing. On a machine without
`uv` installed, both commands failed to launch, and the script printed "lint and tests green"
anyway and pushed.

**How I found it.** Reading the actual console output instead of the summary line. The
CommandNotFoundException was visible directly above the green success message.

**What was wrong.** PowerShell raised the exception, `$LASTEXITCODE` kept a stale zero from
the previous successful command, and both of my `-ne 0` guards passed.

**The fix.** The script checks that the tool exists first, and says SKIPPED explicitly when it
does not.

**What I learned.** Same lesson as the empty-population metric, in a different place: a check
that cannot distinguish "passed" from "never ran" is worse than having no check, because it
gets trusted.
