# Interview - Priya Raghavan, Senior KYC Analyst (SYNTHETIC)

*Synthetic transcript. Persona P1, tenure 8 years. Generated per data/interviews/SYNTHETIC.md.*

**Interviewer:** Walk me through a standard onboarding, start to finish.

**Priya:** Application comes in, we collect the core identifiers - name, date of birth, address, ID number - same four the regulation names. Then, and I know the manual sort of implies otherwise, my team runs the sanctions and PEP screening first, before document verification. We call it screening first. If someone's going to hit a list, I want to know before I've spent forty minutes on their documents. After the screen it's documentary verification, jurisdiction risk, beneficial ownership if it's an entity, risk rating, and the decision. For entities we collect the certification form for owners at twenty-five percent or more - that part's straight from the rule.

**Interviewer:** What does the manual not tell you?

**Priya:** Where the bodies are buried with ownership percentages. The rule says 25 percent, fine. But if the entity's incorporated somewhere like Kavastan and there's an owner sitting at 22, 23 percent, nobody on my team treats that as a pass. In practice anything at 20 or above in a high-risk jurisdiction gets the full look and usually an EDD referral. I've flagged owners at 21 percent three times this year. The manual doesn't say to do that. We do it anyway, and I'll defend it in any exam.

**Interviewer:** Which rules do you apply more strictly than written?

**Priya:** Utility bills. Policy accepts them up to 90 days old. I stopped accepting anything over 60 days years ago, and the seniors follow the same line - at 75 days half the addresses have gone stale on us, especially renters. So: 60 days, or bring me something fresher. Junior analysts sometimes take the 90 because that's what the page says, which is how the same customer can pass with one analyst and get a document request from another. Not my favorite feature of our process.

**Interviewer:** Describe a case that went wrong.

**Priya:** A transliterated name - originally Cyrillic. The screening tool scored the match against the list entry below threshold because of the spelling variants, so it sailed through as clean. QA caught it on sample review. Since then, when I see a name that's clearly transliterated, I manually widen the match tolerance on the screening tool and re-run it. It's a workaround - the matcher should handle transliteration natively, and I've said so in three feedback tickets. Until then, I loosen the match myself and eat the extra false positives.

**Interviewer:** When do you escalate, and why?

**Priya:** Any list hit that survives my first disposition, any ownership structure I can't draw on one sheet of paper, and anything where the customer's story and the documents disagree. Escalation isn't failure - a clean file that should have been escalated is the thing that ends careers here.

**Interviewer:** Which written steps get skipped in practice?

**Priya:** Not on my cases. Ask the frontline about the phone callback step, though - that one's become a bit theoretical for the small accounts, from what I see in the files.

**Interviewer:** Anything else you'd fix?

**Priya:** The case system loses free-text notes if your session times out mid-save. Twice I've retyped a full beneficial-ownership rationale from memory. That's not a compliance gap, it's just software that hates analysts.
