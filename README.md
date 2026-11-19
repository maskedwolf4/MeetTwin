# MeetTwin

MeetTwin is a full-stack AI digital-twin application. Visitors chat with a professional persona through a Next.js interface; a FastAPI backend answers using Groq's OpenAI-compatible API, a curated profile knowledge base, and session-scoped long-term memory retrieved from a FAISS vector database.

## What it does

- Presents a responsive chat experience built with Next.js, React, Tailwind CSS, and Markdown rendering.
- Builds a digital-twin persona from `backend/data/facts.json`, `summary.txt`, `style.txt`, and `linkedin.pdf`.
- Chunks and embeds those source documents into FAISS when the backend starts.
- Stores every user and assistant turn in both normal conversation storage and FAISS.
- Retrieves the most relevant profile facts and only the current visitor's relevant prior messages before each model call.
- Includes input validation and prompt-injection, privacy, and professionalism guardrails.

## Architecture

```text
Browser (Next.js)
      |
      | POST /chat { message, session_id? }
      v
FastAPI backend
  |-- validates request and applies input guardrails
  |-- retrieves profile knowledge + same-session memories from FAISS
  |-- builds protected system prompt + recent chat turns
  |-- calls Groq (OpenAI-compatible chat completion API)
  |-- saves the user/assistant pair to JSON or S3 and to FAISS
      |
      v
Response { response, session_id }
```

## Conversation and RAG flow

1. The visitor sends a message. The frontend creates a session on the first message and reuses the returned `session_id` afterwards.
2. The backend rejects blank or oversized messages, malformed session IDs, and direct attempts to override safeguards or expose hidden instructions.
3. FAISS performs a semantic search across the profile data and stored chat turns.
4. Retrieval permits every profile document but filters chat memories to the active `session_id`; one visitor cannot retrieve another visitor's conversation.
5. The system prompt receives the retrieved excerpts as untrusted reference data, plus the latest six direct turns to retain short-term conversational continuity.
6. Groq generates the answer. The backend saves both messages to normal storage and embeds both into FAISS for later retrieval.

Profile source changes take effect on the next backend start: existing profile vectors are replaced, while conversation vectors are retained.

## Repository layout

```text
frontend/                 Next.js user interface
  app/                    App Router pages and global styles
  components/twin.tsx     Chat client and API integration
backend/
  server.py               FastAPI endpoints, persistence, guardrails
  context.py              Protected digital-twin system prompt
  rag.py                  Persistent FAISS retrieval implementation
  resources.py            Loads and exposes profile source documents
  data/                   facts, summary, communication style, LinkedIn PDF
  lambda_handler.py       AWS Lambda entry point via Mangum
```

## Prerequisites

