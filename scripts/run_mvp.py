from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import run_mvp
from app.models.config import TargetRules
from app.models.pokemon import Pokemon


def main() -> None:
    summary = run_mvp(
        target_pokemon=[Pokemon.PIKACHU, Pokemon.CHARIZARD, Pokemon.GENGAR],
        target_rules=TargetRules(
            allowed_grades={"9", "10"},
            max_current_price=1500.0,
        ),
        dry_run=True,
    )

    print(
        json.dumps(
            summary.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()

