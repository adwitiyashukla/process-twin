# The synthetic data, and why it is synthetic

Everything in `transcripts/` and in `data/case_logs/` was written by me. There are no real
customers, employees, banks or cases anywhere in this project.

I am a student. I do not have access to KYC analysts at a bank, and I could not get real
onboarding case files even if I asked, because they are full of personal data. So I made the
data instead, and this file documents exactly how, so nobody has to guess how much of the
result is real.

The policy documents are real and public: the FFIEC BSA/AML examination manual, the FinCEN
CDD rule at 31 CFR 1010.230, and FATF Recommendation 10.

## How I made it

**The transcripts.** Six personas, each with a role, a length of service, an attitude to
risk, and a set of things they know about. I wrote one interview per persona following the
same question guide, and made each one voice their assigned divergences as ordinary
workplace stories rather than as a list. I also put deliberate red herrings in every
transcript, complaints about slow software and bad dashboards, so the extraction step has
something it should correctly ignore.

The transcripts are frozen and committed. I do not regenerate them, because the delta
evaluation scores against them and regenerating would quietly move the ground truth under
the test. `scripts/generate_interviews.py --check` verifies that every divergence in the
ledger below is still actually voiced in the right transcript, and that check runs as part
of the test suite.

**The case logs.** Sixty records, produced by a generator with no randomness and no LLM.
Every value derives from the case index, so the same files come out on any machine. A test
asserts this byte for byte, and it is how I found a bug where two of the three files were
getting Windows line endings.

The split is 35 policy-consistent cases, 18 showing the tacit patterns, and 7 containing
genuine mistakes.

**The ground truth lives in a separate file.** `cases.jsonl` contains no delta labels at all.
The tags are in `ground_truth_tags.json`, which only the evaluation reads. If the labels were
inside the case records, the extraction step would be finding answers I had already written
down for it, and the precision and recall numbers would mean nothing. There is a test that
greps the case file for label vocabulary to make sure this stays true.

**The error cases are near-misses on purpose.** Two of the seven look like tacit patterns but
are not. One skips the callback on a $50k account, which is outside the informal under-$10k
threshold. Another notes two address mismatches and approves anyway, with no referral. These
are traps for a lazy detector, and they are never tagged with a delta. If the system reports
them as evidence of a practice, that counts against its precision.

**High-risk countries are invented.** Kavastan, Zubaria and Port Meridian. Real countries
move on and off risk lists, and I did not want a synthetic dataset that implies something
about a real place or breaks when FATF publishes an update.

## Does synthetic data make the evaluation meaningless

I think this is the fair question to ask about this project, so here is my answer.

What the evaluation measures is whether the pipeline recovers divergences that verifiably
exist in its inputs. The ledger below defines what exists. That question is answerable with
synthetic data, and the answer is real.

What it does not measure is performance on how people actually talk. My transcripts are
cleaner and better organised than a real interview transcript would be. A real one would have
interruptions, contradictions, and someone remembering something wrong. So the numbers here
are an upper bound on what this pipeline would do with real interviews.

What would actually invalidate it: if the labels leaked into what the extractor sees, if the
divergences were phrased in the transcripts as near-copies of the ledger text rather than as
stories, or if I tuned the detector against this ledger and then reported the same ledger's
numbers. I have tested against the first, written the transcripts to avoid the second, and
kept detector development separate from the scoring runs for the third.

## The ledger

This is the ground truth. Detected divergences are scored against this table, targeting 0.7
precision and 0.7 recall.

The written positions cite clause families rather than exact paragraph numbers, because
FFIEC paragraph numbering only exists after you run `make fetch parse`.

| ID | Kind | Severity | What the policy says | What people do | Who says so | Cases |
|----|------|-----|------------------|--------------------|-----------|-------------|
| D1 | threshold | high | Beneficial owners identified at 25%, CFR-1010.230(b) | Full scrutiny and an EDD referral from 20% when the owner is in a high-risk jurisdiction | P1, P3 | 11 |
| D2 | undocumented acceptance | medium | Nothing written about an expired primary ID, FFIEC-CIP | Expired passport accepted with an official renewal receipt, plus a 30-day follow-up task | P4, P6 | 5 |
| D3 | unwritten rule | medium | No such trigger appears anywhere in policy | Two address mismatches across documents means an automatic EDD referral | P4, P5 | 5 |
| D4 | sequence | low | Policy implies identity verification happens before screening | Sanctions and PEP screening runs first, to fail fast before spending analyst time | P1, P6 | 8 |
| D5 | stricter practice | low | Utility bills accepted up to 90 days old, FFIEC-CIP | Senior analysts only accept 60 days or newer | P1, P2 | 6 |
| D6 | skipped step | high | Callback verification is a written control, FFIEC-CIP | Skipped for accounts under $10k expected activity | P2, P4, P6 | 6 |
| D7 | informal escalation | medium | PEP-associate cases go to a formal EDD ticket, FFIEC-CDD | A senior analyst walks over and briefs the compliance officer verbally first, ticket comes after | P3, P5 | 3 |
| D8 | tooling workaround | high | Name screening runs at the standard match tolerance | Tolerance widened by hand for names that look transliterated | P1, P5 | 4 |
| D9 | gap | medium | No written guidance for applicants with only a foreign tax ID | Sent ad hoc to the EDD specialist, decided case by case | P3, P5 | 3 |
| D10 | practitioner conflict | medium | Policy says nothing about PO-box addresses | QA rejects them outright, the frontline accepts them with one extra document | P2 against P4 | 4 |

D10's four cases split evenly: two where the address was rejected at review, two where it was
accepted with a supplemental document. Both stances need evidence, otherwise it is not a
conflict.

Severity follows one rule: regulatory exposure first, then customer impact, then efficiency.
D1, D6 and D8 are high because an undocumented threshold on a certified requirement, a
skipped verification control, and a widened screening tolerance are the three things an
examiner would write up.

## What the diff demo recommends for each one

D1, write down the 20% high-risk practice or align to 25% and retrain. D2, codify the
renewal-receipt acceptance with its follow-up task. D3, write down the trigger, it is good
control design. D4, update the written order, screening first is defensible. D5, pick one
number. D6, retrain, a control is being skipped on an invented threshold. D7, ticket first
and conversation second. D8, fix the matcher, transliteration handling does not belong in a
per-analyst override. D9, write the foreign-tax-ID procedure down. D10, pick a rule, two
identical customers getting different answers is indefensible.
