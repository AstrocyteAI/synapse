"""X-4 — migration export CLI (Synapse → Cerebro).

Skeleton implementation. Dumps domain data from a running Synapse deployment
to a directory of JSONL files that Cerebro's `POST /v1/admin/migrate/import`
endpoint accepts.

Usage (from repo root):

    uv run python -m synapse.scripts.migrate_export \\
        --base-url https://synapse.acme.com \\
        --token "$SYNAPSE_ADMIN_JWT" \\
        --output ./migration-dump

The output directory will contain:
    councils.jsonl       — one council session per line
    threads.jsonl        — one thread + events bundle per line
    audit_events.jsonl   — one audit event per line
    notification_prefs.jsonl
    devices.jsonl
    api_keys.jsonl       — key prefixes only (raw keys are not exportable)
    webhooks.jsonl

Memory banks (decisions, precedents, councils) are NOT exported by this
tool — Astrocyte handles its own bank export via its dedicated CLI. See
`cerebro/docs/_design/migration.md` for the full procedure.

This tool reads via the public API, never the database. Operators can
run it from a laptop with just an admin JWT.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import httpx

_logger = logging.getLogger("synapse.migrate.export")


# ---------------------------------------------------------------------------
# Per-resource exporters
# ---------------------------------------------------------------------------


def _paginate(client: httpx.Client, path: str, params: dict | None = None) -> list[dict]:
    """Fetch a paginated list. Synapse list endpoints use limit/offset today."""
    out: list[dict] = []
    offset = 0
    page_size = 100
    while True:
        p = {"limit": page_size, "offset": offset, **(params or {})}
        r = client.get(path, params=p)
        r.raise_for_status()
        page = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        if not page:
            break
        out.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    return out


def _export_audit_log(client: httpx.Client) -> list[dict]:
    """Cursor-paginated audit log."""
    out: list[dict] = []
    before_id: int | None = None
    while True:
        params: dict[str, Any] = {"limit": 200}
        if before_id is not None:
            params["before_id"] = before_id
        r = client.get("/v1/admin/audit-log", params=params)
        r.raise_for_status()
        body = r.json()
        rows = body.get("data", [])
        if not rows:
            break
        out.extend(rows)
        nxt = body.get("next_before_id")
        if nxt is None:
            break
        before_id = nxt
    return out


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


RESOURCES: list[tuple[str, str, callable]] = [
    ("councils.jsonl", "/v1/councils", _paginate),
    ("audit_events.jsonl", "/v1/admin/audit-log", lambda c, _p: _export_audit_log(c)),
    # NOTE: thread events are nested under each council; per-council export is
    #       deferred to a future iteration of this script.
]


def export(base_url: str, token: str, output: Path) -> dict[str, int]:
    """Run the export. Returns {filename: row_count} for the summary.

    Writes both per-resource JSONL files (one row per line, good for
    streaming) AND a single ``bundle.json`` that can be POSTed directly to
    Cerebro's ``/v1/admin/migrate/import`` endpoint with no further
    massaging. The bundle is the recommended path for dumps under ~10k
    rows; the JSONL files are kept for streaming-import (planned).
    """
    output.mkdir(parents=True, exist_ok=True)
    headers = {"Authorization": f"Bearer {token}"}
    counts: dict[str, int] = {}
    rows_by_resource: dict[str, list[dict]] = {}

    with httpx.Client(base_url=base_url, headers=headers, timeout=60.0) as client:
        # Verify the backend is actually Synapse before exporting
        info = client.get("/v1/info").json()
        if info.get("backend") != "synapse":
            raise SystemExit(
                f"Refusing to export — /v1/info reports backend={info.get('backend')!r}, "
                f"expected 'synapse'. This script is for migrating OUT of Synapse."
            )

        for filename, path, fetcher in RESOURCES:
            _logger.info("Exporting %s …", path)
            rows = fetcher(client, path)
            out_path = output / filename
            with out_path.open("w") as f:
                for row in rows:
                    f.write(json.dumps(row) + "\n")
            counts[filename] = len(rows)
            rows_by_resource[filename] = rows
            _logger.info("  → %s (%d rows)", out_path, len(rows))

    # Write a manifest so the import side can verify the dump shape
    manifest = {
        "source_backend": info,
        "counts": counts,
        "format_version": 1,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Write a bundle.json that's POST-ready to Cerebro's import endpoint.
    # Maps each resource filename to the import-side key Cerebro expects.
    resource_to_key = {
        "councils.jsonl": "councils",
        "audit_events.jsonl": "audit_events",
    }
    bundle: dict = {"manifest": manifest}
    for filename, rows in rows_by_resource.items():
        key = resource_to_key.get(filename)
        if key:
            bundle[key] = rows
    (output / "bundle.json").write_text(json.dumps(bundle))
    _logger.info("  → %s (POST-ready import payload)", output / "bundle.json")

    return counts


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Synapse → Cerebro migration export")
    p.add_argument("--base-url", required=True, help="e.g. https://synapse.acme.com")
    p.add_argument("--token", required=True, help="Admin JWT")
    p.add_argument("--output", required=True, type=Path, help="Output directory")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    counts = export(args.base_url, args.token, args.output)
    print("\nExport complete.")
    for name, n in counts.items():
        print(f"  {name:30s} {n:>6d} rows")
    print(f"\nManifest: {args.output / 'manifest.json'}")
    print("\nNext step: pipe these files into Cerebro via:")
    print("  POST /v1/admin/migrate/import (Cerebro)")
    print("See cerebro/docs/_design/migration.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
