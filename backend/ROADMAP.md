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