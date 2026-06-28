#!/bin/bash
# Entry point for the kimbir.export-and-deploy-kbi-work-calendar launchd job.
#
# Deliberately a bash script, NOT pwsh: launchd attributes Calendar (TCC)
# access to the responsible process, and pwsh's TCC grant is unreliable under
# launchd (stale cdhash, no GUI to re-prompt) which silently denies the Swift
# EventKit binary. bash is an Apple platform binary and is transparent to TCC,
# so access falls through to the EventKit binary's own grant. pwsh is still used
# for Slack error reporting only, which does not touch Calendar.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PWSH="/usr/local/microsoft/powershell/7/pwsh"
PROFILE_DIR="/Users/kimbirkelund/code/profile/powershell"
SLACK_SCRIPT="$PROFILE_DIR/New-SlackMessage.ps1"
CREDS_MODULE="$PROFILE_DIR/Modules/credentials/credentials.psm1"
ERR_LOG="/tmp/kimbir.export-and-deploy-kbi-work-calendar.err"

notify_slack() {
    # Send via the user's New-SlackMessage.ps1. The credentials module is
    # imported explicitly so its default -WebhookUrl (Get-Credentials) resolves
    # without loading the whole profile. Message passed via env to dodge quoting.
    SLACK_MSG="$1" "$PWSH" -NoProfile -Command \
        "Import-Module '$CREDS_MODULE'; & '$SLACK_SCRIPT' -Message \$env:SLACK_MSG" \
        || echo "WARNING: failed to send Slack notification" >&2
}

on_error() {
    local exit_code=$?
    local line=$1
    local tail
    tail="$(grep -vE 'CryptographyDeprecation|TripleDES|cipher|class' "$ERR_LOG" 2>/dev/null | tail -n 15)"
    notify_slack ":x: *export-and-deploy-kbi-work-calendar* failed on $(hostname -s) (exit ${exit_code}, line ${line}).
Last log lines:
\`\`\`
${tail}
\`\`\`"
    exit "$exit_code"
}
trap 'on_error $LINENO' ERR

# 1. Recreate the output directory.
rm -rf page
mkdir -p page

# 2. Export the calendar to page/ (Swift EventKit via python; no pwsh in chain).
./setup-and-run.sh --no-interactive

# 3. Deploy to Vercel. The vercel CLI emits spinner/cursor-control escape
# sequences on stderr even under CI/NO_COLOR; strip them so the log stays plain
# text. Filtering only stderr via process substitution leaves npx's exit status
# (and the ERR trap) intact.
cd page
export PATH="/opt/homebrew/bin:$PATH"
export CI=1
export NO_COLOR=1
npx --yes vercel@latest --yes --prod \
    2> >(sed -E $'s/\x1b\\[[0-9;?]*[a-zA-Z]//g' >&2)
