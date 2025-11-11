# Appletta Quick Start

## Step 1: Set up PostgreSQL Database

```bash
# Run the automated setup script
chmod +x scripts/setup_postgres_macos.sh
./scripts/setup_postgres_macos.sh

# Apply the database schema
psql appletta < scripts/schema.sql
```

**What this does:**
- Installs PostgreSQL 16 via Homebrew
- Installs pgvector extension for embeddings
- Creates the `appletta` database
- Enables required extensions (vector, pg_trgm, uuid-ossp)
- Creates all tables, indexes, and views

## Step 2: Test Database Connection

```bash
# Run the test suite
python3 scripts/test_database.py
```

You should see all tests passing ✅

## Step 3: Install Backend Dependencies

```bash
cd backend
pip3 install -r requirements.txt
```

This installs:
- FastAPI + Uvicorn
- SQLAlchemy + psycopg2 (PostgreSQL driver)
- pgvector Python library
- Pydantic for validation

## Step 4: Start the Backend

```bash
python3 -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be running at:
- API: http://localhost:8000
- Docs: http://localhost:8000/docs

## Step 5: Start the Frontend

```bash
# In a new terminal
cd frontend
npm run dev
```

Frontend will be running at:
- http://localhost:5173

## Verify Everything Works

1. Open http://localhost:8000/docs
2. Try the `/health` endpoint - should return `{"status": "healthy"}`
3. Try `GET /api/v1/agents` - should return the default agent
4. Open http://localhost:5173 - frontend should load

## Next Steps

Now you're ready to build the RAG Filesystem and Search features! 🚀

## Troubleshooting

**Database connection fails:**
```bash
# Check PostgreSQL is running
brew services list | grep postgresql

# Should show "started" - if not:
brew services start postgresql@16
```

**Tables don't exist:**
```bash
# Reapply schema
psql appletta < scripts/schema.sql
```

**Import errors:**
```bash
# Make sure you're in the repo root
cd /path/to/appletta

# Run with python module syntax
python3 -m uvicorn backend.main:app --reload
```

For detailed troubleshooting, see [DATABASE_SETUP.md](DATABASE_SETUP.md)
