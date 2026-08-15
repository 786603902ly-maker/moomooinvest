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


def load_yaml(path: pathlib.Path) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_stocks() -> list:
    return load_yaml(STOCKS_PATH)["stocks"]


def load_rules() -> dict:
    return load_yaml(RULES_PATH)


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

    weekly  -> ISO year-week, e.g. "2026-W33" (matches rule 4: T1 refreshes
               every week, Monday starts a new week).
    monthly -> "2026-08" (T2 and below refresh on the 1st of the month).
    """
    if tier_refresh == "weekly":
        iso = as_of.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if tier_refresh == "monthly":
        return f"{as_of.year:04d}-{as_of.month:02d}"
    raise ValueError(f"unknown refresh cadence: {tier_refresh}")


def period_start(tier_refresh: str, as_of: dt.date) -> dt.date:
    if tier_refresh == "weekly":
        return as_of - dt.timedelta(days=as_of.weekday())  # Monday
    if tier_refresh == "monthly":
        return as_of.replace(day=1)
    raise ValueError(f"unknown refresh cadence: {tier_refresh}")
