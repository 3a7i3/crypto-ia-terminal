"""CLI status helper for the local LM Studio server."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from lm_studio.client import (
    LM_STUDIO_MODEL,
    LM_STUDIO_URL,
    is_available,
    list_loaded_models,
    list_models,
)


def main() -> None:
    print(f"LM Studio URL  : {LM_STUDIO_URL}")
    print(f"Modele par defaut : {LM_STUDIO_MODEL}")

    if is_available():
        print("[OK] LM Studio est en ligne")
        loaded_models = list_loaded_models()
        if loaded_models:
            print(f"  Modeles LLM charges ({len(loaded_models)}) :")
            for model in loaded_models:
                suffix = "  <--" if model == LM_STUDIO_MODEL else ""
                print(f"    * {model}{suffix}")
        else:
            print("  Aucun modele LLM charge (charge un modele dans LM Studio)")

        all_models = list_models()
        if all_models:
            print(f"  Modeles connus ({len(all_models)}) :")
            for model in all_models:
                suffix = "  <-- par defaut" if model == LM_STUDIO_MODEL else ""
                print(f"    - {model}{suffix}")
    else:
        print("[OFFLINE] LM Studio est hors ligne")
        print("  -> Lance LM Studio, va dans 'Local Server' et clique Start")


if __name__ == "__main__":
    main()
