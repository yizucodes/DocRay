"""
Rot scoring — scores an article 0-100 for staleness using an LLM-as-judge.

Returns JSON with: rot_score, risk_level, confidence, top_issues, recommended_action.
"""

import json
import requests

from config import GMI_API_KEY, GMI_BASE_URL, GMI_MODEL

ROT_SCORE_PROMPT = """\
You are a knowledge-quality auditor. Today's date is {today}.

Given an article, evaluate whether it contains outdated, internally inconsistent, \
or factually questionable information.

IMPORTANT: Evaluate the article on its own terms. If it reports on events from \
the current year ({year}), treat those claims as potentially valid — do NOT flag \
them as "future" or "speculative" simply because they are recent. Focus on:
  - Internal contradictions (numbers don't add up, conflicting claims)
  - Outdated information (references events long past as current)
  - Factual errors (wrong names, impossible statistics, logical impossibilities)
  - Stale context (article references "upcoming" events that have already passed)

Score the article from 0 to 100:
  0  = internally consistent and appears current
  100 = contains clear factual errors or severely outdated information

Return ONLY valid JSON (no markdown fences) with this exact schema:
{{
  "rot_score": <int 0-100>,
  "risk_level": "green" | "yellow" | "red",
  "confidence": <float 0.0-1.0>,
  "top_issues": ["<issue 1>", ...],
  "recommended_action": "<string>"
}}

Rules for risk_level:
  green  = rot_score 0-30
  yellow = rot_score 31-60
  red    = rot_score 61-100

If the article appears internally consistent and current, return a low score with \
an empty top_issues list.

ARTICLE:
{article_text}
"""


def score_article(article_text: str) -> dict:
    """Score a single article for staleness. Returns parsed JSON dict."""
    from datetime import date

    today = date.today()
    prompt = ROT_SCORE_PROMPT.format(
        article_text=article_text,
        today=today.isoformat(),
        year=today.year,
    )

    resp = requests.post(
        f"{GMI_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {GMI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GMI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 512,
        },
        timeout=60,
    )
    resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"].strip()
    # Strip markdown fences if present
    if content.startswith("```"):
        content = content.split("\n", 1)[1]
        content = content.rsplit("```", 1)[0]
    return json.loads(content)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python rot_score.py '<article text or path to .txt file>'")
        sys.exit(1)

    arg = sys.argv[1]
    # If arg looks like a file path, read it
    from pathlib import Path
    p = Path(arg)
    if p.is_file():
        text = p.read_text()
    else:
        text = arg

    result = score_article(text)
    print(json.dumps(result, indent=2))
