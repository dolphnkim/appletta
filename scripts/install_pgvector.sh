#!/bin/bash
# Quick fix to install pgvector if PostgreSQL is already running

echo "🔧 Installing pgvector extension..."

# Clone and build pgvector
TMP_DIR=$(mktemp -d)
cd "$TMP_DIR"

echo "📥 Downloading pgvector..."
git clone --branch v0.7.4 https://github.com/pgvector/pgvector.git
cd pgvector

echo "🔨 Building pgvector..."
make

echo "📦 Installing pgvector..."
sudo make install

cd ~
rm -rf "$TMP_DIR"

echo "✅ pgvector installed!"
echo ""
echo "Now you can run:"
echo "  psql appletta < scripts/schema.sql"
