"""
Phase 3 pipeline — generate an article and verify it scores healthy.

Usage:
    python pipeline.py "Lakers offseason trade rumors"
    python pipeline.py  # runs 3 default test topics
"""

import json
import sys

from generate import retrieve_exemplars, generate_article
from rot_score import score_article


MAX_RETRIES = 3
GREEN_THRESHOLD = 30


def generate_and_verify(
    topic: str,
    original_article: str | None = None,
    max_retries: int = MAX_RETRIES,
) -> dict:
    """Generate an article, rot-score it, and retry up to `max_retries` times
    if the score is not green. Returns the best-scoring result."""
    print(f"\n{'='*60}")
    print(f"TOPIC: {topic}")
    print(f"{'='*60}")

    # Step 1: retrieve exemplars (once — reused across retries)
    print("\n[1] Retrieving style exemplars from HydraDB …")
    exemplars = retrieve_exemplars(topic)
    for i, ex in enumerate(exemplars, 1):
        print(f"  [{i}] {ex['title']} (score: {ex['score']})")

    best: dict | None = None

    for attempt in range(1, max_retries + 1):
        print(f"\n[2] Generating article (attempt {attempt}/{max_retries}) …")
        article = generate_article(topic, exemplars, original_article=original_article)
        print(f"\n--- Generated Article ---\n{article}\n")

        print(f"[3] Running rot score …")
        rot = score_article(article)
        score = rot.get("rot_score", 100)
        status = rot.get("risk_level", "unknown").upper()
        print(f"\n--- Rot Score ---")
        print(json.dumps(rot, indent=2))

        result = {"topic": topic, "article": article, "rot_score": rot}

        # Track the best attempt so far
        if best is None or score < best["rot_score"].get("rot_score", 100):
            best = result

        if score <= GREEN_THRESHOLD:
            print(f"\n✓ PASS — Healthy on attempt {attempt} (score={score}, status={status})")
            return result

        print(f"\n✗ Attempt {attempt} scored {status} (score={score})")
        if attempt < max_retries:
            print("  Retrying …")

    print(f"\n⚠ Best result after {max_retries} attempts: "
          f"score={best['rot_score'].get('rot_score', '?')} "
          f"({best['rot_score'].get('risk_level', '?').upper()})")
    return best


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

TEST_TOPICS = [
    "How the 2026 NBA playoffs first round has reshaped championship odds",
    "Impact of the new NBA in-season tournament on team strategies",
    "Victor Wembanyama's dominance in the 2026 NBA playoffs",
]


def main():
    if len(sys.argv) > 1:
        topics = [sys.argv[1]]
    else:
        print("No topic provided — running 3 test topics.\n")
        topics = TEST_TOPICS

    results = []
    for topic in topics:
        result = generate_and_verify(topic)
        results.append(result)

    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for r in results:
        rot = r["rot_score"]
        status = rot.get("risk_level", "?")
        score = rot.get("rot_score", "?")
        icon = "✓" if status == "green" else "✗"
        print(f"  {icon} [{status.upper():6s} {score:>3}] {r['topic']}")


if __name__ == "__main__":
    main()
