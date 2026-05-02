"""
HydraDB pipeline validation — ESPN NBA news
Requires: pip install -r requirements.txt
Loads config from project-root .env (see .env.example).
"""

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from hydra_db import HydraDB

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v or not str(v).strip():
        raise EnvironmentError(f"{name} must be set in .env or the environment.")
    return v.strip()


def _resolved_knowledge_path() -> Path:
    rel = os.environ.get("HYDRADB_KNOWLEDGE_JSON", "nba_news.json").strip()
    p = PROJECT_ROOT / rel
    return p.expanduser().resolve()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TENANT_ID = os.environ.get("HYDRADB_TENANT_ID", "espn-corpus").strip()
JSON_FILE_PATH = _resolved_knowledge_path()
JSON_FILE = str(JSON_FILE_PATH)
POLL_SECS = float(os.environ.get("HYDRADB_POLL_SECONDS", "2"))
RECALL_QUERY = os.environ.get(
    "HYDRADB_RECALL_QUERY", "NBA playoff recap"
).strip()

# ---------------------------------------------------------------------------
# Auth & client
# ---------------------------------------------------------------------------

API_KEY = _require_env("HYDRADB_API_KEY")
client = HydraDB(token=API_KEY)


# ---------------------------------------------------------------------------
# Step 1 — Create tenant
# ---------------------------------------------------------------------------

def create_tenant():
    print("\n========== STEP 1: Create Tenant ==========")
    try:
        response = client.tenant.create(tenant_id=TENANT_ID)
        print(f"[CREATE_TENANT] Success: {response}")
    except Exception as e:
        msg = str(e).lower()
        if "already exists" in msg or "conflict" in msg or "duplicate" in msg:
            print(f"[CREATE_TENANT] Tenant already exists — continuing. ({e})")
        else:
            print(f"[CREATE_TENANT] ERROR: {e}")
            raise


# ---------------------------------------------------------------------------
# Step 2 — Poll infra status until all systems are up
# ---------------------------------------------------------------------------

def wait_for_provisioned():
    """
    InfraStatusResponse.infra has:
      scheduler_status: bool
      graph_status:     bool
      vectorstore_status: list  (non-empty when ready)
    All three truthy => provisioned.
    """
    print("\n========== STEP 2: Poll Infra Status ==========")
    attempt = 0
    while True:
        attempt += 1
        print(f"[POLL_INFRA] Attempt #{attempt} …")
        try:
            resp = client.tenant.get_infra_status(tenant_id=TENANT_ID)
            infra = resp.infra
            print(
                f"[POLL_INFRA] scheduler_status={infra.scheduler_status} "
                f"graph_status={infra.graph_status} "
                f"vectorstore_status={infra.vectorstore_status}"
            )
            if infra.scheduler_status and infra.graph_status and infra.vectorstore_status:
                print("[POLL_INFRA] Tenant fully provisioned. Continuing.")
                return
        except Exception as e:
            print(f"[POLL_INFRA] ERROR (will retry): {e}")

        print(f"[POLL_INFRA] Not ready yet — waiting {POLL_SECS}s …")
        time.sleep(POLL_SECS)


# ---------------------------------------------------------------------------
# Step 3 — Upload knowledge file
# ---------------------------------------------------------------------------

def upload_knowledge():
    """
    upload.knowledge(files=[...]) accepts a list of file-like objects /
    (filename, bytes, content-type) tuples.
    Returns SourceUploadResponse with .results: list[SourceUploadResultItem]
      each item has .source_id and .status.
    """
    print("\n========== STEP 3: Upload Knowledge ==========")
    print(f"[UPLOAD] File: {JSON_FILE}")
    upload_name = JSON_FILE_PATH.name
    try:
        with open(JSON_FILE_PATH, "rb") as fh:
            file_bytes = fh.read()

        response = client.upload.knowledge(
            tenant_id=TENANT_ID,
            files=[(upload_name, file_bytes, "application/json")],
        )

        print(f"[UPLOAD] success={response.success}  message={response.message}")
        print(
            f"[UPLOAD] success_count={response.success_count} "
            f"failed_count={response.failed_count}"
        )

        source_ids = []
        for item in (response.results or []):
            print(
                f"[UPLOAD]   source_id={item.source_id}  status={item.status} "
                f"error={item.error}"
            )
            source_ids.append(item.source_id)

        if not source_ids:
            raise RuntimeError("Upload returned no source IDs — cannot poll processing.")

        print(f"[UPLOAD] Collected source IDs: {source_ids}")
        return source_ids

    except Exception as e:
        print(f"[UPLOAD] ERROR: {e}")
        raise


