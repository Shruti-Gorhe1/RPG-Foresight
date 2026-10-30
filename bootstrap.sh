#!/usr/bin/env bash
# Thin wrapper around bootstrap.py — passes all args through.
#   ./bootstrap.sh --name payment-insights
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/bootstrap.py" "$@"
