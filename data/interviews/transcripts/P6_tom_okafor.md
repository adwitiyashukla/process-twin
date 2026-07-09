# Interview — Tom Okafor, Ops Team Lead (SYNTHETIC)

*Synthetic transcript. Persona P6, tenure 9 years. Generated per data/interviews/SYNTHETIC.md.*

**Interviewer:** Walk me through a standard onboarding as a process map.

**Tom:** Intake, identifiers, then — in my shop — the sanctions and PEP screen runs first, before document verification. Yes, the written flow implies verify-then-screen. I resequenced it two years ago: screening is thirty seconds of compute, document verification is half an hour of human. Run the screen first and the eight percent of cases that hit a list fail fast, before we've burned analyst time. Same controls, same evidence, better order. I'd defend that sequencing to anyone, and I've offered to get the manual updated to match — that offer is still in someone's inbox.

**Interviewer:** What does the manual not tell you?

**Tom:** How work actually queues. The renewal-receipt pattern, for instance: expired passport plus official renewal receipt gets accepted with a 30-day follow-up task — my team owns that follow-up queue, we clear it weekly, completion rate's high. The manual has no idea this queue exists. It's the most organized invisible process in the building.

**Interviewer:** Which written steps get skipped in practice, and why?

**Tom:** The phone callback on small accounts. Below $10k expected activity the reps mostly skip the callback, and I'll be honest with you — as triage, it's rational. Callback completion on small accounts was running under forty percent anyway because customers don't answer unknown numbers; the step was already failing silently. The difference between me and the floor is that I think the answer is to *change the written rule* to a documented risk threshold, not to quietly not do it. Right now we have the worst of both: a rule nobody follows and a practice nobody wrote down.

**Interviewer:** Describe a case that went wrong.

**Tom:** A rework loop, my personal nemesis. Document request, customer responds, new document triggers a fresh review cycle, which triggers a new document request. Four loops, twenty-two days, for a case that any senior would have cleared in one pass with a phone call. No control failed — we just organized the work badly. I now cap loops at two before it goes to a senior.

**Interviewer:** When do you escalate?

**Tom:** Queue-level, mostly: aging cases, repeat-touch cases, anything where two teams each think the other owns the next step. Individual case risk goes up through the analysts; I escalate when the *process* is the risk.

**Interviewer:** Which rules do you apply more strictly than written?

**Tom:** SLAs. The written standard gives generous timelines; my dashboards run tighter ones, because a KYC file that ages past two weeks starts rotting — customers vanish, documents expire mid-review, everything gets harder.

**Interviewer:** Anything else you'd change?

**Tom:** Kill the duplicate data entry between intake and the case system — that's a tooling gripe, not a control gap. And write down the three or four floor practices everyone already follows. An unwritten process that works is still a liability; it just hasn't invoiced us yet.
