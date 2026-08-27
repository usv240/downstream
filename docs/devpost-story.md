## Inspiration

A dam's emergency action plan isn't really a document. The part that matters is one page listing who calls whom: a name and a phone number that has to be right at three in the morning.

So I went looking at the public record. The US Army Corps of Engineers' [National Inventory of Dams](https://nid.sec.usace.army.mil/nid/) lists **92,606** dams, and **16,972** of them are classified high hazard, meaning that if one failed, people downstream would likely die. (I measured both numbers against the live NID service on 11 August 2026; they're on the landing page.) High hazard is a statement about consequences, not about condition. It doesn't mean a dam is in bad shape.

What stuck with me was where the facts live. Some are in the federal record. Some are on a drawing from 1958 in a filing cabinet. And some exist only in the owner's head: which gravel road washes out in heavy rain, who actually answers after hours. The owner is often a farmer or a small water district, not an engineer. Keeping that page true isn't anyone's job.

That's the shape of problem an agent should be good at. Most of it is research and reconciliation. A small, irreducible part of it needs a person.

## What it does

Downstream drafts and maintains an emergency action plan *with* the owner rather than for them. The division of labour is the whole design: **it handles everything it can prove from the records, and asks the owner only for what only they can know.**

From a single request, with no further clicks, it:

- resolves the dam's record from the public inventory
- reads a legacy engineering drawing with **Gemini 3.5 Flash on Vertex AI**, and keeps a quote for every fact it extracts
- quarantines anything in that scanned document shaped like an instruction, before the text reaches a model
- notices when two sources disagree (the drawing says the dam is 31 ft, the registry says 28), and raises a targeted question with both sources attached instead of quietly picking one
- drafts every section it has evidence for
- refuses to draw a flood map
- schedules its own follow-ups, then stops and asks the owner the handful of things it isn't allowed to guess

Then it keeps being useful:

**It learns from corrections.** When the owner fixes an answer, the draft rewrites itself and the previous version is kept, with the reason it changed. Nothing is silently overwritten.

**It works when nobody's watching.** Follow-ups are durable records in the database, not timers in a browser tab. Cloud Scheduler wakes the service, and the agent re-checks the draft on its own: how many sections are ready, which questions are still open, whether the height conflict is still unresolved, whether the map is still blocked. You can close the laptop and it still happens.

**It shows its work.** The autonomy receipt isn't a claim. It is counted from the run's stored timeline, and every step records which actor performed it: the agent, or the person. A run of the public demo produces 15 agent steps, 7 owner-authority steps, and 0 clicks needed to keep it going.

**It's a service, not just a screen.** You can self-serve an API key in about a second, with no account and no invitation, and drive the same live agent from another application.

## The part I care most about

The single most useful thing this tool could produce is a flood map, showing which houses go under. It won't produce one.

Simplified inundation mapping has documented conditions ([ASDSO's SIMS guidance](https://www.damsafety.org/sites/default/files/files/EAPWG%20Final%20SIMS.pdf) sets them out): the published method has to be applicable, the jurisdiction has to accept it, and the result has to be checked against a reference map. None of those are established here, so the gate fails closed and the draft says plainly what it did not generate and who needs to do it instead: a qualified engineer.

It would have been easy to generate a plausible-looking polygon. An agent that knows the edge of its own competence is worth more than one that guesses well.

## How we built it

Everything runs on Google Cloud:

- **Cloud Run** hosts the agent (FastAPI, Python, `us-central1`)
- **Vertex AI** runs Gemini 3.5 Flash in the request path for the multimodal drawing read
- **Firestore** holds workspaces, the durable wake ladder, API key digests and quota counters
- **Cloud Scheduler** wakes the service so follow-ups fire with nobody present
- **Secret Manager** supplies the scheduler token and key digests
- **Cloud Trace** collects OpenTelemetry spans for each run

The technology badge on the site isn't a logo wall. It is generated from the running process, so it can only claim a service this deployment actually has wired.

Two sources anchor what the draft is allowed to say. [FEMA P-64](https://www.fema.gov/sites/default/files/2020-08/fema_dam-safety_emergency-action-planning_P-64.pdf) defines what an emergency action plan is for, and [ASDSO's guidance on emergency action planning](https://damsafety.org/dam-owners/emergency-action-planning) describes the notification chain and the owner's role in building it. Sections that rest on published requirements carry the citation and the quoted line; sections that rest on the owner carry that attribution instead. Federal guidance doesn't replace state requirements, and the draft says so.

**On the demo data:** the dam in the public demo is synthetic, and the 1958 drawing is a synthetic period-style drawing. That's deliberate. It keeps the workflow fully testable without making claims about a real owner's compliance. The federal inventory query is live and real, and the API opens workspaces from actual NID identifiers.

## Challenges we ran into

**The conflict was fake at first.** The 28-vs-31 disagreement started life hardcoded in a fixture, which made for a nice demo and proved nothing. Deriving it, by comparing the drawing reading against the registry row, is what turned a scripted walkthrough into an agent. A drawing that *agrees* with the registry now correctly raises no question at all.

**Proving asynchrony is harder than building it.** Arming a reminder and having it fire later is easy to claim and easy to fake. Getting it to fire on the wall clock, inside a four-minute unedited video, without ever running it from the page, meant reasoning about the scheduler's polling interval rather than hoping. Two full rehearsals against the deployed service measured 48.9s and 81.9s from arming to firing; the second would have missed its moment, so the lead time was cut and the reveal was moved later.

**Scanned documents are untrusted input.** A drawing can contain text shaped like an instruction. Anything that looks like one is stripped before the document reaches a model, and identifiers are replaced with pseudonyms at the boundary, so the owner's actual phone number stays in their workspace.

## Accomplishments that we're proud of

The refusal. The receipt that's counted from stored state instead of asserted. And a reminder that fires while you're busy doing something else, stamped with the Cloud Run revision that executed it. It is the one thing in the whole product that a page you are looking at cannot fake.

## What we learned

That the interesting design question isn't "how much can the agent do?" but "where exactly should it stop?" Almost everything good about Downstream came from taking that question seriously: stop at owner knowledge, stop at the flood map, stop and ask when two sources disagree.

And that a system's own vocabulary is invisible to the people it was built to convince. "Durable wakes registered" meant nothing to anyone outside the repository; "Follow-ups it scheduled for itself" means something immediately. Half the work of making this understandable was deleting words.

## What's next for Downstream

Opening workspaces from real NID records at scale, so an owner starts from their own dam rather than a preset. Letting an owner supply an already-approved inundation map, which is the one path that legitimately unlocks the mapping section. And encoding jurisdiction-specific requirements, since a plan that satisfies FEMA's general guidance still has to satisfy a particular state.

The pattern generalises past dams: automate what can be grounded in evidence, ask a human only for their own knowledge or authority, keep corrections, keep working between sessions, and refuse what you cannot justify. But the dam case is the one this actually demonstrates, so it is the only one being claimed.

**Try it:** the public workspace needs no key at all. An API key takes about a second, with no account and no invitation.
