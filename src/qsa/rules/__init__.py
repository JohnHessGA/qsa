"""Validation rule library for QSA.

Each rule exposes a single function with the signature

    def check(*, masd, shdb, mefdb, app_cfg) -> list[Finding]

where the `*_conn` arguments are open psycopg2 connections (read-only).
The audit orchestrator opens connections once and passes them to every
rule, then aggregates findings.
"""

from qsa.rules.invalid_timestamps import check as check_invalid_timestamps
from qsa.rules.future_dates import check as check_future_dates
from qsa.rules.missing_symbols import check as check_missing_symbols
from qsa.rules.duplicate_keys import check as check_duplicate_keys
from qsa.rules.orphans import check as check_orphans
from qsa.rules.staleness import check as check_staleness
from qsa.rules.deprecated import check as check_deprecated
from qsa.rules.mef_coverage import check as check_mef_coverage
from qsa.rules.thin_coverage import check as check_thin_coverage

ALL_RULES = [
    ("R001-invalid-timestamps", check_invalid_timestamps),
    ("R002-future-dates",       check_future_dates),
    ("R003-missing-symbols",    check_missing_symbols),
    ("R004-duplicate-keys",     check_duplicate_keys),
    ("R005-orphan-rows",        check_orphans),
    ("R006-staleness",          check_staleness),
    ("R007-deprecated-tables",  check_deprecated),
    ("R008-mef-coverage",       check_mef_coverage),
    ("R009-thin-coverage",      check_thin_coverage),
]
