"""Configuration loading. CUTOFF and every threshold come from config/, never from code."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from arkstream.timeparse import parse_one_utc

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


def load_yaml(name: str, config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    with open(config_dir / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@dataclass(frozen=True)
class Context:
    raw: dict[str, Any]
    root: Path

    @property
    def cutoff(self) -> datetime:
        return parse_one_utc(self.raw["cutoff"])

    def path(self, key: str) -> Path:
        return self.root / self.raw["inputs"][key]

    def section(self, key: str) -> dict[str, Any]:
        return self.raw[key]


def load_context(config_dir: Path = CONFIG_DIR, root: Path = ROOT) -> Context:
    return Context(raw=load_yaml("decision_context.yaml", config_dir), root=root)


def load_instruments(config_dir: Path = CONFIG_DIR) -> dict[str, Any]:
    return load_yaml("instruments.yaml", config_dir)


def assert_no_live_trading(config_dir: Path = CONFIG_DIR) -> None:
    """Rule 6: nothing in this repo may send orders. Fails if someone flips the switch."""
    ex = load_yaml("execution.yaml", config_dir)
    if ex.get("live_trading_enabled", False) is not False:
        raise RuntimeError("live_trading_enabled must be false; this repository contains no order path")
