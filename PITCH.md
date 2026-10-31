# Enterprise Atlas: hackathon pitch

## One-liner

**Enterprise Atlas shows a startup who actually decides inside a 160,000-person enterprise, and proves every line it draws.**

---

## The 3-minute script

**[0:00 – Hook]**
"A startup wants to sell warranty analytics to Mercedes-Benz. Mercedes has about 50,000 people on LinkedIn.
The founder searches *Head of*, finds the most senior name, sends 40 messages, and gets silence.
Not because the product is bad. Because they wrote to the wrong people."

**[0:20 – Problem]**
"Enterprise deals aren't decided by the org chart. They're decided by a buying center:
- someone owns the problem;
- someone sponsors the budget;
- a data lead evaluates;
- IT approves the integration;
- procurement runs the vendor process.

Those people rarely sit in one reporting line. Today, consultants rebuild this map by hand over weeks.
LLM tools do it in seconds and *invent* half of it."

**[0:45 – Demo: decision map]** *(open the Decision map)*
"This is Mercedes-Benz, built today from **real data**:
- **88 real people**, placed into **13 business units, 15 functions and 18 teams**;
- **377 sourced claims**, **111 evidence items** and **17 signals you won't find on LinkedIn**.

On the left is the company. Then the units, ranked by how much of the problem lives there: Mercedes-Benz AG is the target domain, Vans is adjacent, and the rest is low relevance.
Then the teams where the problem lives: Warranty & Goodwill, Field Quality, the After-Sales Data, AI & Analytics team.
On the right is the buying committee, one card per role."

**[1:15 – The 'aha']** *(click the sponsor, open a relationship)*
"Every line has a source, a date and a confidence. Click the sponsor: a Director of Service & Parts and Warranty & Goodwill. We know that from his own headline, seen in three separate searches.
The engine calls him a sponsor *hypothesis*, at 55%, because his seniority sits in the function that owns the problem. A VP of Marketing would never get that label.

Now the part an LLM can't fake. **A job ad tells us the after-sales analytics team doesn't report into the business. It sits inside IT After-Sales, on Databricks and AWS.**
That changes the sales motion: your evaluator is in IT, not in warranty."

**[1:50 – Hidden intelligence]** *(Hidden signals panel)*
"LinkedIn tells you where people sit. Job ads, conference programmes, vendor case studies, industry associations and public tenders tell you what they actually work on. The engine also cleans what it collects:
- it spots profiles that are really alumni, which makes them an introduction route;
- it flags stale 'Daimler AG' and Trucks profiles, since Daimler Truck spun off in 2021;
- it merges the anonymous 'LinkedIn Member' with the same person named in another search."

**[2:15 – Entry paths]** *(Entry paths)*
"Then it tells you *how to get in*. Four routes, each step a real ranked person:
- **Bottom-up:** start with the data lead who would run the pilot.
- **Champion first:** open with someone who already spoke publicly about the topic.
- **Warm intro:** go through a partner or a leadership assistant.
- **Formal route:** register early with the software category manager, so procurement never blocks the yes."

**[2:35 – Why it wins]**
"Three things nobody else combines:
1. **A buying-center ontology, not an org chart.** It's built per problem, because the same person matters for one product and not another.
2. **Provenance as a hard rule.** Each kind of evidence can only prove certain claims. A conference talk can't prove budget ownership, whether a human or an LLM claims it.
3. **A hidden-intelligence layer** from sources a contact database doesn't have.

And it's open: it ships as a **Claude Code skill**. Install it, say *'map the buying center for procurement AI at Siemens'*, and Claude runs the whole pipeline."

**[2:55 – Close]**
"Enterprise Atlas. Stop messaging the most senior person. Start talking to the people who decide."

---

## Slide outline (6 slides)

1. **Title.** "Who actually decides?" Mercedes-Benz decision-map screenshot.
2. **Problem.** The org chart vs the buying center diagram: sponsor, owner, evaluator, IT, procurement. "Influence ≠ hierarchy."
3. **Live demo.** Decision map → sponsor's sources → the IT After-Sales job-ad insight.
4. **How it works.**
   - Pipeline: collectors (LinkedIn via Needle, job ads, events, vendor case studies, associations, TED) → sourced claims with confidence limits per evidence type → org graph + buying-center graph → ranking and entry paths.
   - "Raw data is kept, so the graph can be rebuilt as the parsers improve."
5. **Why us / moat.** Provenance rules, per-problem ontology, hidden-signal sources, analyst curation that survives rebuilds, Claude skill distribution.
6. **Business and ask.**
   - **Customers:** B2B startups selling into the DAX/Fortune 500, plus consultancies and VC platform teams.
   - **Pricing:** priced per account map, then per seat.
   - **Next:** CRM sync, Sales Navigator scale, more countries' tender feeds.

## Numbers to quote (Mercedes-Benz, live build)

| | |
|---|---|
| Real people placed | 88 (80 LinkedIn profiles via Needle, plus speakers and the board) |
| Org structure discovered | 13 business units · 15 functions · 18 teams |
| Sourced claims / evidence | 377 / 111 |
| Off-LinkedIn signals | 17 (10 job ads, 10 event-programme items, 3 vendor claims, association, press) |
| LinkedIn budget used | ~35 searches of a 100/day standard account |
| Anonymous profiles auto-merged with named twins | 2 |

## Judge Q&A prep

- **"Isn't this just scraping LinkedIn?"**
  - LinkedIn data comes through Needle on the user's own connected account, within its limits.
  - LinkedIn only gives the *where*. The value is the buying-center reasoning and the off-LinkedIn signals.
  - The public export withholds names known only from LinkedIn.
- **"How do you avoid hallucinations?"**
  - Every claim needs evidence.
  - Each kind of evidence has a confidence limit and a list of claims it is allowed to make.
  - Role guesses are labelled as hypotheses and capped.
  - The LLM extractor must quote the page word for word.
- **"How accurate are the roles?"**
  - They are hypotheses with their reasons shown.
  - The ranking breaks down into problem fit, role strength, evidence and reachability.
  - An analyst can reject or add claims, and those edits survive rebuilds.
- **"Does it generalize beyond Mercedes?"** Yes. A new company is a JSON file, and a new problem is another JSON file. The skill walks Claude through filling both from official sources.
- **"GDPR?"**
  - The engine never sends outreach.
  - Harvested personal data stays local (git-ignored).
  - Published snapshots are redacted by default.
  - Raw data is kept, so a deletion request can be honoured with a rebuild.
