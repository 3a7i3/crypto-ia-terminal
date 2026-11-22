"""FIXTURE_ONLY — lecteur sans lien prouvé avec le producteur."""
import json
import os


class HistoryReader:
    def __init__(self):
        self.path = os.getenv("FIX_OTHER_PATH")

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            return json.load(fh)
