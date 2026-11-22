"""FIXTURE_ONLY — API GET synthétique."""
from api.history_reader import HistoryReader
from fastapi import FastAPI

app = FastAPI()
_reader = HistoryReader()


@app.get("/api/v1/fix-history")
def get_history():
    return _reader.read()
