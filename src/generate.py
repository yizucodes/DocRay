"""
Content generation — retrieves style exemplars from HydraDB and generates
a new article in the same voice using GMI Cloud.

Pulls from both the main corpus tenant AND the feedback tenant (edited-outputs)
so the system learns from user corrections over time.
"""

import json
import requests

from hydra_db import HydraDB
from config import (
    HYDRADB_API_KEY,
    HYDRADB_TENANT_ID,
    GMI_API_KEY,
    GMI_BASE_URL,
    GMI_MODEL,
)
from feedback import retrieve_feedback

client = HydraDB(token=HYDRADB_API_KEY)

GENERATION_PROMPT = """\
You are a sports journalist writing for a major outlet like ESPN. \
Your job is to write a new article about the topic provided, matching the \
voice, tone, sentence structure, and journalistic style of the example articles below.

STYLE EXAMPLES (use these as voice/tone reference — do NOT copy their facts):
---
{examples}
---
{feedback_section}
Write a new article about the following topic. Match the style above precisely — \
same kind of leads, same sentence rhythm, same use of quotes and statistics, same \
level of detail. The article should be 3-5 paragraphs.

Important guidelines:
- Ground every claim in the facts from the style examples. You may synthesize \
and analyze those facts, but do NOT invent new statistics, fabricate quotes, \
or present speculation as established fact.
- Write in the present analytical voice ("the series has shown…", "this matchup \
highlights…") rather than fabricating events that haven't happened.
- If the topic is forward-looking, frame the article as analysis and projection, \
not as reporting on events that occurred.

TOPIC: {topic}
"""


def retrieve_exemplars(topic: str, max_results: int = 5) -> list[dict]:
    """Retrieve top-N similar articles from HydraDB as style exemplars."""
    result = client.recall.full_recall(
        tenant_id=HYDRADB_TENANT_ID,
        query=topic,
        max_results=max_results,
    )
    chunks = result.chunks or []
    return [
        {
            "title": c.source_title or "(untitled)",
            "content": c.chunk_content,
            "score": c.relevancy_score,
        }
        for c in chunks
    ]


def generate_article(
    topic: str,
    exemplars: list[dict] | None = None,
    original_article: str | None = None,
) -> str:
    """Generate a new article about `topic` in the style of retrieved exemplars.

    Retrieves from both the main corpus AND the feedback tenant so the system
    incorporates user corrections.

    If `original_article` is provided, the model treats it as factual reference
    input and is instructed to preserve supported claims, reframe unsupported
    ones, and avoid inventing new facts.
    """
    if exemplars is None:
        exemplars = retrieve_exemplars(topic)

    examples_text = "\n\n".join(
        f"### {ex['title']}\n{ex['content']}" for ex in exemplars
    )

    # Pull from feedback tenant (edited-outputs) — gracefully empty if no edits yet
    feedback_chunks = retrieve_feedback(topic, max_results=3)
    if feedback_chunks:
        feedback_text = "\n\n".join(
            f"### {fb['title']}\n{fb['content']}" for fb in feedback_chunks
        )
        feedback_section = (
            "\nUSER-CORRECTED EXAMPLES (these are prior articles that a human editor "
            "revised — weight their style and corrections heavily):\n---\n"
            f"{feedback_text}\n---\n\n"
        )
    else:
        feedback_section = ""

    # If regenerating from an existing article, anchor the model to its facts
    if original_article:
        feedback_section += (
            "\nORIGINAL ARTICLE (treat as factual reference input):\n---\n"
            f"{original_article}\n---\n\n"
            "REGENERATION RULES:\n"
            "- Preserve claims from the original article that are supported by the style examples.\n"
            "- Reframe any unsupported or speculative claims as analysis or projection.\n"
            "- Do NOT invent new facts, quotes, or statistics not present in the original or examples.\n\n"
        )

    prompt = GENERATION_PROMPT.format(
        examples=examples_text,
        feedback_section=feedback_section,
        topic=topic,
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
            "temperature": 0.7,
            "max_tokens": 1500,
        },
        timeout=90,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    topic = sys.argv[1] if len(sys.argv) > 1 else "NBA draft prospect rankings 2026"
    print(f"\n=== Retrieving style exemplars for: {topic!r} ===\n")
    exemplars = retrieve_exemplars(topic)
    for i, ex in enumerate(exemplars, 1):
        print(f"  [{i}] {ex['title']} (score: {ex['score']})")

    print(f"\n=== Generating article ===\n")
    article = generate_article(topic, exemplars)
    print(article)
