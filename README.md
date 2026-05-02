# DocRay

> **Knowledge Rot Detector + Style-Matched Content Generator**

A system that automatically scans enterprise knowledge bases for stale content, scores every document for rot using an LLM-as-judge, and regenerates flagged articles in your original brand voice—learning from every human correction.

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![HydraDB](https://img.shields.io/badge/HydraDB-Vector_DB-purple.svg)](https://hydradb.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Pipelines](#pipelines)
- [Configuration](#configuration)

---

## Overview

Enterprise knowledge bases decay. Articles that were accurate last quarter now contain wrong statistics, outdated claims, or superseded information. Your AI is reading them right now.

DocRay provides **autonomous knowledge hygiene** through:

1. **Rot Scoring** - LLM-as-judge scores each document 0–100 for staleness
2. **Issue Detection** - Identifies the specific sentences that are wrong and why
3. **Style-Matched Regeneration** - Retrieves healthy docs as voice exemplars, rewrites in your brand tone
4. **Feedback Loop** - Every human edit is stored and used to improve future generation

### The Core Loop

```
┌─────────────────────────────────────────────────────────────────┐
│                      DOCRAY LOOP                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│   │   SCAN   │───▶│  SCORE   │───▶│REGENERATE│───▶│  VERIFY  │ │
│   │ CORPUS   │    │  (0-100) │    │ (LLM+RAG)│    │          │ │
│   └──────────┘    └──────────┘    └──────────┘    └────┬─────┘ │
│        ▲                                               │       │
│        │                    ┌───────────┐              │       │
│        └────────────────────│  FAILED?  │◀─────────────┘       │
│                             └─────┬─────┘                      │
│                                   │ NO                         │
│                                   ▼                            │
│                            ┌───────────┐                       │
│                            │  HEALTHY  │                       │
│                            └───────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                               DOCRAY                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────┐          ┌─────────────────────────────────────┐  │
│  │     FRONTEND        │          │            BACKEND                   │  │
│  │  (Vanilla JS SPA)   │   HTTP   │           (FastAPI)                  │  │
│  │                     │◀────────▶│                                      │  │
│  │  • Article Dashboard│   REST   │  • /api/rot-score endpoint           │  │
│  │  • Rot Score Panel  │          │  • /api/generate endpoint            │  │
│  │  • Generation View  │          │  • /api/feedback endpoint            │  │
│  │  • Edit & Feedback  │          │  • Static file serving               │  │
│  └─────────────────────┘          └─────────────────┬───────────────────┘  │
│                                                     │                       │
│                         ┌───────────────────────────┼───────────────────┐   │
│                         │        ORCHESTRATOR       │                   │   │
│                         │        (pipeline.py)      │                   │   │
│                         │                           ▼                   │   │
│                         │   ┌─────────────────────────────────────┐     │   │
│                         │   │         Generation Pipeline         │     │   │
│                         │   │                                     │     │   │
│                         │   │  • Retrieve exemplars from HydraDB  │     │   │
│                         │   │  • Generate in style via GMI Cloud  │     │   │
│                         │   │  • Auto rot-score the output        │     │   │
│                         │   │  • Retry if output scores unhealthy │     │   │
│                         │   └───────────────┬─────────────────────┘     │   │
│                         │                   │                           │   │
│                         └───────────────────┼───────────────────────────┘   │
│                                             │                               │
│     ┌───────────────────────────────────────┼────────────────────────────┐  │
│     │                   COMPONENT LAYER     │                            │  │
│     │                                       ▼                            │  │
│     │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐    │  │
│     │  │   HydraDB   │  │  GMI Cloud  │  │     Feedback Store       │    │  │
│     │  │   Client    │  │   Client    │  │   (HydraDB tenant 2)     │    │  │
│     │  │             │  │             │  │                          │    │  │
│     │  │ • Auto-embed│  │ • Rot score │  │ • Store edit pairs       │    │  │
│     │  │ • Full recall│ │ • Generate  │  │ • Retrieve corrections   │    │  │
│     │  │ • Multi-     │  │   content  │  │ • Blend with corpus on   │    │  │
│     │  │   tenant    │  │ • Style-    │  │   future generation      │    │  │
│     │  │             │  │   match     │  │                          │    │  │
│     │  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────────┘    │  │
│     │         │                │                    │                    │  │
│     └─────────┼────────────────┼────────────────────┼────────────────────┘  │
│               │                │                    │                       │
└───────────────┼────────────────┼────────────────────┼───────────────────────┘
                │                │                    │
                ▼                ▼                    ▼
        ┌─────────────┐  ┌─────────────┐    ┌─────────────────┐
        │   HydraDB   │  │  GMI Cloud  │    │   HydraDB       │
        │     API     │  │     API     │    │   (feedback      │
        │             │  │             │    │    tenant)       │
        │ Main corpus │  │DeepSeek-V3.2│    │  Edited outputs  │
        │  retrieval  │  │             │    │                  │
        └─────────────┘  └─────────────┘    └─────────────────┘
```

### Regeneration Data Flow

```
┌────────┐     ┌────────┐     ┌──────────┐     ┌─────────┐     ┌─────────┐
│ Client │     │FastAPI │     │ Pipeline │     │ HydraDB │     │GMI Cloud│
└───┬────┘     └───┬────┘     └────┬─────┘     └────┬────┘     └────┬────┘
    │              │               │                │               │
    │  POST /api/regenerate        │                │               │
    │─────────────▶│               │                │               │
    │              │               │                │               │
    │              │  generate()   │                │               │
    │              │──────────────▶│                │               │
    │              │               │                │               │
    │              │               │  full_recall() │               │
    │              │               │───────────────▶│               │
    │              │               │                │               │
    │              │               │  top 5 exemplars               │
    │              │               │◀───────────────│               │
    │              │               │                │               │
    │              │               │          generate_article()    │
    │              │               │───────────────────────────────▶│
    │              │               │                │               │
    │              │               │          new article text      │
    │              │               │◀───────────────────────────────│
    │              │               │                │               │
    │              │               │          rot_score(output)     │
    │              │               │───────────────────────────────▶│
    │              │               │                │               │
    │              │               │  ┌────────────────────────┐   │
    │              │               │  │ RETRY IF SCORE > 30    │   │
    │              │               │  └────────────────────────┘   │
    │              │               │                │               │
    │              │  GenerateResult│               │               │
    │              │◀──────────────│                │               │
    │              │               │                │               │
    │  Response    │               │                │               │
    │◀─────────────│               │                │               │
    │              │               │                │               │
```

---

## Features

### Rot Detection
- **LLM-as-Judge Scoring** - Each article scored 0–100 with confidence level
- **Issue Identification** - Returns the specific claims that are wrong and why
- **Risk Levels** - Green (healthy), yellow (warning), red (stale)
- **Batch Scanning** - Score all 150 articles in a single API call with progress tracking

### Content Generation
- **Style Matching** - Retrieves top 5 most relevant articles as voice exemplars
- **Brand Voice** - Generated content sounds like your corpus, not a chatbot
- **Auto Verification** - Output is rot-scored immediately; retried if unhealthy
- **Topic-First** - Generate new articles from scratch, not just edits

### Feedback Loop
- **Edit Capture** - Store user-edited article pairs in a dedicated HydraDB tenant
- **Blended Retrieval** - Future generation pulls from both the main corpus and edited outputs
- **Continuous Improvement** - The system learns from every correction without fine-tuning
- **Defensible Moat** - Each organization's edited-outputs tenant becomes a proprietary style asset

---

## Quick Start

### Prerequisites

- Python 3.10+
- A [HydraDB](https://hydradb.com) account and API key
- A [GMI Cloud](https://gmi-serving.com) account and API key

### 1. Clone & Setup Environment

```bash
git clone <repo-url>
cd DocRay

# Configure environment
cp .env.example .env
# Edit .env — fill in HYDRADB_API_KEY and GMI_CLOUD_API_KEY
```

### 2. Start Backend

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Initialize Corpus (first run only)

```bash
python scripts/hydra_setup.py
```

This creates the HydraDB tenant, waits for infrastructure provisioning, uploads `nba_news.json`, and runs a verification query.

### 4. Run the Server

```bash
npm run dev
# or: cd src && uvicorn server:app --reload --port 8000
```

### 5. Open Dashboard

Navigate to [http://localhost:8000](http://localhost:8000)

### Quick API Test

```bash
# Health check
curl http://localhost:8000/api/articles

# Rot score a single article
curl -X POST http://localhost:8000/api/rot-score \
  -H "Content-Type: application/json" \
  -d '{"article_id": 5}'

# Generate a new article
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"topic": "Lakers championship prospects"}'
```

---

## API Reference

### REST Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/articles` | GET | List all articles with cached rot status |
| `/api/rot-score` | POST | Score a single article by ID or raw text |
| `/api/rot-score/batch` | POST | Score all articles; returns full results |
| `/api/generate` | POST | Generate a new article on a given topic |
| `/api/regenerate` | POST | Regenerate a stale article using its title as topic |
| `/api/feedback` | POST | Store a user-edited article pair for learning |

### Request/Response Examples

<details>
<summary><strong>POST /api/rot-score</strong></summary>

**Request:**
```json
{
  "article_id": 5
}
```

**Response:**
```json
{
  "rot_score": 65,
  "risk_level": "red",
  "confidence": 0.95,
  "top_issues": [
    "Incorrect player roster — player was traded in February",
    "Championship odds cited are from the 2024 season"
  ],
  "recommended_action": "regenerate"
}
```
</details>

<details>
<summary><strong>POST /api/generate</strong></summary>

**Request:**
```json
{
  "topic": "Lakers championship prospects"
}
```

**Response:**
```json
{
  "topic": "Lakers championship prospects",
  "article": "The Los Angeles Lakers have emerged as serious...",
  "rot_score": {
    "rot_score": 2,
    "risk_level": "green",
    "confidence": 0.98,
    "top_issues": [],
    "recommended_action": "none"
  }
}
```
</details>

<details>
<summary><strong>POST /api/feedback</strong></summary>

**Request:**
```json
{
  "topic": "Lakers championship prospects",
  "original": "Generated article text...",
  "edited": "User-corrected article text..."
}
```

**Response:**
```json
{
  "success": true,
  "source_ids": ["feedback-uuid-1", "feedback-uuid-2"]
}
```
</details>

---

## Tech Stack

### Backend
| Component | Technology | Purpose |
|-----------|------------|---------|
| Framework | FastAPI + Uvicorn | Async REST API + static file serving |
| Runtime | Python 3.10+ | Backend logic |
| LLM | GMI Cloud (DeepSeek-V3.2) | Rot scoring & content generation |
| Vector DB | HydraDB | Auto-embedding, indexing, and semantic retrieval |
| HTTP | requests | LLM API calls |

### Frontend
| Component | Technology | Purpose |
|-----------|------------|---------|
| Language | Vanilla HTML/CSS/JS | No framework — single file SPA |
| Theme | Dark mode CSS | Custom dark dashboard |
| Layout | CSS Grid | Responsive article card grid |

---

## Project Structure

```
DocRay/
├── src/
│   ├── server.py          # FastAPI app — all endpoints + static serving
│   ├── config.py          # Environment variable loading
│   ├── rot_score.py       # LLM-as-judge scoring pipeline
│   ├── generate.py        # Content generation + HydraDB retrieval
│   ├── pipeline.py        # Generation with retry loop
│   └── feedback.py        # Edit pair storage and retrieval
│
├── web/
│   └── index.html         # Single-page dashboard (all HTML/CSS/JS)
│
├── scripts/
│   └── hydra_setup.py     # HydraDB tenant provisioning + corpus upload
│
├── data/                  # Local article data
├── nba_news.json          # Sample corpus (150 ESPN articles)
│
├── requirements.txt       # Python dependencies
├── package.json           # npm scripts (dev server)
├── .env.example           # Environment variable template
└── .env                   # Secrets (git-ignored)
```

---

## Pipelines

### Rot Scoring (`src/rot_score.py`)

Sends an article through a structured LLM prompt that returns a JSON object with `rot_score`, `risk_level`, `confidence`, `top_issues`, and `recommended_action`. The model is instructed to cite specific sentences, not summarize.

```bash
python src/rot_score.py "Article text here"
```

### Content Generation (`src/generate.py`)

Retrieves the top 5 most semantically similar articles from HydraDB using `full_recall`, then instructs the LLM to write a new article on the target topic **in the same voice** as those exemplars.

```bash
python src/generate.py "NBA Finals preview"
```

### Full Pipeline with Retry (`src/pipeline.py`)

Wraps generation with an automatic rot-score check. If the generated output scores above the healthy threshold, it retries with additional guidance. Stops at `max_iterations`.

```bash
python src/pipeline.py "Knicks playoff run"
```

### Feedback Loop (`src/feedback.py`)

Stores `(original, edited)` article pairs in the `edited-outputs` HydraDB tenant. Generation automatically retrieves from both tenants so corrections accumulate into a proprietary style guide over time.

```bash
python src/feedback.py demo
```

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HYDRADB_API_KEY` | Yes | HydraDB API key |
| `HYDRADB_BASE_URL` | Yes | HydraDB API endpoint |
| `HYDRADB_TENANT_ID` | Yes | Main corpus tenant ID (e.g. `espn-corpus`) |
| `HYDRADB_FEEDBACK_TENANT_ID` | Yes | Feedback tenant ID (e.g. `edited-outputs`) |
| `HYDRADB_KNOWLEDGE_JSON` | Yes | Path to corpus JSON file |
| `GMI_CLOUD_API_KEY` | Yes | GMI Cloud API key |
| `GMI_CLOUD_BASE_URL` | Yes | GMI Cloud API endpoint |
| `GMI_CLOUD_MODEL` | Yes | Model ID (e.g. `deepseek-ai/DeepSeek-V3.2`) |

### Example `.env`

```env
# HydraDB
HYDRADB_API_KEY=your-key-here
HYDRADB_BASE_URL=https://api.hydradb.com
HYDRADB_TENANT_ID=espn-corpus
HYDRADB_FEEDBACK_TENANT_ID=edited-outputs
HYDRADB_KNOWLEDGE_JSON=nba_news.json

# GMI Cloud
GMI_CLOUD_API_KEY=your-key-here
GMI_CLOUD_BASE_URL=https://api.gmi-serving.com/v1
GMI_CLOUD_MODEL=deepseek-ai/DeepSeek-V3.2
```

---

## Built With

- [HydraDB](https://hydradb.com) - Vector database with automatic embedding, indexing, and full-recall retrieval
- [GMI Cloud](https://gmi-serving.com) - OpenAI-compatible LLM API for scoring and generation
- [DeepSeek-V3.2](https://deepseek.com) - LLM for rot scoring and style-matched content generation
- [FastAPI](https://fastapi.tiangolo.com) - Modern Python web framework

---

## License

MIT License - see [LICENSE](LICENSE) for details.
