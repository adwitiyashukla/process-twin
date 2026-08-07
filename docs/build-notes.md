# Build notes

Notes I wrote as I went. I built this in stages and wrote down what I decided and what I
still had to check before moving on, mostly so I would not forget why I did something two
weeks later.

## Stage 1: environment and skeleton

Got Docker Compose running Neo4j, Qdrant, Temporal and Langfuse, wrote the config module,
and built one trivial component end to end so I could see a model call turn into a validated
object and a traced cost before building anything real.

Two decisions here I would defend.

Langfuse v2 rather than v3. Self-hosting v3 needs ClickHouse, Redis, MinIO and a worker,
which is six or more containers. v2 needs one Postgres and gives me traces, spans, costs and
scores, all of which is what I actually use. I pinned the Python SDK below 3 to match.

Tracing degrades to nothing when credentials are missing. Tests, CI and keyless development
all run the same code path minus the export. The alternative would have been mocking Langfuse
everywhere, which tests the mock rather than the seam.

I also made `--dry-run` a real code path rather than a test fixture. CI uses it, and later the
compiler tests and evaluation runs use the same seam to execute whole workflows without a
single API call.

## Stage 2: reading the policy

Fetching, parsing to clause level with stable IDs, indexing into Qdrant, and a retriever.

The clause ID work took longer than everything else in this stage. The IDs have to come from
the document's own structure because the citation guardrail compares those strings later. If
re-parsing produced different IDs, every stored citation would silently point somewhere new.

The problem I did not anticipate: CFR paragraphs go (a), (b), (c) and so on, and after (h)
comes (i). That (i) is the letter i, not roman numeral one. A parser that checks for roman
numerals first corrupts every ID after that point, and 31 CFR 1010.230 genuinely goes up to
(j) so this was not theoretical. The rule I ended up with is that a marker continuing the
letter sequence beats the roman reading. There is a test pinning it.

Still to verify on a machine with network access: the 20 probe queries hitting the 0.9
threshold against the real corpus. The parsing and the ID stability are proven by tests.

## Stage 3: making the data

Six personas, six transcripts, sixty case logs, and a ledger of the ten divergences I planted.

The thing I got right here was keeping the ground-truth labels out of the data files. My
first instinct was to tag each case record with the delta it demonstrates, which would have
been convenient and would have made the whole delta-detection evaluation meaningless, because
the extractor would have been reading answers I wrote down for it.

I also made the seven error cases deliberately close to real patterns. One skips the callback
on a $50k account, just outside the informal threshold. Another has the address-mismatch
trigger but no referral. If the detector reports those as evidence of a practice, it is
wrong, and I wanted a test that catches that specific kind of wrong.

## Stage 4: extraction and the graph

Per-source extraction with a self-correction loop, entity resolution across sources, delta
detection, and loading into Neo4j.

The self-correction loop is the pattern I reuse most: ask the model for structured output,
validate with Pydantic, and if it fails, send the error message and the bad output back and
ask again. Three attempts, then write the batch to a dead-letter file with the whole error
chain and keep going. The runtime guardrails import this same function rather than
reimplementing it.

Entity resolution uses two thresholds with a gap in the middle. Above 0.80 similarity, merge.
Below 0.55, keep separate. In between, ask the model, and if the answer is unparseable, keep
them separate. Being conservative in the ambiguous band seemed better than merging on a
guess.

Delta detection is a rule table rather than an LLM making judgment calls. Every delta traces
back to the exact rule and the exact evidence that produced it, which is the first thing
anyone reviewing this would want to see. Using a model here would be more impressive-sounding
and much harder to defend.

Still to run with an API key: the full extraction pass and the real precision and recall
numbers. The rules recover all ten ledger entries on fixture inputs.

## Stage 5: the runtime

The compiler, the decision components, the guardrails, and the approvals API.

The compiler returns a plain data structure and a separate function turns it into LangGraph.
This meant I could test every compile rule without importing LangGraph, and it also meant the
evaluation runner could execute the spec directly, so evaluation and production share one
execution path.

Rules the compiler enforces: cycles rejected with the offending path printed, unreachable
nodes warned about, a step requiring evidence nothing can supply is a build error, and a step
carrying an unresolved high-severity delta gets a human gate placed between it and whatever
comes next so it cannot be bypassed.

The guardrail I am most attached to is the delta guard, specifically that model confidence
cannot override it. Confidence tells you how sure the model is about its own reasoning. It
tells you nothing about which side of a question the institution has not answered. A
0.99-confidence decision on an open policy conflict is the most dangerous output this system
could produce.

The other default I want to point at: if no reviewer is available when a case hits a gate,
the case halts. It does not proceed. An unattended system never approves on a human's behalf.

## Stage 6: durability and the audit log

One Temporal workflow per case, and an append-only hash-chained log.

The determinism rule is the thing to understand about Temporal. Workflow code gets replayed
against recorded history to rebuild state, so anything non-deterministic in the workflow body
takes a different path on replay. All of it lives in activities, whose results are read back
from history instead of recomputed. I enforce this with a script that parses the workflow
file and checks call targets, running in CI, because this is exactly the rule someone breaks
six months later without knowing it exists.

Duplicate audit entries would come from an activity that wrote its event then failed before
acknowledging, so Temporal retried it. The write is keyed on case, step and event type, and a
retry returns the existing hash.

Still to run: the kill-and-restart demo three times in a row on real infrastructure. The
chain verification and the replay are covered by tests.

## Stage 7: evaluation

Forty cases, the metrics, and the readiness report.

This stage found the most bugs, which was the point of building it. Two written EDD triggers
had disappeared into an additive risk score. My path fidelity metric was scoring correct
escalations as failures. A metric with an empty population was reporting zero. Three of my own
test cases encoded a position I decided was wrong once I saw all three fail the same way. All
of that is in FAILURES.md.

The first full run came out at 0.725 outcome accuracy. After the fixes it passes every
threshold. I am wary of how clean that looks, so the README says plainly what those numbers
do and do not measure: the components are deterministic, so this is the governance machinery
working, not evidence that an LLM makes good KYC decisions.

## Things I still want to check on real infrastructure

Docker Compose bringing all seven containers up healthy, and the hello component producing a
real trace with a cost in Langfuse.

The 20 retrieval probes against the real fetched corpus, hitting 0.9.

A full seed with an API key, for real delta precision and recall.

The durability demo three consecutive times.

A live approval round trip through the API with the Temporal signal.
