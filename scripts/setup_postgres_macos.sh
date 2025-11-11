#!/bin/bash
# PostgreSQL + pgvector setup for Appletta on macOS

echo "🍎 Setting up PostgreSQL with pgvector for Appletta..."
echo ""

# Check if Homebrew is installed
if ! command -v brew &> /dev/null; then
    echo "❌ Homebrew not found. Please install from https://brew.sh"
    exit 1
fi

# Install PostgreSQL
echo "📦 Installing PostgreSQL..."
brew install postgresql@16

# Start PostgreSQL service
echo "🚀 Starting PostgreSQL service..."
brew services start postgresql@16

# Wait for PostgreSQL to start
sleep 3

# Create database
echo "🗄️  Creating appletta database..."
createdb appletta

# Install pgvector extension
echo "📦 Installing pgvector extension..."
brew install pgvector

# Connect and enable pgvector
echo "🔌 Enabling pgvector extension..."
psql appletta << EOF
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- For fuzzy text search
CREATE EXTENSION IF NOT EXISTS btree_gin; -- For faster text search
\q
EOF

echo ""
echo "✅ PostgreSQL setup complete!"
echo ""
echo "Database: appletta"
echo "Connection string: postgresql://$(whoami)@localhost/appletta"
echo ""
echo "To connect manually:"
echo "  psql appletta"
echo ""
echo "To stop PostgreSQL:"
echo "  brew services stop postgresql@16"
