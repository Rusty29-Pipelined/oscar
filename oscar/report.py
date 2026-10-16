import csv
from pathlib import Path
from typing import Iterable
from .models import Candidate


FIELDS = list(Candidate.__dataclass_fields__)


def write_csv(candidates: Iterable[Candidate], path: str) -> None:
    rows = [c.row() for c in candidates]
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
