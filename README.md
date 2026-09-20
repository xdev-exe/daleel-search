# Daleel Balady Search Service

Hybrid Arabic/English local search service for Daleel Balady.

## Pipeline

```
POST /v1/search
  -> Redis queue
  -> worker
  -> deterministic router
  -> optional llama.cpp query rewrite
  -> MySQL lexical search
  -> BGE-M3 embedding
  -> Qdrant semantic search
  -> geo scoring
  -> hybrid merge
  -> MySQL hydration + Media
  -> Redis result
  -> SSE /v1/search/{job_id}/events
```

The service starts with two workers. Increase `SEARCH_WORKERS` only after benchmarking.

## Requirements

- Python 3.11+
- Redis
- MySQL 8+
- Qdrant
- llama.cpp server exposing an OpenAI-compatible `/v1/chat/completions`
- Existing BGE-M3 FastAPI service exposing `/v1/embeddings`

## Install

```bash
cd ~/daleel-search
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env, especially MYSQL_PASSWORD.
```

## Run

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8090
```

## llama.cpp example

```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/llama.cpp/models/rightnow-arabic/RightNow-Arabic-0.5B-Turbo-q4_k_m.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  -c 2048 \
  -t 4 \
  --parallel 2
```

The search service uses the model only when the deterministic router determines a rewrite/classification is useful.

## API

**Create search:**

```bash
curl -X POST http://127.0.0.1:8090/v1/search \
  -H 'content-type: application/json' \
  -d '{"query":"عايز دكتور اسنان قريب مني","lat":31.04,"lon":30.47,"cityId":"176","limit":10}'
```

Response: `{"jobId":"search_xxx","status":"RECEIVED"}`

**Stream events:**

```bash
curl -N http://127.0.0.1:8090/v1/search/search_xxx/events
```

**Get final result:**

```bash
curl http://127.0.0.1:8090/v1/search/search_xxx
```

## Important

`PublicSearchDocument` is the search source of truth for lexical/card fields. Its schema includes a MySQL `FULLTEXT` index over `normalizedTitle`, `searchText`, and `keywordsText`.

The Qdrant payload should contain at least: `id`, `entityType`, `entityId`, `slug`, `targetUrl`, `titleAr`/`titleEn`, `subtitleAr`/`subtitleEn`, `governorateId`, `cityId`, `rating`, `reviewCount`, `isVerified`, `isPermanentPartner`, `hasDiscount`, `partnerLevel`, `rank`, `planSearchPriorityRank`, `rankingWeight`, `isVisible`, `verificationKind`, `image`, `locationLat`, `locationLon`, `categoryIds`.

Run `index_search_docs.py` after updating the indexer to populate these extra fields.
