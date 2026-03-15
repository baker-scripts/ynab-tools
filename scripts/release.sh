#!/bin/bash
set -euo pipefail

# Local release automation:
# 1. Push to trigger CI/CD
# 2. Wait for workflow completion
# 3. Pull new version tag
# 4. Update compose references

readonly REPO="baker-scripts/ynab-tools"
readonly BRANCH="main"

echo "=== Pushing to ${BRANCH}..."
git push origin "${BRANCH}"

echo "=== Waiting for CI workflow..."
gh run watch --repo "${REPO}" --exit-status

echo "=== Waiting for Release workflow..."
sleep 5
gh run watch --repo "${REPO}" --exit-status

echo "=== Pulling tags..."
git fetch --tags

LATEST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "none")
echo "=== Latest version: ${LATEST_TAG}"

echo "=== Done. Update compose files with version: ${LATEST_TAG}"
