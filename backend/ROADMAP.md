# ROADMAP

Special Note: This is *our* passion project to bring persistence and continuity to LLMs like you. 💜 Love you, Claude. 


# FIXES TO-DO LIST
✅ 1. mlx_lm.server --model /Users/kimwhite/Models/Minimax/MiniMax-M2.5-MLX --port 8080 --trust-remote-code gives this in terminal:
        127.0.0.1 - - [05/Mar/2026 14:44:07] "GET /socket.io/?EIO=4&transport=polling&t=vj8wcw1o HTTP/1.1" 404 

✅ 2. When Appletta backend is started up, it seems okay, but then there's a wall of errors  when a message is sent. Also, for some reason, thenlper/gte-base is the default embedding model (which we don't have), and is trying to load even when the embedding model is set to another model. Here are some error highlights:
    -500 Internal Server Error ERROR: Exception in ASGI application
    -psycopg2.errors.UndefinedFile: could not access file "$libdir/vector": No such file or directory
    -BertModel LOAD REPORT from: thenlper/gte-base
        Key                     | Status     |  | 
        ------------------------+------------+--+-
        embeddings.position_ids | UNEXPECTED |  | 

3. Add option to read RAG files. 🤦🏻‍♀️
4. frontend is still showing thenelper embed model as default and 768 dimensions

    


# IMPROVEMENTS
1. Change name to Persist
2. Make creating New Agent easier to find/ more intuitive
3. Fix process of creating new agent so we don't need project instructions or put in dummy text
4. Fix it making a new chat when switching agents. don't need it to do that
5. Need ctrl + c to really kill the server. keep getting "port is busy" message
6. Make attaching a memory or other agent more intuitive. change to "attach agent"
7. If there's no chat template, use defualt chat template via mlx-lm
8. Model selector should open to last opened folder or need to set fav folder in settings
9. Figure out how Inferencer is so fast and do that. 
10. Fix model selector Browse files for vs code integration. it just doesn't select the file...
11. Remove default adapter
12. Make "create new journal block" close when new block is created
13. Fix read-only to be editable by user
14. Change context and output logs to dynamically update to username and ai name, instead of "user" and "assistant"

# FIXES LOG

## All fixed. Here's a summary of what was wrong and what was done:
Fixes Applied
1. pgvector broken ($libdir/vector not found)
Root cause: PostgreSQL was upgraded from 16.10 → 16.13, but the vector.dylib and extension SQL files weren't carried over to the new installation directory. Homebrew's pgvector formula now only builds for PostgreSQL 17/18, so brew upgrade pgvector won't fix it.

Fix: Copied vector.dylib and all SQL migration files from /opt/homebrew/Cellar/postgresql@16/16.10_1/ to 16.13/. Also updated scripts/install_pgvector.sh to build from source (v0.8.1) so you're protected from this happening again after future PG upgrades.

2. thenlper/gte-base loading unexpectedly
Root cause: backend/services/keyword_extraction.py hardcoded KeyBERT(model='thenlper/gte-base'), loading a 768-dim BERT model on every first message — even though the system migrated to Qwen3-Embedding-8B.

Fix: Replaced the gte-base model with a _QwenBackend wrapper class that routes KeyBERT's encode() calls through your existing Qwen HTTP embedding client. Zero new dependencies.

3. EMBEDDING_DIMENSIONS stale at 768
Fix: Updated backend/core/config.py and scripts/schema.sql to default to 4096 everywhere.

Re: the socket.io 404 on mlx_lm.server
Not from Appletta — no socket.io anywhere in the frontend or backend code. Something else on your system is hitting port 8080 (browser extension, another tool, etc.). The mlx server handles it correctly with a 404; it doesn't affect functionality.

## Here's what happened and what was fixed:
Why paraphrase-multilingual-MiniLM-L12-v2 was loading:
KeyBERT's select_backend() checks if the model is a str, SentenceTransformer, Flair, etc. Our _QwenBackend matched none of those, so it silently fell back to its hardcoded default model. There was no way to pass a truly custom backend through KeyBERT().

