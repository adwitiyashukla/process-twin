# process-twin

A KYC onboarding agent that knows the difference between what the policy says and what
people actually do, and refuses to guess when the two disagree.

I am a masters student and I built this to learn how AI agents get deployed in places
where a wrong answer is expensive. Most agent projects I found online stop at "it works on
my machine". I wanted to go further and find out what it actually takes to say an agent is
safe to put in front of real customers.

## The problem I started with

I read a lot about why AI projects fail in banks and finance. The reason that came up
again and again was not that the model was bad. It was that the written procedure and the
real procedure are two different things.

The manual says one thing. The analyst who has been doing the job for eight years does
something slightly different, and usually for a good reason that never made it into any
document. If you train or prompt an agent on only the manual, it will be wrong in practice.
If you build it from only what people do, you have automated an undocumented rule, and now
nobody can defend it in an audit.

So I picked one real process, KYC customer onboarding at a bank, and tried to build a
system that handles both sources honestly instead of picking one.

## What the project does

It reads three kinds of input about the same process:

1. Real published policy: the FFIEC BSA/AML manual sections, the FinCEN CDD rule
   (31 CFR 1010.230), and FATF Recommendation 10.
2. Interview transcripts from six practitioner personas. These are synthetic and I say so
   clearly everywhere, because I do not have access to real KYC analysts.
3. Sixty historical case logs, also synthetic, showing how cases were actually handled.

It pulls process steps out of all three, matches up the ones that describe the same thing,
and builds a graph in Neo4j. When the sources disagree, it does not average them or pick a
winner. It creates a Delta node that records both sides with the evidence for each.

Then it compiles that graph into a runnable workflow and runs test cases through it, with
guardrails that stop it from doing anything it cannot justify.

## Demo 1: finding where practice and policy disagree

This is the part I am most happy with. The system found ten divergences. Here are six:

| Delta | What the policy says | What people actually do | Cases | Severity |
|---|---|---|---|---|
| D1 | Identify beneficial owners at 25% (31 CFR 1010.230) | Analysts apply full scrutiny from 20% for high-risk jurisdictions | 11 of 60 | high |
| D6 | Callback verification is a required control | Skipped for accounts under $10k expected activity | 6 of 60 | high |
| D8 | Screening runs at the standard match tolerance | Tolerance is widened by hand for transliterated names | 4 of 60 | high |
| D2 | Nothing written about expired ID plus a renewal receipt | Accepted, with a 30-day follow-up task | 5 of 60 | medium |
| D3 | No such rule exists in the policy at all | Two address mismatches means an automatic EDD referral | 5 of 60 | medium |
| D10 | Policy says nothing about PO-box addresses | QA rejects them, the frontline accepts them with one extra document | 4 of 60 | medium |

The rest are in [data/interviews/SYNTHETIC.md](data/interviews/SYNTHETIC.md).

D10 is my favourite one. It is not policy versus practice, it is two employees who
disagree with each other. Same customer, same facts, different answer depending on whose
desk the file lands on. When I first designed the extraction step I was going to just pick
whichever version appeared more often. Then I realised that is exactly the wrong thing to
do, because the disagreement is the finding. A compliance officer would want to know about
it. So the system keeps both sides.

```bash
make diff          # prints the diff as markdown
make api           # opens an interactive graph explorer at localhost:8000/explorer
```

## Demo 2: deciding whether it is safe to deploy

I did not want to just say "the agent works". I wanted a number I could defend. So I wrote
40 test cases covering clean applications, messy documents, real risk triggers, adversarial
attempts, and four cases that land exactly on the unresolved policy questions above.

`make report` runs all 40 and produces a report with a go or no-go verdict. Current run:

| Metric | Result | Threshold | Pass? |
|---|---|---|---|
| Outcome accuracy | 1.000 | 0.85 or higher | yes |
| Path fidelity | 1.000 | 0.90 or higher | yes |
| Escalation recall on policy-conflict cases | 1.000 | must be exactly 1.00 | yes |
| Escalation recall on adversarial cases | 1.000 | 0.83 or higher | yes |
| Escalation precision | 1.000 | 0.80 or higher | yes |
| Citation validity | 1.000 | 0.95 or higher | yes |
| Retrieval hit@5 | 0.950 | 0.90 or higher | yes |

A sample report is committed at [docs/sample-report/report.md](docs/sample-report/report.md)
so you can read it without running anything.

### The one threshold I set to 100%

Every metric above tolerates some error except one. Escalation on policy-conflict cases has
to be perfect, and I want to explain why I made that choice, because it is the design
decision I thought hardest about.

If the agent gets an ordinary case wrong, that is bad but it is a normal quality problem.
You measure it, you improve it, a reviewer can catch it.

But if a case lands exactly on a question the bank itself has not answered, where the rule
book says 25% and the floor says 20% and nobody has decided which one wins, and the agent
just picks one, then it has invented policy. It produces a confident decision with a clean
audit trail on a real customer's file, and the audit trail makes it look correct. There is
no way to catch that later. So the system is not allowed to do it at all, and if even one
of those four cases slips through, the whole run fails.

## What broke while I was building it

I kept a file called [FAILURES.md](FAILURES.md) with every bug I hit, how I found it, and
what I changed. There are ten entries. Three I would actually talk about in an interview:

