"""Shared helpers for the DCA alert engine."""
import datetime as dt
import json
import pathlib

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
PRICES_DIR = DATA_DIR / "prices"
STATE_PATH = DATA_DIR / "state.json"
STOCKS_PATH = CONFIG_DIR / "stocks.yaml"
RULES_PATH = CONFIG_DIR / "rules.yaml"
RUNG_NOTES_PATH = CONFIG_DIR / "rung_notes.yaml"


def load_yaml(path: pathlib.Path) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_stocks() -> list:
    return load_yaml(STOCKS_PATH)["stocks"]


def load_rules() -> dict:
    return load_yaml(RULES_PATH)


def load_rung_notes() -> dict:
    if not RUNG_NOTES_PATH.exists():
        return {}
    return load_yaml(RUNG_NOTES_PATH).get("notes") or {}


def normalize_rung_id(rung_id: str | None) -> str | None:
    """Canonicalise a cluster rung id so notes survive MA crossings.

    A merged-support rung is named after its MAs in whatever order they
    ranked that day: MA200 above MA100 gives "ma-200+100", and the moment
    those two cross it becomes "ma-100+200" -- the same support level, a
    different string, so a note keyed on the old spelling would silently
    stop showing. Sorting the periods makes both spellings collapse to one
    key. Non-MA ids ("rung-drop-1", "custom-...") pass through untouched.

    Note this only fixes *ordering*. If MA100 drifts within cluster_merge_pct
    of MA200 the two separate rungs "ma-200"/"ma-100" become one
    "ma-200+100", which is a genuinely different rung and is left alone --
    build_dashboard.py warns about those so the key can be re-pointed by hand.
    """
    if not rung_id or not rung_id.startswith("ma-"):
        return rung_id
    parts = rung_id[3:].split("+")
    if not all(part.isdigit() for part in parts):
        return rung_id
    return "ma-" + "+".join(sorted(parts, key=int))


def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    return {"generated_at": None, "stocks": {}}


def save_state(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True, default=str)
        f.write("\n")


def period_key(tier_refresh: str, as_of: dt.date) -> str:
    """Return the identifier for the refresh period a date falls in.

    weekly   -> ISO year-week, e.g. "2026-W33" (matches rule 4: T1 refreshes
                every week, Monday starts a new week).
    biweekly -> ISO year + 2-week block, e.g. "2026-B16" (weeks 1-2 -> B00,
                weeks 3-4 -> B01, ...). Approximate: a block can straddle a
                year boundary near week 52/53, which is fine for a DCA cadence.
    monthly  -> "2026-08" (T3 and below refresh on the 1st of the month).
    """
    if tier_refresh == "weekly":
        iso = as_of.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if tier_refresh == "biweekly":
        iso = as_of.isocalendar()
        block = (iso[1] - 1) // 2
        return f"{iso[0]}-B{block:02d}"
    if tier_refresh == "monthly":
        return f"{as_of.year:04d}-{as_of.month:02d}"
    raise ValueError(f"unknown refresh cadence: {tier_refresh}")


def period_start(tier_refresh: str, as_of: dt.date) -> dt.date:
    if tier_refresh == "weekly":
        return as_of - dt.timedelta(days=as_of.weekday())  # Monday
    if tier_refresh == "biweekly":
        monday_this_week = as_of - dt.timedelta(days=as_of.weekday())
        iso_week = as_of.isocalendar()[1]
        # odd ISO week = first week of its 2-week block, even = second week
        return monday_this_week if iso_week % 2 == 1 else monday_this_week - dt.timedelta(days=7)
    if tier_refresh == "monthly":
        return as_of.replace(day=1)
    raise ValueError(f"unknown refresh cadence: {tier_refresh}")
