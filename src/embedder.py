"""
Yerel embedding sarmalayıcı.

- Model YALNIZCA yerel diskten yüklenir (`local_files_only=True`).
- Hiçbir koşulda HuggingFace'e istek atılmaz; airgap.py zaten bunu bloklar,
  bu katman ise anlaşılır bir hata mesajı üretir.
- Tekil (singleton) yükleme: Streamlit yeniden çalıştırmalarında model
  tekrar tekrar RAM'e alınmaz.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import List, Optional, Sequence

import numpy as np

from .config import Config, load_config

_LOCK = threading.Lock()
_MODEL = None
_MODEL_PATH: Optional[str] = None


class EmbeddingModelNotFound(RuntimeError):
    pass


def _resolve_model_dir(cfg: Config) -> Path:
    primary = cfg.resolve("embedding.model_path")
    if primary.exists():
        return primary
    fb_raw = cfg.get_path("embedding.fallback_model_path")
    if fb_raw:
        fb = cfg.resolve("embedding.fallback_model_path")
        if fb.exists():
            return fb
    raise EmbeddingModelNotFound(
        f"Embedding modeli bulunamadı: {primary}\n"
        "Çevrimdışı kurulum yapılmamış olabilir. İnternetli makinede şunu çalıştırın:\n"
        "  python scripts/download_models.py --out models\n"
        "ve 'models/' klasörünü air-gap makineye kopyalayın."
    )


def get_model():
    """SentenceTransformer örneğini döndürür (tembel + tekil yükleme)."""
    global _MODEL, _MODEL_PATH
    if _MODEL is not None:
        return _MODEL
    with _LOCK:
        if _MODEL is not None:
            return _MODEL
        cfg = load_config()
        model_dir = _resolve_model_dir(cfg)

        import torch  # noqa: WPS433 (tembel import: başlangıç süresini kısaltır)
        from sentence_transformers import SentenceTransformer

        # CPU'da iş parçacığı sayısını sınırlamak, Streamlit ile birlikte
        # çalışırken sistemin kilitlenmesini önler.
        try:
            torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))
        except Exception:
            pass

        model = SentenceTransformer(
            str(model_dir),
            device=cfg.get_path("embedding.device", "cpu"),
            local_files_only=True,
        )
        max_len = cfg.get_path("embedding.max_seq_length")
        if max_len:
            model.max_seq_length = int(max_len)

        _MODEL = model
        _MODEL_PATH = str(model_dir)
        return _MODEL


def model_info() -> dict:
    cfg = load_config()
    return {
        "path": _MODEL_PATH or str(cfg.get_path("embedding.model_path")),
        "loaded": _MODEL is not None,
        "device": cfg.get_path("embedding.device", "cpu"),
        "max_seq_length": cfg.get_path("embedding.max_seq_length"),
    }


def _encode(texts: Sequence[str], prefix: str, show_progress: bool = False) -> np.ndarray:
    cfg = load_config()
    model = get_model()
    prepared = [f"{prefix}{t}" if prefix else t for t in texts]
    vectors = model.encode(
        prepared,
        batch_size=int(cfg.get_path("embedding.batch_size", 4)),
        normalize_embeddings=bool(cfg.get_path("embedding.normalize_embeddings", True)),
        convert_to_numpy=True,
        show_progress_bar=show_progress,
    )
    return np.asarray(vectors, dtype=np.float32)


def embed_passages(texts: Sequence[str], show_progress: bool = False) -> List[List[float]]:
    """Belge parçalarını vektörleştirir (indeksleme yönü)."""
    if not texts:
        return []
    cfg = load_config()
    prefix = cfg.get_path("embedding.passage_prefix", "") or ""
    return _encode(texts, prefix, show_progress).tolist()


def embed_query(text: str) -> List[float]:
    """Kullanıcı sorusunu vektörleştirir (arama yönü)."""
    cfg = load_config()
    prefix = cfg.get_path("embedding.query_prefix", "") or ""
    return _encode([text], prefix)[0].tolist()


def cosine_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Normalize edilmiş vektörler için kosinüs benzerlik matrisi."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    a = a / (np.linalg.norm(a, axis=-1, keepdims=True) + 1e-9)
    b = b / (np.linalg.norm(b, axis=-1, keepdims=True) + 1e-9)
    return a @ b.T
