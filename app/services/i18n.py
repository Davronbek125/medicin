"""
Ko'p tillilik (i18n) xizmati - O'zbekcha va Ruscha matnlar.
"""
import json
from pathlib import Path
from typing import Dict, Any

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"

_locales: Dict[str, Dict[str, str]] = {}


def load_locales() -> None:
    """Barcha lokalizatsiya fayllarini yuklash."""
    for lang in ["uz", "ru"]:
        file_path = LOCALES_DIR / f"{lang}.json"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                _locales[lang] = json.load(f)
        else:
            _locales[lang] = {}


def t(key: str, lang: str = "uz", **kwargs: Any) -> str:
    """Kalit so'z bo'yicha matnni olish va o'zgaruvchilarni joylashtirish."""
    if not _locales:
        load_locales()
    
    selected_lang = lang if lang in _locales else "uz"
    text = _locales.get(selected_lang, {}).get(key)
    
    if text is None:
        # Fallback to uzbek
        text = _locales.get("uz", {}).get(key, key)
        
    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text
