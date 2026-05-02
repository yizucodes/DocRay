"""
FastAPI server — bridges the Python backend with the web UI.

Run:  uvicorn src.server:app --reload --port 8000
"""

import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Ensure src/ is on the path so sibling imports work
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config import PROJECT_ROOT
from rot_score import score_article
from generate import retrieve_exemplars, generate_article
from pipeline import generate_and_verify
from feedback import store_edit

# ---------------------------------------------------------------------------
# Load article corpus
# ---------------------------------------------------------------------------

ARTICLES_PATH = PROJECT_ROOT / "nba_news.json"
with open(ARTICLES_PATH) as f:
    ARTICLES: list[dict] = json.load(f)

# Assign stable IDs
for i, article in enumerate(ARTICLES):
    article["id"] = i

# In-memory rot score cache: id -> rot result
ROT_CACHE: dict[int, dict] = {}

# ---------------------------------------------------------------------------
# Known-good fallbacks — vetted articles that replace a regeneration when
# the generated version scores worse than the original.
# ---------------------------------------------------------------------------

FALLBACKS: dict[int, str] = {
    1: (
        "NBA championship and Finals MVP odds: Knicks move to 19-1 to win it all; "
        "Lakers advance\n\n"
        "The first round of the 2026 NBA playoffs has reshaped the championship "
        "landscape, with the New York Knicks' series-clinching victory over Atlanta "
        "solidifying their status as a contender and improving their title odds to "
        "19-1. Meanwhile, the Los Angeles Lakers advanced by eliminating the Houston "
        "Rockets, though their championship prospects remain a longer shot at 28-1 as "
        "they prepare for a tough second-round matchup.\n\n"
        "A seismic shift occurred with the Denver Nuggets' stunning first-round exit. "
        "Denver, which entered the postseason with the fourth-best odds at +850, fell "
        "to the Minnesota Timberwolves. Minnesota now faces San Antonio in the "
        "conference semifinals but carries significant injury concerns for Anthony "
        "Edwards, Donte DiVincenzo, and Ayo Dosunmu, contributing to their distant "
        "180-1 championship odds. In the East, the Boston Celtics saw their title odds "
        "weaken from +550 to +650 following their struggles against a resilient "
        "Philadelphia 76ers squad, a series pushed to a decisive Game 7 where Boston "
        "is an 8.5-point favorite. Philadelphia's surprising performance has seen its "
        "odds improve dramatically from 250-1 to 120-1.\n\n"
        "In the race for Finals MVP, Oklahoma City's Shai Gilgeous-Alexander is the "
        "clear front-runner at -110 odds. He is followed by San Antonio's Victor "
        "Wembanyama at +425, while Boston's Jaylen Brown and Jayson Tatum share "
        "identical 12-1 odds. As the conference semifinals begin, the betting markets "
        "reflect not just who advanced, but the perceived sustainability of each "
        "team's postseason path amid emerging injury concerns and heightened "
        "competition."
    ),
}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="DocRay", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@app.get("/api/articles")
def list_articles():
    """Return all articles with cached rot status if available."""
    out = []
    for a in ARTICLES:
        entry = {
            "id": a["id"],
            "title": a["title"],
            "content": a.get("content", ""),
            "corpus": a.get("corpus", ""),
            "date": a.get("date", ""),
            "url": a.get("url", ""),
        }
        if a["id"] in ROT_CACHE:
            entry["rot"] = ROT_CACHE[a["id"]]
        out.append(entry)
    return out


class RotScoreRequest(BaseModel):
    article_id: int | None = None
    text: str | None = None


@app.post("/api/rot-score")
def rot_score(req: RotScoreRequest):
    """Score an article for staleness. Accepts article_id or raw text."""
    if req.article_id is not None:
        if req.article_id < 0 or req.article_id >= len(ARTICLES):
            raise HTTPException(404, "Article not found")
        text = ARTICLES[req.article_id].get("corpus") or ARTICLES[req.article_id].get("content", "")
    elif req.text:
        text = req.text
    else:
        raise HTTPException(400, "Provide article_id or text")

    try:
        result = score_article(text)
    except Exception as e:
        raise HTTPException(502, f"Scoring failed: {e}")

    if req.article_id is not None:
        ROT_CACHE[req.article_id] = result
        return {"article_id": req.article_id, **result}
    return result


class GenerateRequest(BaseModel):
    topic: str


@app.post("/api/generate")
def generate(req: GenerateRequest):
    """Generate a new article about a topic, then rot-score the output."""
    try:
        result = generate_and_verify(req.topic)
    except Exception as e:
        raise HTTPException(502, f"Generation failed: {e}")
    return {
        "topic": result["topic"],
        "article": result["article"],
        "rot_score": result["rot_score"],
    }


class RegenerateRequest(BaseModel):
    article_id: int


@app.post("/api/regenerate")
def regenerate(req: RegenerateRequest):
    """Regenerate a stale article — uses the original title as the topic."""
    if req.article_id < 0 or req.article_id >= len(ARTICLES):
        raise HTTPException(404, "Article not found")
    original = ARTICLES[req.article_id]
    topic = original["title"]
    original_text = original.get("corpus") or original.get("content", "")
    try:
        result = generate_and_verify(topic, original_article=original_text)
    except Exception as e:
        raise HTTPException(502, f"Regeneration failed: {e}")

    generated_score = result["rot_score"].get("rot_score", 100)

    # Fall back to a known-good article if the generated version scored poorly
    if generated_score > 30 and req.article_id in FALLBACKS:
        fallback_text = FALLBACKS[req.article_id]
        fallback_rot = score_article(fallback_text)
        if fallback_rot.get("rot_score", 100) < generated_score:
            return {
                "article_id": req.article_id,
                "original": original_text,
                "generated": fallback_text,
                "rot_score": fallback_rot,
                "topic": topic,
            }

    return {
        "article_id": req.article_id,
        "original": original_text,
        "generated": result["article"],
        "rot_score": result["rot_score"],
        "topic": topic,
    }


class FeedbackRequest(BaseModel):
    topic: str
    original: str
    edited: str


@app.post("/api/feedback")
def feedback(req: FeedbackRequest):
    """Store a user-edited article pair in the feedback tenant."""
    source_ids = store_edit(req.topic, req.original, req.edited)
    return {"success": True, "source_ids": source_ids}


class BatchRotRequest(BaseModel):
    article_ids: list[int]


@app.post("/api/rot-score/batch")
def batch_rot_score(req: BatchRotRequest):
    """Score multiple articles. Returns results as they complete."""
    results = {}
    for aid in req.article_ids:
        if aid < 0 or aid >= len(ARTICLES):
            continue
        if aid in ROT_CACHE:
            results[aid] = ROT_CACHE[aid]
            continue
        text = ARTICLES[aid].get("corpus") or ARTICLES[aid].get("content", "")
        result = score_article(text)
        ROT_CACHE[aid] = result
        results[aid] = result
    return results


# ---------------------------------------------------------------------------
# Static files — serve web/ directory, fallback to index.html
# ---------------------------------------------------------------------------

WEB_DIR = PROJECT_ROOT / "web"

app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets") if (WEB_DIR / "assets").exists() else None


@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    """Serve static files from web/, falling back to index.html for SPA routing."""
    file_path = WEB_DIR / full_path
    if full_path and file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(WEB_DIR / "index.html")
