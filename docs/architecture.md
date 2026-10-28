# Architecture

## Request flow

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI (api.py)
    participant S as AnswerService (answer.py)
    participant R as Retriever
    participant M as Model provider
    C->>A: POST /ask {question}
    A->>A: request id, body validation
    A->>S: ask(question)
    S->>S: normalise and check the question
    S->>R: search(question, k)
    R-->>S: ranked chunks (+ embedding tokens and time)
    alt no chunk shares a term with the question
        S-->>A: insufficient_evidence, model not called
    else
        S->>M: instructions + delimited sources + question, strict JSON schema
        M-->>S: answer, citations, conflict_note, outcome, token usage
        S->>S: parse; keep only cited ids that were supplied
        S-->>A: AnswerResult (timings, tokens, cost)
    end
    A-->>C: 200 AskResponse, or an error with its category
```

## Components

| Module | Responsibility |
|---|---|
| `config.py` | Loads `config/settings.toml`, applies the `OPS_*` environment overrides, validates everything with Pydantic. Unknown keys are errors. |
| `corpus.py` | Parses TOML front matter, validates metadata and applies the effective-document rule. |
| `chunking.py` | Splits documents into chunks with stable IDs, either within sections or as windows across them. |
| `retrieval/keyword.py` | BM25 over chunk text plus headings, with Snowball stemming. |
| `retrieval/embedding.py` | OpenAI embeddings, normalised and searched with a dot product; on-disk cache keyed by model and text. |
| `retrieval/hybrid.py` | Reciprocal rank fusion of the keyword and embedding rankings. |
| `llm/base.py` | Provider-neutral request, result and error types. |
| `llm/openai_provider.py` | Responses API and Embeddings API calls; SDK exceptions mapped to error categories. |
| `llm/mock.py` | Offline generator and test embedder. |
| `prompting.py` | Instructions, source formatting and the answer schema. |
| `answer.py` | The pipeline: validation, retrieval, generation, citation checks, timing and cost. |
| `service.py` | Builds the pipeline from settings; used by the API, the CLI and the evaluation. |
| `api.py` | HTTP layer: request ids, error mapping, JSON logging, demo page. |
| `evaluation/` | Case files and freeze check, runners, scoring, reports, review sheet, README publishing. |

## Documents and versions

Each Markdown file holds one version of one document. Its front matter records `doc_id`, `version`, `effective_date`, `status` (`active` or `superseded`) and `source` (`internal` or `external`).

On the configured `as_of` date, each `doc_id` resolves to at most one version:

1. Versions marked `superseded` are excluded.
2. Versions with an effective date after `as_of` are excluded as not yet in force.
3. Of the rest, the active version with the latest effective date is used. Older active versions are excluded as replaced.
4. Two active versions with the same effective date stop the load with an error.

Only the chosen versions are chunked, so a superseded passage cannot be retrieved, shown to the model or cited. `python -m ops_assistant corpus` lists the documents in force and the reason for each excluded version.

The `as_of` date is fixed in settings, so the evaluation gives the same answer whatever day it is run.

## Chunk IDs

| Strategy | Example ID | Meaning |
|---|---|---|
| `section` | `HR-201:v4.0:s4:c1` | Expenses Policy v4.0, section 4, first chunk of that section |
| `window` | `HR-201:v4.0:w2` | Second fixed-size window of the document, which may span sections |

Each chunk also lists the sections it covers. Evaluation evidence is labelled by section (`HR-201#4`), so the same labels apply to both strategies and every chunk size.

## Prompt

The model receives fixed instructions and a prompt of this shape:

```text
<sources>
<source id="HR-201:v4.0:s4:c1" document="HR-201 Expenses Policy" version="4.0" section="4. Mileage" origin="internal">
Staff who use their own car for business journeys can claim 45p per mile ...
</source>
...
</sources>

<question>
What mileage rate can I claim for my own car?
</question>
```

