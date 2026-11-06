#!/usr/bin/env bash
# Apply .github/rulesets/main.json to this repository (needs admin rights and the GitHub CLI, `gh auth login`).
#   GitHub Actions (integration 15368) may still push to main: the verify, papers and proposals workflows commit
#   evidence and applied proposals there. Repository admins may bypass only through a pull request (so the owner
#   can merge their own pull request). Everyone else needs the code owner's review for the paths in CODEOWNERS.
# Without the CLI: Settings -> Rules -> Rulesets -> New ruleset -> Import a ruleset, and pick the JSON file.
set -euo pipefail
repo="${1:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}"
existing=$(gh api "repos/$repo/rulesets" -q '.[] | select(.name | startswith("main: verifier paths")) | .id' || true)
if [ -n "$existing" ]; then
  gh api -X PUT "repos/$repo/rulesets/$existing" --input "$(dirname "$0")/../.github/rulesets/main.json" >/dev/null
  echo "updated ruleset $existing on $repo"
else
  gh api -X POST "repos/$repo/rulesets" --input "$(dirname "$0")/../.github/rulesets/main.json" >/dev/null
  echo "created the ruleset on $repo"
fi
