import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


PAPER_FIELDS = [
    "paper_id", "symbol", "setup_family", "timeframe", "signal_date",
    "entry_price", "stop_loss", "target_1", "target_2", "target_3",
    "status", "opened_at", "closed_at", "exit_price", "exit_reason",
    "return_r", "notes", "strategy_version",
]


def open_from_scan(scan_path: str, ledger_path: str) -> int:
    """Copy confirmed/watch candidates into a paper ledger, deduplicated by signal."""
    ledger = Path(ledger_path)
    existing = {}
    if ledger.exists():
        with ledger.open(newline="") as handle:
            for row in csv.DictReader(handle):
                existing[row["paper_id"]] = row
    with Path(scan_path).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        if row.get("status") not in {"watch", "triggered"}:
            continue
        paper_id = "|".join([row["symbol"], row["timeframe"], row["setup_family"], row["signal_date"]])
        if paper_id in existing:
            continue
        existing[paper_id] = {
            "paper_id": paper_id, "symbol": row["symbol"], "setup_family": row["setup_family"],
            "timeframe": row["timeframe"], "signal_date": row["signal_date"],
            "entry_price": row["entry_price"], "stop_loss": row["stop_loss"],
            "target_1": row["target_1"], "target_2": row["target_2"], "target_3": row["target_3"],
            "status": "OPEN", "opened_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "closed_at": "", "exit_price": "", "exit_reason": "", "return_r": "",
            "notes": "", "strategy_version": row.get("strategy_version", ""),
        }
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAPER_FIELDS)
        writer.writeheader(); writer.writerows(existing.values())
    return len(existing)


def close_trade(ledger_path: str, paper_id: str, exit_price: float, reason: str, notes: str = "") -> None:
    path = Path(ledger_path)
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    found = False
    for row in rows:
        if row["paper_id"] == paper_id:
            risk = float(row["entry_price"]) - float(row["stop_loss"])
            row["status"] = "CLOSED"; row["closed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            row["exit_price"] = str(exit_price); row["exit_reason"] = reason
            row["return_r"] = str(round((exit_price - float(row["entry_price"])) / risk, 3)) if risk else "0"
            row["notes"] = notes; found = True
    if not found:
        raise KeyError("Unknown paper trade: " + paper_id)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PAPER_FIELDS); writer.writeheader(); writer.writerows(rows)