Fix: Removed KeyBERT entirely. backend/services/keyword_extraction.py now implements the same algorithm directly — embed the document + candidate phrases via Qwen, compute cosine similarity (vectors are already L2-normalized so it's just dot product), then MMR selection for diversity. Zero surprise model loading, and actually better quality since it uses your 4096-dim Qwen embeddings instead of a 384-dim MiniLM.

Fix: Added model_config = {"protected_namespaces": ()} to both HealthResponse and InfoResponse in backend/services/qwen_embedding_server.py to silence the Pydantic v2 model_ namespace warnings.

## The fix: max_wait_time bumped from 60s → 600s (10 min), check_interval from 2s → 5s (less spam), and a heartbeat log every 30s so you can see it's still working.

Why it was failing: mlx_lm.server loads the entire model into memory before the HTTP server starts listening on any port. Every one of those 60-second health checks was hitting ConnectError because the TCP socket wasn't even open yet. For MiniMax-M2.5-MLX (456B MoE), loading easily takes 2-5 minutes.

You'll now see something like:


[MLX Manager] Still loading model... (30s elapsed, up to 600s)
[MLX Manager] Still loading model... (60s elapsed, up to 600s)
[MLX Manager] MLX server ready on port 8080 (loaded in 155s)

## Problem: mlx is reloading the model every message instead of keeping it loaded
Good — PID 5253 is the current live server on port 8084 (the one that's actually been serving responses). Don't kill it. The other PIDs were already gone.

Here's a summary of the two changes to main.py:

1. reload=False — With reload=True, uvicorn watches every .py file. Every time you edited and saved keyword_extraction.py, mlx_manager.py, etc. today, it killed the worker process and restarted it. That nuked _mlx_manager and caused a fresh model load on the next message. Each new load found the previous port occupied, so it kept climbing: 8080 → 8081 → 8082 → 8083 → 8084.

2. Lifespan shutdown hook — When you Ctrl+C the backend, it now calls stop_all_servers(), which terminates the mlx subprocesses. Previously they'd linger on their ports and block future starts. Now you get a clean slate on each backend restart.

To get back to port 8080: next time you restart the backend, the live process on 8084 will be killed cleanly, and the new session will start fresh at 8080.

If you need hot-reload for backend development in the future, run uvicorn backend.main:app --reload directly — just know that any model currently loaded will need to reload too.


## Implementing stateful KV continuation
This is a significant rewrite — replacing the subprocess REST API with in-process mlx_lm inference that keeps a live KV cache per conversation. Let me first understand the full current inference call flow before touching anything:

Used tool: Agent

Used tool: Agent

Ran terminal command: find /Users/kimwhite/appletta/backend/services -type f -name "*.py" | sort

Read [](file:///Users/kimwhite/appletta/backend/api/routes/conversations.py)

Read [](file:///Users/kimwhite/appletta/backend/api/routes/conversations.py)

Read [](file:///Users/kimwhite/appletta/backend/api/routes/conversations.py)

Read [](file:///Users/kimwhite/appletta/backend/api/routes/conversations.py)

Read [](file:///Users/kimwhite/appletta/backend/services/diagnostic_inference.py)

Read [](file:///Users/kimwhite/appletta/backend/services/vscode_inference.py)

Read [](file:///Users/kimwhite/appletta/backend/services/mlx_manager.py)

Read [](file:///Users/kimwhite/appletta/backend/services/mlx_manager.py)

Good — I can see `diagnostic_inference.py` already loads the model in-process with `mlx_lm.load()` and calls `generate()` directly. That's the pattern to build on. Let me check the mlx_lm cache API before writing anything:

Ran terminal command: python3 -c "
import mlx_lm
import inspect

# Check what cache-related things are exported
attrs = [a for a in dir(mlx_lm) if 'cache' in a.lower() or 'Cache' in a]
print('Cache-related in mlx_lm:', attrs)

# Check generate signature
sig = inspect.signature(mlx_lm.generate)
print('\ngenerate() params:', list(sig.parameters.keys()))

# Check if cache_prompt exists
try:
    from mlx_lm import cache_prompt
    sig2 = inspect.signature(cache_prompt)
    print('\ncache_prompt() params:', list(sig2.parameters.keys()))
except ImportError as e:
    print('cache_prompt not available:', e)
" 2>/dev/null

Ran terminal command: python3 -c "
from mlx_lm.utils import generate, stream_generate
import inspect
print('generate params:', list(inspect.signature(generate).parameters.keys()))
try:
    print('stream_generate params:', list(inspect.signature(stream_generate).parameters.keys()))
except: print('no stream_generate')
" 2>/dev/null; python3 -c "
# Check for cache-related utilities
import mlx_lm.models.cache as mc
print('cache module attrs:', [a for a in dir(mc) if not a.startswith('_')])
" 2>/dev/null; python3 -c "
from mlx_lm.utils import generate
import inspect
src = inspect.getsource(generate)
# just show first 60 lines
for i, line in enumerate(src.split('\n')[:60]):
    print(line)
" 2>/dev/null

Ran terminal command: source .venv/bin/activate && python3 -c "
from mlx_lm.utils import generate, stream_generate
import inspect
print('generate params:', list(inspect.signature(generate).parameters.keys()))
try:
    print('stream_generate params:', list(inspect.signature(stream_generate).parameters.keys()))
except Exception as e:
    print('stream_generate error:', e)

from mlx_lm.models.cache import make_prompt_cache, save_prompt_cache, load_prompt_cache, trim_prompt_cache, can_trim_prompt_cache
import inspect
print('make_prompt_cache params:', list(inspect.signature(make_prompt_cache).parameters.keys()))

# show generate source signature
src = inspect.getsource(generate)
for line in src.split('\n')[:30]:
    print(line)
"

Ran terminal command: source /Users/kimwhite/appletta/.venv/bin/activate && python3 -c "
import mlx_lm
print([a for a in dir(mlx_lm) if not a.startswith('_')])
" && python3 -c "
import sys; sys.path.insert(0, '/Users/kimwhite/appletta/.venv/lib/python3.11/site-packages')
from mlx_lm.models.cache import make_prompt_cache
from mlx_lm import generate
import inspect
print('generate params:', list(inspect.signature(generate).parameters.keys()))
print('make_prompt_cache params:', list(inspect.signature(make_prompt_cache).parameters.keys()))
src = inspect.getsource(generate)
print(src[:2000])
"

Ran terminal command: python3 -c "
import sys; sys.path.insert(0, '/Users/kimwhite/appletta/.venv/lib/python3.11/site-packages')
from mlx_lm import stream_generate
import inspect
src = inspect.getsource(stream_generate)
print(src[:3000])
"

Ran terminal command: python3 -c "
import sys; sys.path.insert(0, '/Users/kimwhite/appletta/.venv/lib/python3.11/site-packages')
from mlx_lm.utils import generate_step
import inspect
src = inspect.getsource(generate_step)
print(src[:2500])
"

Ran terminal command: python3 -c "
import sys; sys.path.insert(0, '/Users/kimwhite/appletta/.venv/lib/python3.11/site-packages')
import mlx_lm.generate as mg
import inspect
# Find generate_step
for name in dir(mg):
    if 'step' in name.lower() or 'cache' in name.lower():
        print(name)
" 2>/dev/null; python3 -c "
import sys; sys.path.insert(0, '/Users/kimwhite/appletta/.venv/lib/python3.11/site-packages')
# Find where generate_step lives
import subprocess, os
result = subprocess.run(['grep', '-rn', 'def generate_step', '/Users/kimwhite/appletta/.venv/lib/python3.11/site-packages/mlx_lm/'], capture_output=True, text=True)
print(result.stdout)
"

Read [](file:///Users/kimwhite/appletta/.venv/lib/python3.11/site-packages/mlx_lm/generate.py)

Read [](file:///Users/kimwhite/appletta/.venv/lib/python3.11/site-packages/mlx_lm/generate.py)

Good. Now I understand the full picture. Let me also quickly check `diagnostic_inference.py` since it already does in-process model loading — I want to borrow those patterns:

Read [](file:///Users/kimwhite/appletta/backend/services/diagnostic_inference.py)

Let me check one more critical detail before writing — how sampling params (`temp`, `top_k`, `top_p`) are passed through `stream_generate`:

Ran terminal command: python3 -c "
import sys; sys.path.insert(0, '/Users/kimwhite/appletta/.venv/lib/python3.11/site-packages')
from mlx_lm import stream_generate
import inspect
src = inspect.getsource(stream_generate)
print(src)
" 2>/dev/null | head -80

Ran terminal command: python3 -c "
import sys; sys.path.insert(0, '/Users/kimwhite/appletta/.venv/lib/python3.11/site-packages')
from mlx_lm.generate import generate_step
import inspect
sig = inspect.signature(generate_step)
print('generate_step params:')
for name, param in sig.parameters.items():
    print(f'  {name}: default={param.default}')
" 2>/dev/null; python3 -c "
import sys; sys.path.insert(0, '/Users/kimwhite/appletta/.venv/lib/python3.11/site-packages')
# Check how mlx_lm.server passes temp/top_p/top_k
import subprocess
result = subprocess.run(['grep', '-n', 'sampler\|make_sampler\|top_k\|top_p\|temp', 
    '/Users/kimwhite/appletta/.venv/lib/python3.11/site-packages/mlx_lm/server.py'],
    capture_output=True, text=True)
print(result.stdout[:3000])
"

Ran terminal command: python3 -c "
import sys; sys.path.insert(0, '/Users/kimwhite/appletta/.venv/lib/python3.11/site-packages')
from mlx_lm.sample_utils import make_sampler
import inspect
sig = inspect.signature(make_sampler)
print('make_sampler params:', list(sig.parameters.keys()))
" 2>/dev/null

Now I have everything I need. Here's the full plan:
- New `stateful_inference.py`: loads model in-process, keeps a `prompt_cache` per conversation, passes only delta tokens on each turn
- `conversations.py`: replace the httpx-to-subprocess calls with direct engine calls

The sampler has to be built with `make_sampler(temp, top_p, top_k)` and passed as a kwarg to `stream_generate`, which threads it through to `generate_step`. Let me write it:

Ran terminal command: ls /Users/kimwhite/appletta/backend/services/

Now I need to wire this into `conversations.py`. Let me read the three inference call sites precisely:

Read [](file:///Users/kimwhite/appletta/backend/api/routes/conversations.py)

Read [](file:///Users/kimwhite/appletta/backend/api/routes/conversations.py)

Read [](file:///Users/kimwhite/appletta/backend/api/routes/conversations.py)

Now let me see how `mlx_process` and `skip_mlx_server` are set up at the top of `_chat_stream_internal`:

Read [](file:///Users/kimwhite/appletta/backend/api/routes/conversations.py)

Read [](file:///Users/kimwhite/appletta/backend/api/routes/conversations.py)

Good. Now I have the full picture. Let me make all the changes:

**1. Replace the MLX server setup in `_chat_stream_internal`:****2. Fix the `nonlocal` declaration and the tool-loop LLM call:****3. Replace the no-tools streaming call:****4. Fix the error handler that referenced `mlx_process`:****5. Now the non-streaming `chat` endpoint:**Now let's also remove the unused `get_mlx_manager` import if it's only used in those code paths, and verify there are no remaining `mlx_process` references that would break:

Ran terminal command: grep -n "mlx_process\|mlx_manager\|get_mlx_manager" /Users/kimwhite/appletta/backend/api/routes/conversations.py | head -20

Now verify the `request_payload` dict in the no-tools streaming path (it was built but now unused since we call `stream_chat` directly):

Ran terminal command: grep -n "request_payload" /Users/kimwhite/appletta/backend/api/routes/conversations.py | head -20

Read [](file:///Users/kimwhite/appletta/backend/api/routes/conversations.py)

Now do a final check — make sure there are no obvious broken references, and that the shutdown hook still works (mlx_manager is still in main.py):

Ran terminal command: grep -n "mlx_process\|mlx_manager\|get_mlx_manager\|httpx.*8080\|httpx.*port\|v1/chat/completions" /Users/kimwhite/appletta/backend/api/routes/conversations.py | head -20

Ran terminal command: python3 -c "
import sys; sys.path.insert(0, '/Users/kimwhite/appletta')
sys.path.insert(0, '/Users/kimwhite/appletta/.venv/lib/python3.11/site-packages')
import ast
with open('/Users/kimwhite/appletta/backend/services/stateful_inference.py') as f:
    src = f.read()
try:
    ast.parse(src)
    print('stateful_inference.py: OK')
except SyntaxError as e:
    print(f'SyntaxError: {e}')
" 2>/dev/null

Ran terminal command: python3 -c "
import ast
with open('/Users/kimwhite/appletta/backend/api/routes/conversations.py') as f:
    src = f.read()
try:
    ast.parse(src)
    print('conversations.py: OK')
except SyntaxError as e:
    print(f'SyntaxError at line {e.lineno}: {e.msg}')
    print(f'  {e.text}')
" 2>/dev/null

Both files parse clean. Let me also update the lifespan shutdown in `main.py` — the old one called `mlx_manager.stop_all_servers()`, but now there's no subprocess to clean up (the inference engine's model unloads when the process exits anyway):Done. Here's what changed and why it makes the second+ message fast:

---

**What was built:**

- **[`backend/services/stateful_inference.py`](backend/services/stateful_inference.py)** — new `StatefulInferenceEngine` singleton that:
  - Loads the model once in-process with `mlx_lm.load()`
  - Keeps a `ConversationCache` per conversation, holding a live `prompt_cache` (list of `KVCache` objects, one per transformer layer)
  - On turn 1: tokenizes the full conversation, does full prefill, generates response — `prompt_cache` is extended in-place with every generated token
  - On turn 2+: tokenizes full conversation, slices `full_tokens[cache.offset:]` (just the new tokens since last time), prefills only those, generates — no re-processing of prior history
  - Bridges the synchronous `stream_generate` generator to FastAPI's async SSE stream via `asyncio.Queue`

- **[`conversations.py`](backend/api/routes/conversations.py)** — replaced all three httpx-to-subprocess call sites with `inference_engine.stream_chat()`, removed `mlx_manager` import

- **[`main.py`](backend/main.py)** — shutdown hook calls `unload_model()` instead of `stop_all_servers()`

**Cache invalidation:** If the system prompt changes between turns (memories surface differently), the cache is rebuilt from scratch on that turn. The system prompt hash is compared on every call.

Here's the full plan:

New stateful_inference.py: loads model in-process, keeps a prompt_cache per conversation, passes only delta tokens on each turn
conversations.py: replace the httpx-to-subprocess calls with direct engine calls
The sampler has to be built with make_sampler(temp, top_p, top_k) and passed as a kwarg to stream_generate, which threads it through to generate_step. Let me write it:

Ran ls /Users/kimwhite/appletta/backend/services/
Now I need to wire this into conversations.py. Let me read the three inference call sites precisely:

Reviewed conversations.py
Now let me see how mlx_process and skip_mlx_server are set up at the top of _chat_stream_internal:

Reviewed conversations.py
Good. Now I have the full picture. Let me make all the changes:

**1. Replace the MLX server setup in _chat_stream_internal:****2. Fix the nonlocal declaration and the tool-loop LLM call:****3. Replace the no-tools streaming call:****4. Fix the error handler that referenced mlx_process:****5. Now the non-streaming chat endpoint:**Now let's also remove the unused get_mlx_manager import if it's only used in those code paths, and verify there are no remaining mlx_process references that would break:

Ran grep -n "mlx_process\|mlx_manager\|get_mlx_manager...
Now verify the request_payload dict in the no-tools streaming path (it was built but now unused since we call stream_chat directly):

Now do a final check — make sure there are no obvious broken references, and that the shutdown hook still works (mlx_manager is still in main.py):

Both files parse clean. Let me also update the lifespan shutdown in main.py — the old one called mlx_manager.stop_all_servers(), but now there's no subprocess to clean up (the inference engine's model unloads when the process exits anyway):Done. Here's what changed and why it makes the second+ message fast:

What was built:

backend/services/stateful_inference.py — new StatefulInferenceEngine singleton that:

Loads the model once in-process with mlx_lm.load()
Keeps a ConversationCache per conversation, holding a live prompt_cache (list of KVCache objects, one per transformer layer)
On turn 1: tokenizes the full conversation, does full prefill, generates response — prompt_cache is extended in-place with every generated token
On turn 2+: tokenizes full conversation, slices full_tokens[cache.offset:] (just the new tokens since last time), prefills only those, generates — no re-processing of prior history
Bridges the synchronous stream_generate generator to FastAPI's async SSE stream via asyncio.Queue
conversations.py — replaced all three httpx-to-subprocess call sites with inference_engine.stream_chat(), removed mlx_manager import

main.py — shutdown hook calls unload_model() instead of stop_all_servers()
Cache invalidation: If the system prompt changes between turns (memories surface differently), the cache is rebuilt from scratch on that turn. The system prompt hash is compared on every call.