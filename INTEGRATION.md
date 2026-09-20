# Daleel Balady Search Service — Integration Guide

## Overview

A hybrid Arabic/English search service running at `http://127.0.0.1:8090` (internal).  
Exposes a job-based async API with Server-Sent Events (SSE) for live progress streaming.

The pipeline: query → Redis queue → worker → router → optional LLM rewrite → MySQL FULLTEXT → BGE-M3 semantic embedding → Qdrant vector search → geo scoring → hybrid merge → hydration → ranked results.

---

## Base URL

| Environment | URL |
|---|---|
| Internal (server) | `http://127.0.0.1:8090` |
| Via nginx proxy | Configure `/api/search/` → `http://127.0.0.1:8090/v1/search/` |

---

## API Reference

### 1. Create a Search Job

**`POST /v1/search`**

Start a search. Returns a `jobId` immediately — the actual search runs asynchronously.

#### Request Body

```json
{
  "query": "عايز دكتور اسنان قريب مني",
  "lat": 31.04,
  "lon": 30.47,
  "cityId": "176",
  "governorateId": null,
  "categoryIds": [],
  "entityTypes": [],
  "limit": 10,
  "offset": 0,
  "userId": null,
  "sessionId": null
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes | Arabic or English search query, 1–1000 chars |
| `lat` | float | no | User latitude (-90 to 90). Enables geo scoring |
| `lon` | float | no | User longitude (-180 to 180). Enables geo scoring |
| `cityId` | string | no | Filter results to a specific city |
| `governorateId` | string | no | Filter results to a governorate |
| `categoryIds` | string[] | no | Filter to specific category IDs |
| `entityTypes` | string[] | no | Filter to entity types: `SHOP`, `SERVICE`, `PRODUCT`, `OFFER` |
| `limit` | int | no | Results per page, 1–30 (default: 10) |
| `offset` | int | no | Pagination offset (default: 0) |
| `userId` | string | no | For future personalization |
| `sessionId` | string | no | For future session tracking |

#### Response `200`

```json
{
  "jobId": "search_e7f1d69928504686acf6eb1a1c038f48",
  "status": "RECEIVED"
}
```

---

### 2. Stream Live Progress (SSE)

**`GET /v1/search/{jobId}/events`**

Connect immediately after creating the job. Streams status updates then the final result as Server-Sent Events.

#### Event: `status`

Fired at each pipeline stage. Use the `message` for the loading UI text.

```
event: status
data: {
  "jobId": "search_xxx",
  "status": "CLASSIFYING",
  "message": "Understanding the search.",
  "data": {},
  "timestamp": 1789937105.75
}
```

#### Status sequence & suggested UI text

| `status` | `message` (from server) | Suggested animated icon |
|---|---|---|
| `RECEIVED` | Search received. | pulse dot |
| `QUEUED` | Search queued. | pulse dot |
| `RUNNING` | Worker N started. | spinner |
| `CLASSIFYING` | Understanding the search. | brain/sparkle |
| `REWRITING` | Refining the search query. | pencil/sparkle |
| `SEARCHING_DATABASE` | Searching names and database text. | database |
| `EMBEDDING` | Creating the semantic search vector. | waveform |
| `SEARCHING_VECTOR` | Searching the semantic index. | radar/satellite |
| `MERGING` | Combining search matches. | merge arrows |
| `LOADING_DETAILS` | Loading result details. | download |
| `RANKING` | Ranking the results. | trophy/sort |
| `COMPLETED` | Search completed. | checkmark |
| `FAILED` | Search failed. | error icon |

#### Event: `result`

Fired once when complete. Contains the full result payload. Close the SSE connection after receiving this.

```
event: result
data: { ...full SearchResponse... }
```

---

### 3. Poll for Result (non-streaming fallback)

**`GET /v1/search/{jobId}`**

Returns status while running, full result when done.

```json
{
  "status": "COMPLETED",
  "result": { ...SearchResponse... }
}
```

---

### 4. Health Check

**`GET /v1/health`**

```json
{ "ok": true, "service": "daleel-search" }
```

---

## SearchResponse Schema

```json
{
  "jobId": "search_xxx",
  "query": "دكتور اسنان",
  "normalizedQuery": "دكتور اسنان",
  "mode": "GEO",
  "results": [ ...SearchResult[] ],
  "meta": {
    "total": 83,
    "returned": 5,
    "offset": 0,
    "tookMs": 718.51,
    "locationUsed": true,
    "cityId": "176",
    "governorateId": null
  }
}
```

### SearchResult Schema

```json
{
  "entityType": "SHOP",
  "entityId": "98f48eb8-c452-4b7b-8971-fb6faf1cd69e",
  "title": "عيادة اسنان د.محمد وفائي",
  "titleAr": "عيادة اسنان د.محمد وفائي",
  "titleEn": null,
  "subtitle": "طب أسنان",
  "url": "/shop/عيادة-اسنان-دمحمد-وفائي-6108",
  "image": "https://cdn.daleelbalady.com/media/shop/cover.jpg",
  "rating": 4.5,
  "reviewCount": 23,
  "verified": true,
  "distanceMeters": 1240.5,
  "score": 0.789784,
  "lexicalScore": 1.0,
  "semanticScore": 0.970812,
  "geoScore": 0.84,
  "businessScore": 0.35,
  "metadata": {
    "slug": "عيادة-اسنان-دمحمد-وفائي-6108",
    "partnerLevel": "GOLD",
    "rank": "PREMIUM",
    "hasDiscount": false,
    "verificationKind": "VERIFIED"
  }
}
```

| Field | Notes |
|---|---|
| `url` | Relative path — prepend `https://daleelbalady.com` |
| `image` | May be `null` — show placeholder |
| `distanceMeters` | `null` if no coordinates in index yet |
| `score` | Composite 0–1. Higher = more relevant |
| `metadata.partnerLevel` | `NONE`, `SILVER`, `GOLD`, `PLATINUM` |
| `metadata.verificationKind` | `NONE`, `DEMO`, `VERIFIED` |

