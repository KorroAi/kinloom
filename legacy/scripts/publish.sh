#!/usr/bin/env bash
# Outward-facing steps, prepared but NOT run by Claude: each one needs the user's explicit approval.
# Usage (Git Bash, from the kinloom folder):
#   scripts/publish.sh github   # create a PRIVATE GitHub repo "kinloom" and push main
#   scripts/publish.sh site     # deploy site/ to Vercel (production URL is public)
#   scripts/publish.sh check    # run every test before publishing anything
set -euo pipefail
cd "$(dirname "$0")/.."

check() {
  dotnet build -warnaserror --no-incremental
  dotnet test
  python -m unittest discover -s docs/phase0b
  dotnet run --project src/Kinloom.Sim -- scenarios/village.json packs/medieval.pack.json out/village --publish site
  git diff --quiet -- site/demo.html || { echo "site/demo.html changed: commit it before publishing"; exit 1; }
}

case "${1:-}" in
  check)
    check
    ;;
  github)
    check
    if git remote get-url origin >/dev/null 2>&1; then
      echo "Remote 'origin' already exists: $(git remote get-url origin)"
    else
      gh repo create kinloom --private --source . --remote origin
    fi
    git push -u origin main
    ;;
  site)
    check
    if grep -q 'KINLOOM_WAITLIST_URL = ""' site/config.js; then
      echo "Note: no waitlist URL in site/config.js — the page will show 'Waitlist opens soon'."
    fi
    vercel deploy site --prod --yes
    ;;
  *)
    echo "Usage: scripts/publish.sh check | github | site"
    exit 2
    ;;
esac
