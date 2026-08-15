"""
ChromaDB (kalıcı, yerel dosya tabanlı) sarmalayıcı.

Neden Chroma? Sunucu süreci gerektirmez, tek klasörde saklanır, yedeklemesi
kopyala-yapıştır kadar basittir. Air-gap ortamda "kurulacak bir servis daha"
olmaması büyük avantajdır. 1-2 milyon parçanın üzerine çıkılırsa Qdrant'a
geçiş için bu dosyadaki arayüzü uygulamak yeterlidir.

Embedding'ler DIŞARIDAN verilir (embedding_function=None). Böylece Chroma'nın
varsayılan indirmeli modeli asla devreye girmez -> air-gap garantisi.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence  # noqa: F401

from .config import Config, load_config


def get_client(cfg: Optional[Config] = None):
    import chromadb
    from chromadb.config import Settings

    cfg = cfg or load_config()
    persist_dir = cfg.resolve("paths.vectordb")
    persist_dir.mkdir(parents=True, exist_ok=True)

    return chromadb.PersistentClient(
        path=str(persist_dir),
        settings=Settings(anonymized_telemetry=False, allow_reset=True),
    )


def get_collection(client=None, cfg: Optional[Config] = None, create: bool = True):
    cfg = cfg or load_config()
    client = client or get_client(cfg)
    name = cfg.get_path("retrieval.collection_name", "belge_koleksiyonu")
    space = cfg.get_path("retrieval.distance", "cosine")

    if create:
        return client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": space, "hnsw:construction_ef": 200, "hnsw:M": 32},
        )
    return client.get_collection(name=name)


def upsert(collection,
           ids: Sequence[str],
           documents: Sequence[str],
           embeddings: Sequence[Sequence[float]],
           metadatas: Sequence[Dict[str, Any]],
           batch_size: int = 256) -> None:
    """Büyük partileri parçalayarak yazar (Chroma'nın batch sınırı için)."""
    total = len(ids)
    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        collection.upsert(
            ids=list(ids[start:end]),
            documents=list(documents[start:end]),
            embeddings=[list(e) for e in embeddings[start:end]],
            metadatas=list(metadatas[start:end]),
        )


def delete_by_source(collection, source_path: str) -> int:
    """Bir belgenin tüm parçalarını siler (belge güncellendiğinde çağrılır)."""
    try:
        existing = collection.get(where={"source_path": source_path}, include=[])
        ids = existing.get("ids", []) or []
        if ids:
            collection.delete(ids=ids)
        return len(ids)
    except Exception:
        return 0


def query(collection,
          query_embedding: Sequence[float],
          top_k: int,
          where: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Benzerlik araması. Kosinüs UZAKLIĞI -> BENZERLİK dönüşümü burada yapılır."""
    res = collection.query(
        query_embeddings=[list(query_embedding)],
        n_results=max(1, int(top_k)),
        where=where or None,
        include=["documents", "metadatas", "distances", "embeddings"],
    )

    out: List[Dict[str, Any]] = []
    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    embs_raw = res.get("embeddings")
    embs = embs_raw[0] if embs_raw is not None and len(embs_raw) else [None] * len(ids)

    for i, _id in enumerate(ids):
        distance = float(dists[i]) if i < len(dists) else 1.0
        # Chroma cosine distance = 1 - cosine_similarity
        similarity = max(0.0, min(1.0, 1.0 - distance))
        out.append({
            "id": _id,
            "text": docs[i] if i < len(docs) else "",
            "metadata": metas[i] if i < len(metas) else {},
            "distance": distance,
            "similarity": similarity,
            "embedding": embs[i] if i < len(embs) else None,
        })
    return out


def fetch_all(collection, batch: int = 5000) -> List[Dict[str, Any]]:
    """
    Koleksiyondaki tüm parçaları (id, metin, metadata) getirir.
    BM25 anahtar kelime indeksini bellekte kurmak için gereklidir.
    Embedding'ler DAHİL EDİLMEZ — bellek israfı olurdu.
    """
    out: List[Dict[str, Any]] = []
    try:
        total = collection.count()
    except Exception:
        return out

    offset = 0
    while offset < total:
        got = collection.get(
            include=["documents", "metadatas"],
            limit=min(batch, total - offset),
            offset=offset,
        )
        ids = got.get("ids", []) or []
        docs = got.get("documents", []) or []
        metas = got.get("metadatas", []) or []
        for i, _id in enumerate(ids):
            out.append({
                "id": _id,
                "text": docs[i] if i < len(docs) else "",
                "metadata": metas[i] if i < len(metas) else {},
            })
        if not ids:
            break
        offset += len(ids)
    return out


def get_by_ids(collection, ids: Sequence[str]) -> List[Dict[str, Any]]:
    """Belirli id'lerin metin, metadata ve embedding'lerini getirir."""
    if not ids:
        return []
    got = collection.get(ids=list(ids),
                         include=["documents", "metadatas", "embeddings"])
    res_ids = got.get("ids", []) or []
    docs = got.get("documents", []) or []
    metas = got.get("metadatas", []) or []
    embs_raw = got.get("embeddings")
    embs = embs_raw if embs_raw is not None and len(embs_raw) else [None] * len(res_ids)

    out = []
    for i, _id in enumerate(res_ids):
        out.append({
            "id": _id,
            "text": docs[i] if i < len(docs) else "",
            "metadata": metas[i] if i < len(metas) else {},
            "embedding": embs[i] if i < len(embs) else None,
        })
    return out


def stats(cfg: Optional[Config] = None) -> Dict[str, Any]:
    cfg = cfg or load_config()
    try:
        client = get_client(cfg)
        col = get_collection(client, cfg, create=True)
        count = col.count()
        sources = set()
        if count:
            # Kaynak listesi için yalnızca metadata çekilir (bellek dostu)
            got = col.get(include=["metadatas"], limit=min(count, 20000))
            for m in got.get("metadatas", []) or []:
                if m and m.get("source_file"):
                    sources.add(m["source_file"])
        return {"chunks": count, "documents": len(sources), "sources": sorted(sources)}
    except Exception as exc:
        return {"chunks": 0, "documents": 0, "sources": [], "error": str(exc)}


def reset(cfg: Optional[Config] = None) -> None:
    """Koleksiyonu tamamen siler (tam yeniden indeksleme öncesi)."""
    cfg = cfg or load_config()
    client = get_client(cfg)
    name = cfg.get_path("retrieval.collection_name", "belge_koleksiyonu")
    try:
        client.delete_collection(name)
    except Exception:
        pass
    manifest = Path(cfg.resolve("paths.manifest"))
    if manifest.exists():
        manifest.unlink()