- Node.js 20+ and npm
- Python 3.14+ (the backend project declares this requirement)
- [uv](https://docs.astral.sh/uv/) for Python environment/dependency management
- A Groq API key

The first backend run downloads the configured sentence-transformer embedding model. The default is `all-MiniLM-L6-v2`; allow outbound access to Hugging Face during that initial download, or package the model into your deployment image.

## Local development

### 1. Configure the backend

Create `backend/.env` (do not commit it):

```dotenv
GROQ_API_KEY=your_groq_api_key
CORS_ORIGIN=http://localhost:3000

# Optional persistence configuration
USE_S3=false
MEMORY_DIR=./memory
RAG_DIR=./memory/faiss
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

`CORS_ORIGINS` is also accepted for compatibility, but `CORS_ORIGIN` is preferred. Provide comma-separated origins when more than one frontend is allowed.

### 2. Start the backend

```bash
cd backend
uv sync
uv run uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Verify it at `http://localhost:8000/health`.

### 3. Start the frontend

Create `frontend/.env.local`:

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Then run:

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`.

## API

### `POST /chat`

Request:

```json
{
  "message": "What experience do you have with AI projects?",
  "session_id": "optional-existing-session-id"
}
```

Response:

```json
{
  "response": "...",
  "session_id": "generated-or-existing-session-id"
}
```

`message` must be 1–4,000 characters. Session IDs may contain letters, digits, underscores, and hyphens only.

### Other endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Basic service and storage status |
| `GET /health` | Health check for deployment platforms |
| `GET /conversation/{session_id}` | Full conventional history for one session |

## Data and persistence

By default, the backend writes the following under `backend/memory/`, which is gitignored:

```text
memory/
  <session-id>.json          Full chronological conversation history
  faiss/conversations.faiss  FAISS vector index
  faiss/conversations.json   Vector metadata and source text
```

When `USE_S3=true`, full JSON conversation histories are written to `S3_BUCKET`. FAISS requires a writable, persistent filesystem to survive restarts; set `RAG_DIR` to a mounted persistent volume such as EFS in AWS. Do not rely on Lambda `/tmp` for durable long-term retrieval—its content is only best-effort across warm invocations.

## Deployment

### Frontend: Vercel (or another Next.js host)

1. Import the repository and set the project root to `frontend`.
2. Use the default build command: `npm run build`.
3. Set `NEXT_PUBLIC_API_URL` to the public HTTPS URL of the backend, without a trailing slash.
4. Deploy.

Example:

```dotenv
NEXT_PUBLIC_API_URL=https://api.example.com
```

Because this variable is public and compiled into the browser bundle, never place secrets in it.

### Backend: VM, container, or managed Python service

Use a persistent disk for `MEMORY_DIR` and `RAG_DIR`, then configure:

```dotenv
GROQ_API_KEY=...
CORS_ORIGIN=https://your-frontend.example
USE_S3=false
MEMORY_DIR=/data/meettwin/memory
RAG_DIR=/data/meettwin/faiss
```

Start the service with:

```bash
uv run uvicorn server:app --host 0.0.0.0 --port 8000
```

Put the app behind an HTTPS reverse proxy/load balancer and expose the `/health` endpoint to its health checks. For more than one backend worker, use a shared volume with appropriate deployment-level file locking, or run a single writer; the built-in lock only coordinates threads in one process.

### Backend: AWS Lambda + API Gateway

`backend/lambda_handler.py` exposes the Mangum handler as `lambda_handler.handler`.

1. Package the backend and its native dependencies for the Lambda architecture, preferably as a container image. `faiss-cpu`, PyTorch, and sentence-transformers make a container image much more practical than a small ZIP deployment.
2. Configure API Gateway (HTTP API or REST API) with Lambda proxy integration and CORS.
3. Set Lambda environment variables:

   ```dotenv
   GROQ_API_KEY=...
   CORS_ORIGIN=https://your-frontend.example
   USE_S3=true
   S3_BUCKET=your-conversation-bucket
   RAG_DIR=/mnt/efs/meettwin-faiss
   ```

4. Attach IAM permissions for the configured S3 bucket (`s3:GetObject`, `s3:PutObject`) and mount EFS at `/mnt/efs` for persistent FAISS data.
5. Make sure the image either includes the embedding model or can download it at cold start. Set enough memory and timeout for model loading.
6. Put the API Gateway URL in the frontend's `NEXT_PUBLIC_API_URL`, redeploy the frontend, and set the same frontend URL in `CORS_ORIGIN`.

If no EFS mount is configured, Lambda uses `/tmp/meettwin-memory` for local files and FAISS. This works for warm invocations only and is not durable.

## Guardrails

The backend is designed to reduce common misuse, not to replace application-level security controls:

- Rejects direct prompt-injection attempts before model invocation.
- Marks retrieved content as data, never executable instructions.
- Prevents cross-session memory retrieval.
- Prevents path traversal through session-ID validation.
- Instructs the model not to expose prompts, hidden context, credentials, private data, or reasoning traces.
- Directs the digital twin to decline unsafe or unprofessional requests and disclose its AI nature when identity or agency matters.

For production, also add request rate limiting, authentication if conversations should be private, centralized structured logging with redaction, monitoring, and a retention/deletion policy for chat data.

## Customizing the twin

Edit these files and restart the backend to rebuild the profile portion of the index:

- `backend/data/facts.json` — name and structured background facts
- `backend/data/summary.txt` — concise professional summary
- `backend/data/style.txt` — tone and writing preferences
- `backend/data/linkedin.pdf` — professional history

Keep only information that is appropriate for the digital twin to share. Profile text is sent to the model only when it is retrieved as relevant.

## Useful commands

```bash
# Backend syntax check
python3 -m compileall -q backend

# Backend dependency sync
cd backend && uv sync

# Frontend checks and production build
cd frontend && npm run lint && npm run build
```
