"""
pytest ortak ayarları.

Proje kökünü ve eval/ klasörünü import yoluna ekler; testler `src.*` ve
`matching`/`stats` modüllerini doğrudan çağırabilsin diye.
"""

from __future__ import annotations

import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))
sys.path.insert(0, str(KOK / "eval"))
