#!/usr/bin/env python3
"""
DOE orchestration script for the Saunagus market analysis workflow.
Runs scrapers, builds the report, and optionally exports an Excel-friendly file.
"""
import argparse
import csv
import json
import sqlite3
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_REPORT_DAYS = 90


def load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_path(path_value: str, repo_root: Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else (repo_root / path).resolve()


def run_step(cmd: List[str], cwd: Path, label: str) -> int:
    print(f"[orchestrator] {label}: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=False, cwd=cwd)
    except Exception as exc:  # noqa: BLE001
        print(f"[orchestrator] {label} failed: {exc}")
        return 1
    if result.returncode != 0:
        print(f"[orchestrator] {label} exited with code {result.returncode}")
    return result.returncode


def summarize_providers(config: Dict[str, Any]) -> None:
    providers = config.get("providers", []) or []
    enabled = [p for p in providers if p.get("enabled", True)]
    print(
        "[orchestrator] providers:",
        f"{len(providers)} total, {len(enabled)} enabled",
    )


def export_sessions_csv(conn: sqlite3.Connection, output_path: Path) -> None:
    cursor = conn.execute("SELECT * FROM sessions")
    columns = [col[0] for col in cursor.description]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in cursor:
            writer.writerow(row)
    print(f"[orchestrator] wrote CSV export: {output_path}")


def export_sessions_excel(db_path: Path, output_path: Path, csv_fallback: Path) -> None:
    if not db_path.exists():
        print(f"[orchestrator] database not found: {db_path}")
        return
    try:
        import pandas as pd  # type: ignore[import-not-found]
    except Exception:
        print("[orchestrator] pandas not available; exporting CSV instead.")
        conn = sqlite3.connect(db_path)
        try:
            export_sessions_csv(conn, csv_fallback)
        finally:
            conn.close()
        return

    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query("SELECT * FROM sessions", conn)
    finally:
        conn.close()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_path, index=False)
    print(f"[orchestrator] wrote Excel export: {output_path}")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    default_config = repo_root / "data" / "reference" / "config.json"
    default_report = repo_root / "outputs" / "reports" / "report.html"
    default_db = repo_root / "data" / "db" / "lasauna.sqlite"
    default_excel = repo_root / "outputs" / "excel" / "sessions.xlsx"
    default_csv = repo_root / "outputs" / "excel" / "sessions.csv"

    parser = argparse.ArgumentParser(
        description="Orchestrate scraping and reporting for the Saunagus market analysis."
    )
    parser.add_argument(
        "--config",
        default=str(default_config),
        help="Path to config.json.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Override report days (defaults to config report_days).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Override report output path (defaults to config report_output_path).",
    )
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Skip YOGO scraping step.",
    )
    parser.add_argument(
        "--skip-non-yogo",
        action="store_true",
        help="Skip non-YOGO scrapers.",
    )
    parser.add_argument(
        "--skip-report",
        action="store_true",
        help="Skip report generation.",
    )
    parser.add_argument(
        "--export-excel",
        action="store_true",
        help="Export sessions to outputs/excel (xlsx if pandas is available).",
    )
    parser.add_argument(
        "--excel-output",
        default=str(default_excel),
        help="Excel output path (only used with --export-excel).",
    )
    parser.add_argument(
        "--csv-output",
        default=str(default_csv),
        help="CSV fallback path when pandas is unavailable.",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the report in a browser.",
    )
    args = parser.parse_args()

    config_path = Path(args.config).expanduser()
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()

    config = load_config(config_path)
    summarize_providers(config)

    report_days = int(args.days or config.get("report_days", DEFAULT_REPORT_DAYS))
    report_output = args.output or config.get("report_output_path", str(default_report))
    report_output_path = resolve_path(report_output, repo_root)

    scraper_script = repo_root / "execution" / "scrapers" / "lasauna_scraper.py"
    non_yogo_script = repo_root / "execution" / "scrapers" / "non_yogo_scraper.py"
    report_script = repo_root / "execution" / "scrapers" / "report.py"

    exit_code = 0
    if not args.skip_scrape:
        exit_code |= run_step(
            [sys.executable, str(scraper_script), "--config", str(config_path)],
            repo_root,
            "scrape (yogo)",
        )
        if not args.skip_non_yogo:
            if non_yogo_script.exists():
                exit_code |= run_step(
                    [sys.executable, str(non_yogo_script), "--config", str(config_path)],
                    repo_root,
                    "scrape (non-yogo)",
                )
            else:
                print(f"[orchestrator] non-yogo scraper not found: {non_yogo_script}")

    if not args.skip_report:
        report_output_path.parent.mkdir(parents=True, exist_ok=True)
        exit_code |= run_step(
            [
                sys.executable,
                str(report_script),
                "--config",
                str(config_path),
                "--days",
                str(report_days),
                "--output",
                str(report_output_path),
            ],
            repo_root,
            "report",
        )

    if args.export_excel:
        db_path = resolve_path(str(config.get("output_db_path", default_db)), repo_root)
        export_sessions_excel(
            db_path,
            resolve_path(args.excel_output, repo_root),
            resolve_path(args.csv_output, repo_root),
        )

    if not args.no_open:
        if report_output_path.exists():
            webbrowser.open(report_output_path.resolve().as_uri())
            print(f"[orchestrator] opened report: {report_output_path}")
        else:
            print(f"[orchestrator] report not found: {report_output_path}")

    return 0 if exit_code == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
