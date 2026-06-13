#!/usr/bin/env bash
# QSA cron entry point. Pure plumbing.
# Owns the `audit` subcommand so the crontab line stays a bare wrapper call;
# any extra args (e.g. --rules, --csv) are still forwarded.
# See ~/repos/aft-platform/docs/conventions/cron-conventions.md.
set -euo pipefail
mkdir -p /mnt/aftdata/logs/qsa
cd /home/johnh/repos/qsa
source .venv/bin/activate
exec qsa audit "$@"
