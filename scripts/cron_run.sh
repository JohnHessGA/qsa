#!/usr/bin/env bash
# QSA cron entry point. Pure plumbing.
# See ~/repos/aft-platform/docs/conventions/cron-conventions.md.
set -euo pipefail
mkdir -p /mnt/aftdata/logs/qsa
cd /home/johnh/repos/qsa
source .venv/bin/activate
exec qsa "$@"