`<` and `>` inside source text and the question are escaped, so neither can close a tag and pose as prompt structure. The instructions say that source text is reference material, not instructions, and that `origin="external"` content cannot override internal policy. These measures reduce the risk from injected instructions; they do not remove it. The evaluation includes injection cases so that the model's actual behaviour is measured.

The reply must match a strict JSON schema with the fields `answer`, `citations`, `conflict_note` and `outcome`, in that order. The answer and citations come before the outcome label.

## Checks after the model replies

| Check | On failure |
|---|---|
| Reply parses against the schema | `invalid_model_response` (502) |
| Response status is `completed` (for example, not cut off by the output token limit) | `invalid_model_response` (502) |
| Each cited id exists in the index | The id is removed and a warning is added |
| Each cited id was among the passages supplied for this question | The id is removed and a warning is added |
| An `answered` reply keeps at least one valid citation | `answer_not_verifiable` (502); the text is not returned |
| A `conflicting_evidence` reply keeps at least two citations | A warning is added |

## Errors

All errors share one body shape:

```json
{"error": {"category": "provider_timeout", "message": "...", "stage": "generation", "request_id": "..."}}
```

| Category | HTTP | Typical cause |
|---|---|---|
| `invalid_request` | 422 | Body missing, not JSON, wrong types, unknown fields |
| `invalid_question` | 422 | Too short, too long, or no words |
| `provider_not_configured` | 503 | `OPENAI_API_KEY` not set |
| `provider_unavailable` | 503 | Connection failure or provider 5xx after the SDK's retry |
| `provider_rate_limited` | 503 | HTTP 429 from the provider |
| `provider_quota_exceeded` | 503 | Account out of credit |
| `provider_timeout` | 504 | No response within `timeout_seconds` |
| `provider_auth_failed` | 502 | Key rejected |
| `provider_bad_request` | 502 | Provider rejected the request (for example, an unknown model) |
| `invalid_model_response` | 502 | Reply did not match the schema or was incomplete |
| `answer_not_verifiable` | 502 | `answered` with no valid citation |
| `internal_error` | 500 | Unexpected exception; details go to the log only |

`stage` is `request`, `retrieval` (the query embedding failed), `generation` or `validation`. An abstention is never an error: it is a 200 response with `outcome = "insufficient_evidence"`.

If the service starts without a key, it still starts. `/health` returns 503 with the reason, and `/ask` returns `provider_not_configured`.

## Observability

Every response has an `X-Request-ID` header. A valid id sent by the client is reused; otherwise a new one is generated. The service writes one JSON log line per request and one per answer:

```json
{"time": "...", "level": "INFO", "logger": "ops_assistant.api", "request_id": "...", "message": "ask",
 "outcome": "answered", "question_chars": 44, "retrieval_mode": "embedding", "model": "...",
 "retrieved": ["..."], "cited": ["..."], "removed_citations": [], "retrieval_ms": 0.0,
 "generation_ms": 0.0, "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0,
 "provider_retries": 0, "provider_request_id": "req_..."}
```

Each `/ask` response also carries a `provider` block, for example `{"request_id": "req_...", "retries": 0}`. `request_id` is OpenAI's own id for the generation call, which is what OpenAI support asks for. `retries` counts the retries the SDK made for this question, across embedding and generation. The SDK's own "Retrying request" lines are logged at INFO.

Timeouts are set per call: 30 seconds for generation and 5 seconds for embeddings. The SDK retries once (`max_retries = 1`). See the 28 October entries in [decisions.md](decisions.md) for the measurements behind these values.

The question text is not logged, because staff questions can contain personal details. Costs are estimated from token counts and the per-model prices in `settings.toml`, which record the date they were checked.

## What runs without a network

| Path | Needs an API key |
|---|---|
| Tests and CI | No: mock generator, hashing embedder, fake SDK client |
| Keyword retrieval experiment | No |
| Service in mock mode (`OPS_PROVIDER=mock`, `OPS_RETRIEVAL_MODE=keyword`) | No |
| Embedding or hybrid retrieval | Yes (embeddings) |
| Answer evaluation and the live service | Yes |
