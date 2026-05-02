# Hackathon Build Plan
## Knowledge Rot Detector + Style-Matched Content Generator

---

## Phase 1: Data (30 minutes)

1. Download the Reuters dataset from Kaggle — you need a free account
2. Open the CSV, pick one category column (business or finance), filter to just that category
3. Take 150 articles — not more, not less
4. Keep only two columns: the article title and the article body text
5. Manually pick 3 of those 150 articles and edit one fact in each — wrong number, outdated claim, anything clearly incorrect. Label these your "stale" docs. These are your rot demo articles.

---

## Phase 2: Infrastructure (30 minutes)
> HydraDB handles embedding and indexing automatically — no need to generate embeddings yourself.

6. Create a HydraDB account and get your API key from hydradb.com
7. Create a tenant by calling `POST /tenants/create` with a tenant ID like `reuters-corpus`
8. Poll `GET /tenants/infra/status?tenant_id=reuters-corpus` until the status returns provisioned — do not ingest until this is complete
9. Upload your 150 articles as TXT files using `POST /ingestion/upload_knowledge` — HydraDB automatically handles embedding and indexing for you
10. Verify ingestion is complete by calling `GET /ingestion/verify_processing` and waiting for status to show "completed"
11. Run a test retrieval using `POST /recall/full_recall` with a plain English query like "business earnings report" — confirm you get back relevant chunks before building anything on top

---


## Phase 3: Content Generation (45 minutes)

16. Write a generation prompt (using GMI Cloud) that takes a user topic as input, retrieves the top 5 most similar articles from HydraDB using `full_recall`, and instructs the LLM to write a new article in the same voice using those 5 as style examples
17. Test it with 3 different topic prompts and read the output — does it sound like ESPN? If yes, move on. If no, adjust the prompt to emphasize style matching more explicitly
18. Add one more step to the generation flow: after generating, automatically run the rot score prompt on the new output to confirm it scores healthy (green)



---

## Phase 4: Feedback Loop (30 minutes)

19. Create a second HydraDB tenant called `edited-outputs`
20. Every time a user edits a generated article, store both the original generated version and the edited version as a pair using `POST /ingestion/upload_knowledge`
21. When generating future articles, retrieve from both tenants — `espn-corpus` AND `edited-outputs` — so the system learns from corrections over time
22. This is the feature that makes the product defensible. Make sure you can point to this in the demo and say "it learns from every edit"

---

## Phase 5: UI (45 minutes)

23. Build a single page with three sections: a document dashboard, a rot score panel, and a generation panel
24. The dashboard shows all 150 articles as cards — green for healthy, red for stale. The 3 corrupted articles should appear red immediately on load
25. Clicking a red card opens the rot score panel showing the score, the flagged sentence highlighted, and a "Regenerate" button
26. Clicking Regenerate triggers the generation flow and shows the new article next to the original side by side
27. Add a simple text field at the bottom: "Generate new article about ___" — this is your forward-looking demo moment

---

## Phase 6 Demo Prep (30 minutes)

28. Rehearse the exact sequence: dashboard → click red card → show rot score → hit regenerate → show side by side → type new topic → generate
29. Make sure every step takes under 10 seconds — if anything is slow, add a loading state so silence does not kill the energy
30. Prepare one sentence for each transition so you are narrating the story, not the UI
31. Have a backup: screenshot the working demo in case anything breaks live



## V2: Rot Scoring (45 minutes)

12. Write a single LLM prompt (using GMI Cloud) that takes one article and asks the model to score it 0–100 for staleness, identify the specific problematic sentence, and return a JSON object with: `rot_score`, `risk_level`, `confidence`, `top_issues`, and `recommended_action`
13. Run that prompt against your 3 manually corrupted articles — confirm it flags them correctly with high rot scores
14. Run it against 5 clean articles — confirm they score low
15. That is your rot scoring pipeline working end to end

---
---

## Stack Summary

| Layer | Tool | Purpose |
|-------|------|---------|
| Corpus storage + retrieval | HydraDB | Auto-embeds, indexes, and retrieves articles |
| Rot scoring | GMI Cloud LLM | LLM-as-judge scores each doc 0–100 |
| Content generation | GMI Cloud LLM | Generates new articles using retrieved style exemplars |
| Feedback loop | HydraDB (second tenant) | Stores edited outputs to improve future generation |
| UI | Single page app | Dashboard + rot panel + generation panel |

---

## Total Estimated Time: 4.5 hours

That leaves buffer for debugging, which you will need.

---

## Key Demo Script (3 minutes)

**Act 1 — The problem (30s):** Show a stale article. Say: *"This is what enterprise knowledge looks like. Accurate yesterday, wrong today. And your AI is reading it right now."*

**Act 2 — The diagnosis (60s):** Run the rot score. Dashboard turns red. System explains why in plain English.

**Act 3 — The fix (60s):** Hit Regenerate. Show original vs regenerated side by side. New one sounds like Reuters.

**Act 4 — The hook (30s):** Say: *"Every enterprise has thousands of docs like this. We find them, score them, and rewrite them automatically — in your brand voice."*