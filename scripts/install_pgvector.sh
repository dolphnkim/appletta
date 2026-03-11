#!/bin/bash
# Quick fix to install pgvector if PostgreSQL is already running
#
# NOTE: brew's pgvector formula now targets PostgreSQL 17/18.
# If you're on PostgreSQL 16, build from source using this script.
# After a PostgreSQL upgrade (e.g. 16.10 -> 16.13), re-run this script
# so the vector.dylib is rebuilt for the new version.

echo "Installing pgvector extension..."

# Clone and build pgvector
TMP_DIR=$(mktemp -d)
cd "$TMP_DIR"

echo "Downloading pgvector..."
git clone --branch v0.8.1 https://github.com/pgvector/pgvector.git
cd pgvector

echo "Building pgvector..."
make

echo "Installing pgvector..."
sudo make install

cd ~
rm -rf "$TMP_DIR"

echo "✅ pgvector installed!"
echo ""
echo "Now you can run:"
echo "  psql appletta < scripts/schema.sql"
