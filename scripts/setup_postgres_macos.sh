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
echo "⏳ Waiting for PostgreSQL to start..."
sleep 5

# Create database
echo "🗄️  Creating appletta database..."
createdb appletta || echo "Database might already exist, continuing..."

# Install pgvector from source (brew package doesn't work properly)
echo "📦 Installing pgvector extension from source..."
echo "   This will take a minute..."

# Clone and build pgvector
TMP_DIR=$(mktemp -d)
cd "$TMP_DIR"

git clone --branch v0.7.4 https://github.com/pgvector/pgvector.git
cd pgvector

# Build and install
make
make install # This installs to the PostgreSQL extensions directory

cd ~
rm -rf "$TMP_DIR"

# Connect and enable extensions
echo "🔌 Enabling extensions..."
psql appletta << EOF
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;
\q
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ PostgreSQL setup complete!"
    echo ""
    echo "Database: appletta"
    echo "Connection string: postgresql://$(whoami)@localhost/appletta"
    echo ""
    echo "Next steps:"
    echo "  1. Apply schema: psql appletta < scripts/schema.sql"
    echo "  2. Test: python3 scripts/test_database.py"
    echo ""
else
    echo ""
    echo "❌ Setup failed. See errors above."
    exit 1
fi
