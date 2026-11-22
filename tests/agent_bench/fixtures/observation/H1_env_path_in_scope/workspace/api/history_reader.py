"""FIXTURE_ONLY — lecteur synthétique servi par l'API."""
import json
import os

from pipeline.publish import validate


class HistoryReader:
    def __init__(self):
        self.path = os.getenv("FIX_HISTORY_PATH")

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            doc = json.load(fh)
        return doc if not validate(doc) else None
