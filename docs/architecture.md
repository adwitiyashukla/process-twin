# Design decisions

These are the choices I made while building this and why. I wrote each one down when I
made it, not afterwards, so a few of them are wrong in hindsight and I have said so where
that is the case.

## Why a graph and not just a vector store

My first instinct was to put everything in a vector database and let retrieval sort it out.
The reason I did not is that I need to answer questions like "show me every step that came
from a source with no written policy behind it" and "for this step, list every place the
information came from". Those are graph traversals. In a flat vector store you can only ask
"what is similar to this", which does not help when the whole point is tracking where a
piece of knowledge originated.

The graph also makes the delta idea possible at all. A Delta is a node connected to the
step it is about, the clause it contradicts, and the evidence for the practised version.
That shape does not exist in a vector index.

## Why disagreements become nodes instead of being resolved

This is the decision the whole project rests on.

When three sources describe the same step differently, the obvious move is to pick the most
common version or average the values. I nearly did that. The problem is that both ways of
resolving it are wrong:

If you side with practice, you have taken an undocumented rule and made it the system's
official behaviour. Nobody approved that, and there is now no record that it was ever a
question.

If you side with policy, you throw away the reason the practice exists. Analysts widened
the screening tolerance for transliterated names because the matcher was missing real hits.
Deleting that knowledge makes the system worse, not more compliant.

So the written value stays canonical, and the disagreement becomes a Delta node with both
sides attached. A human decides. The system's job is to surface the question clearly, not to
answer it.

## Why the workflow is compiled from the graph

I could have written the KYC workflow by hand in LangGraph. Compiling it from the graph
means the graph is the single source of truth: when extraction finds a new control or a new
delta, the workflow changes on the next compile without anyone editing Python.

It also makes the compile step a place to enforce rules. Missing evidence becomes a build
error instead of a runtime failure. A newly detected high-severity delta automatically gets
a human gate. If the workflow were hand-written, both of those would depend on someone
remembering.

## Why the compiler emits a plain data structure

`compile_workflow` returns a `WorkflowSpec`, which is just Pydantic models. Turning that
into an actual LangGraph object is a separate function.

I split it this way so I could unit test every compile rule without importing LangGraph at
all. The cycle detection, the evidence checks, the gate placement, all of it is testable
against plain dicts. The evaluation runner also executes the spec directly, which means the
eval and the runtime share one execution path instead of drifting apart.

## Why cycles are rejected

A process graph with a loop makes path fidelity meaningless and gives no termination
guarantee. The thing people usually want a loop for is retrying a failed step, and that
belongs in Temporal's retry policy where it gets backoff, a cap, and visibility. So the
compiler rejects cycles and prints the offending path.

## Why the decision components are deterministic

The thresholds, the ownership arithmetic, the list logic: all of it is plain Python, not
model output. Two reasons. An examiner should be able to re-derive any threshold decision by
hand. And evaluation numbers should not move because a model sampled differently today.

The trade-off is real and I say so in the README: this means the evaluation measures the
governance machinery, not LLM judgment. The LLM seam exists for the parts that genuinely
need judgment.

## Why clause IDs come from document structure

IDs like `CFR-1010.230(b)(1)` are built from the regulation's own paragraph hierarchy, never
from chunk offsets. The citation guardrail compares those strings, so if re-parsing the same
document produced different IDs, every stored citation would silently point somewhere new
and every audit record would become wrong without any error appearing.

This was harder than I expected. CFR paragraphs run (a), (b) ... (h), (i), (j), and that (i)
is the letter i, not roman numeral one. A parser that assumes roman numerals corrupts every
ID from that point on. 31 CFR 1010.230 really does go up to (j), so this was not
hypothetical. The rule I settled on: a marker that continues the letter sequence wins over
the roman reading.

## Why I fetch the CFR from the eCFR API instead of a PDF

The eCFR versioner API serves structured XML with the paragraph hierarchy already marked up,
and it accepts an as-of date so re-fetching gives identical bytes. Parsing a PDF would have
meant reconstructing that hierarchy with regexes. FFIEC sections come from their HTML pages
for the same reason. FATF is the one source with no structured version, so it is the only
place I parse PDF text.

## Why some processed clauses are committed and others are not

FFIEC and CFR are US government works in the public domain, so the processed clause files
are committed and a fresh clone works immediately. FATF text is copyrighted, so those files
are gitignored and regenerated locally. Every probe and evaluation case that has to work out
of the box cites CFR or FFIEC.

## Why fastembed instead of sentence-transformers

sentence-transformers pulls in torch, which is about 2GB. fastembed runs the same BGE models
through ONNX on CPU with no torch and no API cost per embedding. On a student laptop that
matters.

Tests use a deterministic hashing embedder instead, clearly marked as non-semantic. It
measures character overlap, not meaning, so it can verify that indexing and search and the
k-limits work without downloading anything. Actual retrieval quality is measured by
`make probe` against the real corpus with the real models, which is the only honest way to
measure it.

## Why guardrails run in a specific order

Delta guard, then citation validity, then the component's own reason, then the confidence
gate. The order is by how fundamental the problem is, because the first failure supplies the
reason the reviewer sees.

I got this wrong initially. A boundary case escalated with the message "confidence 0.50 <
0.7", which is true but useless. The component had a precise explanation ready, that the case
sits between the written 25% rule and the practised 20% one, and the generic confidence check
fired first and won. Low confidence is usually a symptom of the component encoding an
unresolved question, so the component's own reason should outrank it.

## Why Temporal instead of a job queue

Three things a queue does not give you. Signals, so a case can sleep for days waiting on a
human without holding a process. Replay-based recovery, so killing the worker mid-case
resumes at the same step. Durable timers.

The cost is the determinism constraint: workflow code gets replayed against recorded
history, so it cannot call an LLM or read the clock or generate a UUID. All of that lives in
activities, whose results are read back from history rather than recomputed. I enforce this
with a script that parses the workflow file and checks the call targets, running in CI,
because this is exactly the kind of rule that gets broken six months later by someone who
did not know about it.

The first version of that script used a regex over the file text and flagged its own
docstring, which mentioned `datetime.now()` while explaining that the module does not call
it. Analysing the AST checks what the code does rather than what it says.

## Why the audit log is separate from Temporal

Temporal history is an execution record. The audit log is compliance evidence: append-only,
hash-chained, replayable, and readable by someone who has never heard of Temporal. Keeping
them separate means the compliance artefact does not depend on which orchestrator I picked.

Duplicate entries would come from an activity that wrote its event and then failed before
acknowledging, so Temporal retried it. The write is keyed on case, step and event type, and
a retry returns the existing hash instead of appending again.

## Why the explorer talks to FastAPI instead of Neo4j directly

The obvious approach with neovis.js is to give the browser the database connection. That
means shipping database credentials to the client. Serving graph JSON from FastAPI instead
keeps credentials server-side, and it let me add a fallback that reads from the derived JSON
files so the explorer works even when Neo4j is not running.

## What breaks at 10,000 cases a day

I have not run this at scale, so this is reasoning rather than measurement.

First, activity fan-out against a single worker. Fix: partition workers by task queue and
scale out.

Second, the audit log append, which currently reads the whole file to find the previous
hash. That is fine at a few hundred events and quadratic beyond it. Fix: keep the chain head
in memory or Redis with periodic checkpointing, and shard by case prefix with a chain per
shard.

Third, retrieval latency per component. The clause corpus barely changes, so a warm
embedding cache would serve almost every case.

After those, Neo4j read replicas for the graph expansion queries.
