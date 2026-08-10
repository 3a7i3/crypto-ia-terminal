from __future__ import annotations

from pathlib import Path

from tracker_system.config.settings import OPEN_POSITIONS_FILE
from tracker_system.storage.loader import load_json
from tracker_system.storage.saver import save_json


def load_positions(path: Path = OPEN_POSITIONS_FILE) -> list[dict]:
    return load_json(path, [])


def save_positions(positions: list[dict], path: Path = OPEN_POSITIONS_FILE) -> None:
    save_json(path, positions)


def replace_position(updated_position: dict, path: Path = OPEN_POSITIONS_FILE) -> None:
    positions = load_positions(path)
    new_positions = [
        updated_position if pos.get("id") == updated_position.get("id") else pos
        for pos in positions
    ]
    save_positions(new_positions, path)
