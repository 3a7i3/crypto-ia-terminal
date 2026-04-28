"""
Module : api_rest.py
API REST minimaliste pour exposer les résultats et déclencher des analyses à distance.
"""

import os

import pandas as pd
from fastapi import FastAPI, File, UploadFile

app = FastAPI()


@app.get("/results")
def get_results(sim_csv_dir: str = "sim_summaries"):
    csv_files = [f for f in os.listdir(sim_csv_dir) if f.endswith(".csv")]
    if not csv_files:
        return {"error": "Aucun fichier de simulation trouvé."}
    sim_dfs = [pd.read_csv(os.path.join(sim_csv_dir, f)) for f in csv_files]
    sim_df = pd.concat(sim_dfs, ignore_index=True)
    return sim_df.head(100).to_dict(orient="records")


@app.post("/upload")
def upload_csv(file: UploadFile = File(...), sim_csv_dir: str = "sim_summaries"):
    os.makedirs(sim_csv_dir, exist_ok=True)
    file_path = os.path.join(sim_csv_dir, file.filename)
    with open(file_path, "wb") as f:
        f.write(file.file.read())
    return {"status": "ok", "filename": file.filename}


# Pour lancer : uvicorn api_rest:app --reload