---

## Search Modes

The router automatically picks the mode — the frontend does not need to set it.

| Mode | Triggered by | Uses |
|---|---|---|
| `NAME` | Short name query, no intent words | Lexical only |
| `GEO` | Has coordinates or location words | Lexical + Semantic + Geo |
| `HYBRID` | Semantic intent words | Lexical + Semantic + LLM rewrite |
| `HYBRID_GEO` | Semantic intent + location | Lexical + Semantic + Geo + LLM rewrite |

---

## Frontend Integration

### JavaScript / TypeScript — Full SSE Flow

```typescript
interface SearchResult {
  entityType: string;
  entityId: string;
  title: string;
  titleAr: string | null;
  titleEn: string | null;
  subtitle: string | null;
  url: string | null;
  image: string | null;
  rating: number;
  reviewCount: number;
  verified: boolean;
  distanceMeters: number | null;
  score: number;
  lexicalScore: number;
  semanticScore: number;
  geoScore: number;
  businessScore: number;
  metadata: {
    slug: string | null;
    partnerLevel: string | null;
    rank: string | null;
    hasDiscount: boolean | null;
    verificationKind: string | null;
  };
}

interface SearchResponse {
  jobId: string;
  query: string;
  normalizedQuery: string;
  mode: string;
  results: SearchResult[];
  meta: {
    total: number;
    returned: number;
    offset: number;
    tookMs: number;
    locationUsed: boolean;
    cityId: string | null;
    governorateId: string | null;
  };
}

interface SearchStatus {
  jobId: string;
  status: string;
  message: string;
  data: Record<string, unknown>;
  timestamp: number;
}

const SEARCH_BASE = 'https://daleelbalady.com/api/search'; // nginx proxy path

async function search(
  query: string,
  options: {
    lat?: number;
    lon?: number;
    cityId?: string;
    limit?: number;
    offset?: number;
  },
  onStatus: (status: SearchStatus) => void,
  onResult: (result: SearchResponse) => void,
  onError: (error: string) => void
): Promise<void> {
  // 1. Create the job
  const res = await fetch(`${SEARCH_BASE}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, limit: 10, ...options }),
  });

  if (!res.ok) {
    onError('Failed to start search');
    return;
  }

  const { jobId } = await res.json();

  // 2. Open SSE stream
  const es = new EventSource(`${SEARCH_BASE}/${jobId}/events`);

  es.addEventListener('status', (e: MessageEvent) => {
    const status: SearchStatus = JSON.parse(e.data);
    onStatus(status);
    if (status.status === 'FAILED') {
      es.close();
      onError(String((status.data as any)?.error ?? 'Search failed'));
    }
  });

  es.addEventListener('result', (e: MessageEvent) => {
    es.close();
    onResult(JSON.parse(e.data));
  });

  es.onerror = () => {
    es.close();
    onError('Connection lost');
  };
}
```

---

### React — Loading State with Animated Text

```tsx
import { useState, useCallback } from 'react';

// Animated loading indicator — cycles through status messages
// with a smooth fade transition and a pulsing Arabic-aware spinner.

const STATUS_ICONS: Record<string, string> = {
  RECEIVED:           '⟳',
  QUEUED:             '⟳',
  RUNNING:            '⟳',
  CLASSIFYING:        '✦',
  REWRITING:          '✦',
  SEARCHING_DATABASE: '◈',
  EMBEDDING:          '◈',
  SEARCHING_VECTOR:   '◈',
  MERGING:            '⊕',
  LOADING_DETAILS:    '⊕',
  RANKING:            '⊕',
  COMPLETED:          '✓',
  FAILED:             '✕',
};