# ---------------------------------------------------------------------------
# Step 4 — Poll processing status until all files are completed
# ---------------------------------------------------------------------------

DONE_STATUSES = {"completed", "success"}
FAILED_STATUSES = {"errored", "failed"}


def wait_for_processing(source_ids):
    """
    verify_processing returns BatchProcessingStatus with
    .statuses: list[ProcessingStatus]
      each has .file_id and .indexing_status
        ('queued' | 'processing' | 'completed' | 'errored' |
         'graph_creation' | 'success')
    """
    print("\n========== STEP 4: Poll Processing Status ==========")
    attempt = 0
    while True:
        attempt += 1
        print(f"[POLL_PROCESSING] Attempt #{attempt} …")
        try:
            resp = client.upload.verify_processing(
                tenant_id=TENANT_ID,
                file_ids=source_ids,
            )

            all_done = True
            for ps in resp.statuses:
                status = (ps.indexing_status or "").lower()
                print(
                    f"[POLL_PROCESSING]   file_id={ps.file_id} "
                    f"indexing_status={ps.indexing_status} "
                    f"success={ps.success} message={ps.message}"
                )
                if status in FAILED_STATUSES:
                    raise RuntimeError(
                        f"File {ps.file_id} failed processing: "
                        f"{ps.error_code} — {ps.message}"
                    )
                if status not in DONE_STATUSES:
                    all_done = False

            if all_done and resp.statuses:
                print("[POLL_PROCESSING] All files processed. Continuing.")
                return

        except RuntimeError:
            raise
        except Exception as e:
            print(f"[POLL_PROCESSING] ERROR (will retry): {e}")

        print(f"[POLL_PROCESSING] Not done yet — waiting {POLL_SECS}s …")
        time.sleep(POLL_SECS)


# ---------------------------------------------------------------------------
# Step 5 — Full recall query
# ---------------------------------------------------------------------------

def run_recall():
    """
    full_recall returns RetrievalResult with
    .chunks: list[VectorStoreChunk]
      each has .chunk_content, .source_title, .relevancy_score, .source_id
    """
    print("\n========== STEP 5: Full Recall Query ==========")
    print(f"[RECALL] Query: {RECALL_QUERY!r}")
    try:
        result = client.recall.full_recall(
            tenant_id=TENANT_ID,
            query=RECALL_QUERY,
            max_results=5,
        )

        chunks = result.chunks or []
        print(f"\n========== RECALL RESULTS ({len(chunks)} chunk(s)) ==========")

        if not chunks:
            print("(No chunks returned.)")
        else:
            for i, chunk in enumerate(chunks, start=1):
                print(
                    f"\n--- Chunk {i} "
                    f"| title: {chunk.source_title or '(no title)'} "
                    f"| score: {chunk.relevancy_score} "
                    f"| source_id: {chunk.source_id} ---"
                )
                print(chunk.chunk_content)

        return chunks

    except Exception as e:
        print(f"[RECALL] ERROR: {e}")
        raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== HydraDB Pipeline Validation ===")
    print(f"Root   : {PROJECT_ROOT}")
    print(f"Tenant : {TENANT_ID}")
    print(f"File   : {JSON_FILE}")
    print(f"Time   : {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")

    if not JSON_FILE_PATH.is_file():
        raise FileNotFoundError(
            f"Knowledge file not found: {JSON_FILE_PATH} "
            f"(set HYDRADB_KNOWLEDGE_JSON in .env, path relative to project root)"
        )

    create_tenant()
    wait_for_provisioned()
    source_ids = upload_knowledge()
    wait_for_processing(source_ids)
    run_recall()

    print("\n=== Pipeline completed successfully ===")


if __name__ == "__main__":
    main()
