# QSA — Qualitative Signal Audit

> **AFT platform context.** This repo is one tool in **AFT** (AI Finance Testbed),
> a personal, advisory-only financial data & research platform (it never trades).
> Pipeline: Bronze (MDC→MASD) → Silver (UDC→SHDB/mart) → Gold (RSE) → derived (DAS)
> → application streams (IRA Guard, MEF, GDE, cc2, TIDE, CIA, JRA) → ops (Overwatch);
> QSA audits data quality. Each tool owns one database and writes only that one;
> SHDB is read-only to consumers; advisory only.
>
> **Where this tool sits + what every tool reads/writes →** the canonical catalog
> `~/repos/aft-platform/docs/platform/aft_tools_overview.md`. Platform-wide *behavior*
> rules live in `~/repos/aft-platform/CLAUDE.md` (auto-loaded as a parent of this
> file). System-wide docs: `~/repos/aft-platform/docs/`.

For this tool's internals see its `docs/` and `README`; for its place in the platform see the canonical catalog linked above.
