from pathlib import Path
from functools import lru_cache
import json
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parents[1]

class Language(BaseModel):
    code: str
    name: str
    native: str

@lru_cache
def get_languages() -> list[Language]:
    with open(BASE_DIR / "jsons" / "languages.json", encoding="utf-8") as f:
        data = json.load(f)

    return [Language(**lang) for lang in data]
