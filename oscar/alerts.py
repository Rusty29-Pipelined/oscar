import json
from typing import Dict


def format_alert(candidate: Dict[str, str]) -> str:
    """Create a human-review alert. This function never places an order."""
    return (f"OSCAR {candidate.get('status', 'SIGNAL')}: {candidate['symbol']} "
            f"{candidate['timeframe']} {candidate['setup_family']} | "
            f"Entry {candidate['entry_price']} | SL {candidate['stop_loss']} | "
            f"T1 {candidate['target_1']} T2 {candidate['target_2']} T3 {candidate['target_3']} | "
            f"R:R {candidate.get('risk_reward_t1', '?')} | {candidate.get('reason_codes', '')}")


def write_alerts(scan_path: str, output_path: str) -> int:
    import csv
    from pathlib import Path
    with Path(scan_path).open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    alerts = [format_alert(row) for row in rows if row.get("status") in {"triggered", "watch"}]
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("\n".join(alerts) + ("\n" if alerts else ""))
    return len(alerts)
