#!/usr/bin/env sh
# Entry point for both the HA add-on and the standalone container.
set -e
cd /app
exec python -m grow_brain.main
