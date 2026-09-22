#!/usr/bin/env bash
# Copy the add-on's dashboard (single source of truth) into public/ for the Vercel deployment.
set -euo pipefail
cd "$(dirname "$0")"
rm -rf public && mkdir -p public
cp -R ../grow_brain/grow_brain/web/. public/
printf 'User-agent: *\nDisallow: /\n' > public/robots.txt
echo "synced $(find public -type f | wc -l | tr -d ' ') files into public/"