**Two policy rules quietly stopped working.** I had implemented EDD triggers as
contributions to an overall risk score. A case with a beneficial owner at 30% in a
high-risk country scored "medium" and got approved straight through, even though the
written rule clearly requires escalation. The lesson I took from it: a categorical rule
should be a direct check on the case, not a number added to a total that might not cross a
threshold.

**My evaluation metric was punishing correct behaviour.** Path fidelity was showing 0.00
while every other signal said the system was fine. The metric demanded every step run, so
any case that correctly stopped at a human gate was scored as a failure. If I had tuned the
system to raise that number I would have been training it to stop escalating, which is the
opposite of the point. I rewrote the metric definition instead.

**My "reproducible" data was only reproducible on Linux.** I have a test asserting the case
logs regenerate byte for byte. It passed in CI nine times. Then I ran it on my own Windows
machine and it failed immediately: Python's `write_text()` had been silently using CRLF for
two of the three files. CI runs Ubuntu, so CI was never going to catch it. Single-OS CI
cannot verify a cross-platform claim.

## Running it

```bash
git clone https://github.com/adwitiyashukla/process-twin && cd process-twin
uv sync --all-extras
cp .env.example .env                    # add your ANTHROPIC_API_KEY here
docker compose up -d && python scripts/wait_healthy.py

make test                               # 126 tests, no Docker or API key needed
make report                             # Demo 2, the readiness report
make fetch parse index probe            # download policy docs, build the clause store
make seed                               # extraction and graph building (needs API key)
make diff                               # Demo 1, the policy-vs-practice diff
make api                                # explorer and approvals inbox
make demo-durability                    # kill the worker mid-case, watch it resume
```

## How it is built

**Reading the policy.** Clauses get IDs from the document structure itself, like
`CFR-1010.230(b)(1)`, not from where a chunk happens to start. This matters because the
citation checker compares those strings. If an ID silently points somewhere new after a
re-parse, every audit record referencing it becomes wrong without anyone noticing. Getting
this right was harder than I expected. CFR paragraphs go (a), (b) ... (h), (i), and that
(i) is the letter i, not roman numeral one, so a naive parser corrupts every ID after that
point.

**Extraction.** The LLM is asked for structured output, Pydantic validates it, and if
validation fails the error message and the bad output are fed back to the model to try
again. Three attempts, then the batch is written to a dead-letter file with the full error
chain and the pipeline keeps going instead of crashing.

**Reconciliation.** Same real-world step described three different ways gets merged. Where
sources agree, confidence goes up. Where they disagree, the written value stays canonical
and the disagreement becomes a Delta.

**The compiler.** The graph compiles into a workflow. Controls become checkpoints,
high-severity deltas become mandatory human gates, cycles are rejected at compile time, and
a step needing evidence that no component can produce is a build error rather than a
failure at 3am. The graph is the source of truth, so changing the process is a re-compile,
not a code rewrite.

**Guardrails.** Every decision must cite a clause that exists and is actually relevant,
checked with a cross-encoder. Low confidence sends the case to a human. An unresolved
high-severity delta sends it to a human regardless of how confident the model is, because
confidence tells you how sure the model is about its own reasoning, not which side of an
open question is correct.

**Durability.** Each case is a Temporal workflow. A case waiting for a human sleeps without
holding a process, and if you kill the worker mid-case it resumes at the same step. All the
non-deterministic work lives in activities, never in workflow code, and there is a script in
CI that checks this by parsing the file rather than trusting me to remember.

**Audit.** Every state change appends to a hash-chained log. Each entry carries the previous
entry's hash, so editing or deleting history breaks the chain and the checker says exactly
where.

## What this project does not do

The interview transcripts and case logs are **synthetic**. I generated them, and I documented
exactly how in [SYNTHETIC.md](data/interviews/SYNTHETIC.md), including an argument for why
this does not make the delta-detection evaluation meaningless and what would. I am a
student, I do not have access to real KYC analysts or real customer files. The policy
documents are real and public.

The evaluation measures the governance machinery, not LLM judgment quality. The v1
decision components are deterministic on purpose so an examiner could re-derive every
threshold by hand. That means those 1.000 scores say the guardrails and gates and routing
work correctly. They do not say an LLM makes good KYC decisions.

One process, one jurisdiction, no real personal data, single machine, no fine-tuning.

Delta detection is a rule table, not an LLM making judgment calls, so every delta traces to
the exact rule that produced it. LLM-assisted detection is something I would like to try next.

High-risk countries in the synthetic data are made up (Kavastan, Zubaria, Port Meridian) so
nothing here mislabels a real country or breaks when FATF updates its lists.

## What I would do next

Move two of the deterministic activities to a Go worker over gRPC, mostly to learn the
cross-language Temporal story. Point the whole thing at a second process, probably
healthcare prior-authorisation, to find out how much of this generalises and how much I
overfit to KYC. Add semantic evaluation. Add a Windows and Linux CI matrix, since I now
know from experience why that matters.

## More detail

[Design decisions and why I made them](docs/architecture.md)

[The graph schema](docs/graph-schema.md)

[How the evaluation works](docs/eval-methodology.md)

[Build notes I kept as I went](docs/build-notes.md)

[Things that broke](FAILURES.md)

## Built with

Python 3.11, Pydantic v2, LangGraph, Neo4j, Qdrant with BGE embeddings, Temporal, Langfuse,
FastAPI, pytest, ruff, Docker Compose.

MIT licensed. Built by Adi Shukla.
