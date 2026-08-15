"""
Merkezi yapılandırma yükleyici.

config.yaml tek doğruluk kaynağıdır. Ortam değişkeni ile geçersiz kılma:
    BELGE_ASISTANI_CONFIG=/path/to/other.yaml
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

# Proje kök dizini: src/config.py -> src -> proje kökü
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Config(dict):
    """Nokta notasyonu ile erişilebilen sözlük: cfg.get_path('llm.model')"""

    def get_path(self, dotted: str, default: Any = None) -> Any:
        node: Any = self
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def resolve(self, dotted: str) -> Path:
        """Yapılandırmadaki göreli bir yolu mutlak yola çevirir."""
        raw = self.get_path(dotted)
        if raw is None:
            raise KeyError(f"Yapılandırmada yol bulunamadı: {dotted}")
        p = Path(raw)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


@lru_cache(maxsize=1)
def load_config() -> Config:
    cfg_path = Path(os.environ.get("BELGE_ASISTANI_CONFIG", PROJECT_ROOT / "config.yaml"))
    if not cfg_path.exists():
        raise FileNotFoundError(f"Yapılandırma dosyası bulunamadı: {cfg_path}")
    with open(cfg_path, "r", encoding="utf-8") as fh:
        data: Dict[str, Any] = yaml.safe_load(fh) or {}
    return Config(data)


def ensure_directories(cfg: Config) -> None:
    """Gerekli klasörleri oluşturur (ilk çalıştırma için)."""
    for key in ("paths.documents", "paths.vectordb", "paths.models", "paths.logs"):
        cfg.resolve(key).mkdir(parents=True, exist_ok=True)
