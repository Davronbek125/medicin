"""
Pytest uchun umumiy sozlamalar.

Eng muhimi: testlar HAR DOIM vaqtinchalik test bazasidan foydalanishi kerak.

Ilgari `DB_PATH` faqat `tests/test_services.py` import qilinayotganda (module-level
kod orqali) o'rnatilardi. Natijada, faqat bitta fayl ishga tushirilganda
(masalan `pytest tests/test_api.py`) `DB_PATH` standart holatda qolib, testlar
haqiqiy `data/clinic.db` bazasiga yozishi mumkin edi.

`conftest.py` pytest tomonidan test modullaridan OLDIN import qilinadi, shuning
uchun bu yerda `DB_PATH` ni o'rnatish barcha testlar uchun izolyatsiyani kafolatlaydi.
"""
import os

# MUHIM: `app.config` import qilinishidan oldin muhit o'zgaruvchisini o'rnatamiz.
TEST_DB_PATH = "data/test_clinic.db"
os.environ["DB_PATH"] = TEST_DB_PATH

from app.config import settings  # noqa: E402  (env sozlangandan keyin import qilinadi)

# Settings allaqachon yaratilgan bo'lsa ham qiymatni kafolatlaymiz.
settings.DB_PATH = TEST_DB_PATH

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_db():
    """Test sessiyasi tugagach vaqtinchalik test bazasini (va WAL/SHM fayllarini) o'chirish."""
    yield
    for suffix in ("", "-wal", "-shm"):
        path = TEST_DB_PATH + suffix
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
