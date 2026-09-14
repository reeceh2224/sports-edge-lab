from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODELS_DIR = ROOT / "models"
DB_PATH = DATA_DIR / "sports_edge.sqlite"

for p in (RAW_DIR, PROCESSED_DIR, MODELS_DIR):
    p.mkdir(parents=True, exist_ok=True)