function SearchLoader({ message, status }: { message: string; status: string }) {
  const icon = STATUS_ICONS[status] ?? '⟳';
  const isDone = status === 'COMPLETED' || status === 'FAILED';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '12px 16px',
        borderRadius: '12px',
        background: 'rgba(0,0,0,0.04)',
        animation: isDone ? 'none' : undefined,
        direction: 'rtl',
        fontFamily: 'inherit',
      }}
    >
      <span
        style={{
          fontSize: '18px',
          display: 'inline-block',
          animation: isDone ? 'none' : 'daleel-spin 1.4s linear infinite',
          color: status === 'FAILED' ? '#e53e3e' : '#3b82f6',
        }}
      >
        {icon}
      </span>
      <span
        key={message}
        style={{
          fontSize: '14px',
          color: '#374151',
          animation: 'daleel-fade 0.35s ease',
        }}
      >
        {message}
      </span>
      <style>{`
        @keyframes daleel-spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes daleel-fade {
          from { opacity: 0; transform: translateY(4px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}

// Result card
function SearchResultCard({ result }: { result: SearchResult }) {
  const fullUrl = result.url ? `https://daleelbalady.com${result.url}` : null;
  const isVerified = result.verified;
  const distance = result.distanceMeters != null
    ? result.distanceMeters < 1000
      ? `${Math.round(result.distanceMeters)} م`
      : `${(result.distanceMeters / 1000).toFixed(1)} كم`
    : null;

  return (
    <a
      href={fullUrl ?? '#'}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        display: 'flex',
        gap: '12px',
        padding: '12px',
        borderRadius: '12px',
        border: '1px solid #e5e7eb',
        background: '#fff',
        textDecoration: 'none',
        color: 'inherit',
        transition: 'box-shadow 0.15s',
        direction: 'rtl',
      }}
    >
      {/* Image */}
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: 8,
          background: '#f3f4f6',
          flexShrink: 0,
          overflow: 'hidden',
        }}
      >
        {result.image ? (
          <img
            src={result.image}
            alt={result.title}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 22,
              color: '#9ca3af',
            }}
          >
            ◈
          </div>
        )}
      </div>

      {/* Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{
              fontWeight: 600,
              fontSize: 14,
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {result.title}
          </span>
          {isVerified && (
            <span style={{ color: '#3b82f6', fontSize: 13, flexShrink: 0 }}>✓</span>
          )}
        </div>

        {result.subtitle && (
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
            {result.subtitle}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: 4, alignItems: 'center' }}>
          {result.rating > 0 && (
            <span style={{ fontSize: 12, color: '#f59e0b' }}>
              {'★'.repeat(Math.round(result.rating))} {result.rating.toFixed(1)}
              <span style={{ color: '#9ca3af' }}> ({result.reviewCount})</span>
            </span>
          )}
          {distance && (
            <span style={{ fontSize: 12, color: '#6b7280' }}>📍 {distance}</span>
          )}
          {result.metadata.hasDiscount && (
            <span
              style={{
                fontSize: 11,
                background: '#fef3c7',
                color: '#92400e',
                borderRadius: 4,
                padding: '1px 6px',
              }}
            >
              خصم
            </span>
          )}
        </div>
      </div>
    </a>
  );
}

// Main hook — use this in your chat component
function useSearch() {
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState('');
  const [statusKey, setStatusKey] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [meta, setMeta] = useState<SearchResponse['meta'] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async (
    query: string,
    options: { lat?: number; lon?: number; cityId?: string; limit?: number } = {}
  ) => {
    setLoading(true);
    setResults([]);
    setMeta(null);
    setError(null);
    setStatusMessage('جاري البحث...');
    setStatusKey('RECEIVED');

    await search(
      query,
      options,
      (status) => {
        setStatusMessage(status.message);
        setStatusKey(status.status);
      },
      (result) => {
        setLoading(false);
        setResults(result.results);
        setMeta(result.meta);
        setStatusMessage('');
      },
      (err) => {
        setLoading(false);
        setError(err);
        setStatusMessage('');
      }
    );
  }, []);

  return { run, loading, statusMessage, statusKey, results, meta, error };
}

// Example chat bubble usage
function SearchBubble({ query, lat, lon, cityId }: {
  query: string;
  lat?: number;
  lon?: number;
  cityId?: string;
}) {
  const { run, loading, statusMessage, statusKey, results, meta, error } = useSearch();

  // Trigger on mount
  useState(() => { run(query, { lat, lon, cityId }); });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 480 }}>
      {loading && (
        <SearchLoader message={statusMessage} status={statusKey} />
      )}

      {error && (
        <div style={{ color: '#e53e3e', fontSize: 13, padding: '8px 12px' }}>
          حدث خطأ: {error}
        </div>
      )}

      {results.length > 0 && (
        <>
          <div style={{ fontSize: 12, color: '#9ca3af', padding: '0 4px' }}>
            {meta?.total} نتيجة · {meta?.tookMs}ms
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {results.map((r) => (
              <SearchResultCard key={`${r.entityType}-${r.entityId}`} result={r} />
            ))}
          </div>
        </>
      )}

      {!loading && results.length === 0 && !error && (
        <div style={{ fontSize: 13, color: '#9ca3af' }}>لا توجد نتائج</div>
      )}
    </div>
  );
}
```

---

### Nginx Proxy Config

Add to your server block so the frontend hits `/api/search/` and nginx forwards to the service:

```nginx
location /api/search/ {
    proxy_pass http://127.0.0.1:8090/v1/search/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

    # Critical for SSE — disable all buffering
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 1h;
    chunked_transfer_encoding on;
}
```

After this the frontend uses:
- `POST /api/search` → create job
- `GET /api/search/{jobId}/events` → SSE stream
- `GET /api/search/{jobId}` → poll result

---

## Backend (Node.js / NestJS) Integration

If searches are proxied through your backend instead of direct from browser:

```typescript
// search.service.ts
import { Injectable } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';

const SEARCH_INTERNAL = 'http://127.0.0.1:8090/v1';

@Injectable()
export class SearchService {
  constructor(private http: HttpService) {}

  async createJob(body: {
    query: string;
    lat?: number;
    lon?: number;
    cityId?: string;
    limit?: number;
    offset?: number;
  }) {
    const { data } = await firstValueFrom(
      this.http.post(`${SEARCH_INTERNAL}/search`, body)
    );
    return data; // { jobId, status }
  }

  async getResult(jobId: string) {
    const { data } = await firstValueFrom(
      this.http.get(`${SEARCH_INTERNAL}/search/${jobId}`)
    );
    return data;
  }

  // For SSE passthrough — pipe the upstream SSE to the client response
  getEventsUrl(jobId: string) {
    return `${SEARCH_INTERNAL}/search/${jobId}/events`;
  }
}
```

For SSE passthrough in NestJS, pipe the upstream response directly:

```typescript
// search.controller.ts
@Get(':jobId/events')
async streamEvents(@Param('jobId') jobId: string, @Res() res: Response) {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.flushHeaders();

  const upstream = await fetch(`http://127.0.0.1:8090/v1/search/${jobId}/events`);
  const reader = upstream.body!.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    res.write(decoder.decode(value));
  }
  res.end();
}
```

---

## Chat Integration Pattern

When a user sends a message in the chat that triggers a search:

1. **Detect search intent** in the chat handler (or always search for queries)
2. **POST** to `/api/search` with the query + user's GPS coords if available
3. **Open EventSource** to `/api/search/{jobId}/events`
4. **Show `<SearchLoader>`** while events stream in — update text on each `status` event
5. **On `result` event** — close EventSource, replace loader with `<SearchResultCard>` list
6. **On error** — show retry option

The `message` field in each status event is already human-readable Arabic-friendly English. You can use it as-is or map it to Arabic:

```typescript
const STATUS_AR: Record<string, string> = {
  RECEIVED:           'تم استلام البحث',
  QUEUED:             'في قائمة الانتظار',
  RUNNING:            'جاري المعالجة',
  CLASSIFYING:        'تحليل الاستفسار',
  REWRITING:          'تحسين نص البحث',
  SEARCHING_DATABASE: 'البحث في قاعدة البيانات',
  EMBEDDING:          'معالجة المعنى الدلالي',
  SEARCHING_VECTOR:   'البحث الذكي',
  MERGING:            'دمج النتائج',
  LOADING_DETAILS:    'تحميل التفاصيل',
  RANKING:            'ترتيب النتائج',
  COMPLETED:          'اكتمل البحث',
  FAILED:             'فشل البحث',
};
```

---

## Key Notes for the Agent

- **SSE requires no buffering** — ensure nginx has `proxy_buffering off` and the frontend doesn't batch SSE events
- **Arabic text** is returned as proper Unicode — render with `dir="rtl"` or `direction: rtl`
- **Images may be null** — always have a placeholder ready
- **`url` is relative** — always prepend `https://daleelbalady.com`
- **`distanceMeters` is null** until `index_search_docs.py` is run to populate Qdrant coordinates
- **Job TTL is 15 minutes** — don't poll after that, the job is gone
- **Max 30 results per page** — use `offset` for pagination
- **Two workers run in parallel** — typical response time 500–800ms on warm cache
- **llama.cpp is optional** — if port 8080 is down, search degrades gracefully (no query rewrite, still works)
