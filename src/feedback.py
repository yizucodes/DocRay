"""
Feedback loop — stores original/edited article pairs in a sub-tenant of the
main HydraDB tenant, so the generation system learns from corrections over time.

Uses a sub-tenant (under espn-corpus) instead of a separate top-level tenant
to stay within HydraDB plan limits.

Phase 4 of PLAN.md (steps 19-22).
"""

import json
import time

from hydra_db import HydraDB
from config import HYDRADB_API_KEY, HYDRADB_TENANT_ID, HYDRADB_FEEDBACK_TENANT_ID

client = HydraDB(token=HYDRADB_API_KEY)

POLL_SECS = 2

# The feedback sub-tenant lives under the main corpus tenant.
# HydraDB sub-tenants share the parent's infrastructure, so no separate
# provisioning is needed — we just upload with a sub_tenant_id.
FEEDBACK_SUB_TENANT = HYDRADB_FEEDBACK_TENANT_ID  # "edited-outputs"


# ---------------------------------------------------------------------------
# Step 20 — Store an original/edited pair
# ---------------------------------------------------------------------------

def store_edit(topic: str, original: str, edited: str):
    """
    Upload a feedback pair to the edited-outputs sub-tenant.

    The pair is stored as a single JSON document containing both versions,
    so the generation system can retrieve the edited version as a style
    reference and understand how the user corrected the original.
    """
    pair = {
        "topic": topic,
        "original": original,
        "edited": edited,
        "type": "feedback_pair",
    }

    filename = f"feedback_{int(time.time())}.json"
    file_bytes = json.dumps(pair, indent=2).encode()

    print(f"[FEEDBACK] Uploading edit pair for topic: {topic!r}")
    resp = client.upload.knowledge(
        tenant_id=HYDRADB_TENANT_ID,
        sub_tenant_id=FEEDBACK_SUB_TENANT,
        files=[(filename, file_bytes, "application/json")],
    )
    print(f"[FEEDBACK] Upload success={resp.success}  message={resp.message}")

    source_ids = [item.source_id for item in (resp.results or [])]
    if not source_ids:
        raise RuntimeError("Feedback upload returned no source IDs.")

    # Wait for processing
    _wait_for_processing(source_ids)
    print(f"[FEEDBACK] Feedback pair stored and indexed.")
    return source_ids


DONE_STATUSES = {"completed", "success"}
FAILED_STATUSES = {"errored", "failed"}


def _wait_for_processing(source_ids: list[str]):
    """Poll until all source IDs are processed."""
    while True:
        try:
            resp = client.upload.verify_processing(
                tenant_id=HYDRADB_TENANT_ID,
                file_ids=source_ids,
            )
            all_done = True
            for ps in resp.statuses:
                status = (ps.indexing_status or "").lower()
                if status in FAILED_STATUSES:
                    raise RuntimeError(f"File {ps.file_id} failed: {ps.message}")
                if status not in DONE_STATUSES:
                    all_done = False
            if all_done and resp.statuses:
                return
        except RuntimeError:
            raise
        except Exception:
            pass
        time.sleep(POLL_SECS)


# ---------------------------------------------------------------------------
# Step 21 — Retrieve from feedback sub-tenant
# ---------------------------------------------------------------------------

def retrieve_feedback(topic: str, max_results: int = 3) -> list[dict]:
    """
    Retrieve relevant edited articles from the feedback sub-tenant.
    Returns empty list if no feedback data exists yet.
    """
    try:
        result = client.recall.full_recall(
            tenant_id=HYDRADB_TENANT_ID,
            sub_tenant_id=FEEDBACK_SUB_TENANT,
            query=topic,
            max_results=max_results,
        )
        chunks = result.chunks or []
        return [
            {
                "title": c.source_title or "(feedback)",
                "content": c.chunk_content,
                "score": c.relevancy_score,
            }
            for c in chunks
        ]
    except Exception as e:
        # Sub-tenant may be empty — degrade gracefully
        print(f"[FEEDBACK] Could not retrieve from feedback sub-tenant: {e}")
        return []


# ---------------------------------------------------------------------------
# CLI — demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        store_edit(
            topic="NBA playoff preview",
            original="The Lakers are expected to dominate the playoffs.",
            edited="The Lakers face a tough second-round matchup after narrowly advancing past Houston in five games.",
        )
        results = retrieve_feedback("Lakers playoffs")
        print(f"\n[FEEDBACK] Retrieved {len(results)} chunk(s) from feedback sub-tenant.")
        for r in results:
            print(f"  - {r['title']} (score: {r['score']})")
            print(f"    {r['content'][:200]}")
    else:
        print("Usage: python feedback.py demo")
