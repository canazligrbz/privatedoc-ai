"""
Yerel LLM istemcisi (Ollama ve vLLM/OpenAI-uyumlu).

Yalnızca 127.0.0.1 üzerindeki servise konuşur. airgap.py başka bir adrese
çıkışı zaten bloklar; bu modül ayrıca base_url'i doğrular.
"""

from __future__ import annotations

import json
from typing import Dict, Generator, Optional
from urllib.parse import urlparse

import httpx

from .config import Config, load_config


class LLMUnavailable(RuntimeError):
    pass


def _assert_local(base_url: str) -> None:
    host = (urlparse(base_url).hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise LLMUnavailable(
            f"Güvenlik: LLM sunucusu yalnızca localhost olabilir, verilen: {host!r}"
        )


def _diagnose(detail: str, model: str, num_ctx: int) -> str:
    """Ollama'nın ham hata metnini anlaşılır bir çözüm önerisine çevirir."""
    d = detail.lower()
    if "cuda_host" in d or "cuda host" in d or ("cuda" in d and "allocate" in d):
        return (
            "GPU/PINNED BELLEK HATASI. Ollama bir NVIDIA GPU tespit edip modeli oraya\n"
            "  yüklemeye çalışıyor, ancak sabitlenmiş (pinned) host belleği ayıramıyor.\n"
            "  Çözüm:\n"
            "   1) config.yaml → llm.num_gpu: 0  (saf CPU modu — pinned bellek istemez)\n"
            "   2) GPU'yu kullanmak istiyorsanız: VRAM'i 'nvidia-smi' ile kontrol edin,\n"
            "      6 GB ve üzeriyse num_gpu: 20 gibi kısmi bir değer deneyin.\n"
            "   3) Ollama'yı yeniden başlatın (değişiklik yeni model yüklemesinde etkin olur)."
        )
    if "memory" in d or "insufficient" in d or "unable to allocate" in d or "oom" in d:
        return (
            f"YETERSİZ BELLEK. '{model}' modeli num_ctx={num_ctx} ile RAM'e sığmadı.\n"
            "  Çözüm sırasıyla:\n"
            "   1) Açık uygulamaları kapatın (özellikle tarayıcı).\n"
            "   2) config.yaml → llm.num_ctx değerini 4096'ya düşürün.\n"
            "   3) Daha küçük modele geçin:\n"
            "        ollama pull qwen2.5:3b-instruct-q4_K_M\n"
            "      ve config.yaml → llm.model değerini bu modelle değiştirin."
        )
    if "no space" in d or "disk" in d or "space left" in d:
        return ("DİSK ALANI YETERSİZ. Ollama modeli belleğe eşleyemiyor. "
                "En az 15 GB boş alan açın veya OLLAMA_MODELS ortam değişkeni ile "
                "model klasörünü başka bir sürücüye taşıyın.")
    if "not found" in d or "no such model" in d:
        return (f"MODEL BULUNAMADI: '{model}'. Şunu çalıştırın: ollama pull {model}\n"
                "  veya config.yaml → llm.model değerini 'ollama list' çıktısındaki bir isimle eşleyin.")
    if "invalid" in d and "option" in d:
        return ("Geçersiz model parametresi. Ollama sürümünüz eski olabilir; "
                "güncelleyin veya config.yaml → llm bölümündeki ek seçenekleri kaldırın.")
    return ("Ollama sunucusu hata döndürdü. Ayrıntı için terminalde şunu deneyin:\n"
            f"    ollama run {model} \"merhaba\"")


def _raise_http_error(response, model: str, num_ctx: int) -> None:
    """Akışlı yanıtta gövdeyi okuyup anlaşılır hata fırlatır."""
    try:
        response.read()
        body = response.text or ""
    except Exception:
        body = ""
    detail = body.strip()
    try:
        parsed = json.loads(body)
        detail = str(parsed.get("error", detail))
    except Exception:
        pass
    raise LLMUnavailable(
        f"Ollama HTTP {response.status_code}\n"
        f"  Sunucu mesajı: {detail[:500] or '(boş)'}\n"
        f"  → {_diagnose(detail, model, num_ctx)}"
    )


class LocalLLM:
    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or load_config()
        self.provider = str(self.cfg.get_path("llm.provider", "ollama")).lower()
        self.base_url = str(self.cfg.get_path("llm.base_url", "http://127.0.0.1:11434")).rstrip("/")
        self.model = str(self.cfg.get_path("llm.model"))
        self.timeout = float(self.cfg.get_path("llm.timeout_s", 600))
        _assert_local(self.base_url)

    # ------------------------------------------------------------ sağlık

    def health(self) -> Dict[str, object]:
        """Servis ayakta mı, model yüklü mü?"""
        try:
            if self.provider == "ollama":
                r = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
                r.raise_for_status()
                models = [m.get("name", "") for m in r.json().get("models", [])]
                base = self.model.split(":")[0]
                ok = any(m == self.model or m.startswith(base) for m in models)
                return {
                    "online": True,
                    "model_available": ok,
                    "models": models,
                    "message": "Hazır" if ok else f"'{self.model}' yüklü değil",
                }
            r = httpx.get(f"{self.base_url}/v1/models", timeout=5.0)
            r.raise_for_status()
            models = [m.get("id", "") for m in r.json().get("data", [])]
            return {
                "online": True,
                "model_available": self.model in models or not models,
                "models": models,
                "message": "Hazır",
            }
        except Exception as exc:
            return {
                "online": False,
                "model_available": False,
                "models": [],
                "message": f"LLM sunucusuna ulaşılamıyor ({self.base_url}). "
                           f"Ollama çalışıyor mu? Ayrıntı: {exc}",
            }

    # ------------------------------------------------------------ seçenekler

    def _options(self, temperature: Optional[float] = None) -> Dict[str, object]:
        c = self.cfg
        opts = {
            "temperature": float(temperature if temperature is not None
                                 else c.get_path("llm.temperature", 0.0)),
            "top_p": float(c.get_path("llm.top_p", 0.9)),
            "top_k": int(c.get_path("llm.top_k", 20)),
            "repeat_penalty": float(c.get_path("llm.repeat_penalty", 1.05)),
            "num_ctx": int(c.get_path("llm.num_ctx", 8192)),
            "num_predict": int(c.get_path("llm.num_predict", 900)),
            "seed": int(c.get_path("llm.seed", 42)),
        }
        threads = int(c.get_path("llm.num_thread", 0) or 0)
        if threads > 0:
            opts["num_thread"] = threads
        # num_gpu: 0 = saf CPU, null/eksik = Ollama otomatik seçsin
        num_gpu = c.get_path("llm.num_gpu", None)
        if num_gpu is not None:
            opts["num_gpu"] = int(num_gpu)
        stops = c.get_path("llm.stop") or []
        if stops:
            opts["stop"] = list(stops)
        return opts

    # ------------------------------------------------------------ üretim

    def stream_chat(self,
                    system: str,
                    user: str,
                    temperature: Optional[float] = None) -> Generator[str, None, None]:
        """Token akışı üretir (arayüzde canlı yazma efekti)."""
        if self.provider == "ollama":
            options = self._options(temperature)
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": True,
                "keep_alive": self.cfg.get_path("llm.keep_alive", "30m"),
                "options": options,
            }
            url = f"{self.base_url}/api/chat"
            try:
                with httpx.stream("POST", url, json=payload, timeout=self.timeout) as r:
                    if r.status_code >= 400:
                        _raise_http_error(r, self.model, int(options.get("num_ctx", 0)))
                    for line in r.iter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        piece = (data.get("message") or {}).get("content", "")
                        if piece:
                            yield piece
                        if data.get("done"):
                            break
            except LLMUnavailable:
                raise
            except Exception as exc:
                # httpx dışı hatalar da (proxy yapılandırması, SSL, kesilen
                # bağlantı) anlaşılır tek bir hata tipine dönüştürülür;
                # aksi hâlde arayüze ham yığın izi düşer.
                raise LLMUnavailable(f"LLM isteği başarısız: {exc}") from exc
            return

        # vLLM / OpenAI uyumlu
        opts = self._options(temperature)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": True,
            "temperature": opts["temperature"],
            "top_p": opts["top_p"],
            "max_tokens": opts["num_predict"],
        }
        url = f"{self.base_url}/v1/chat/completions"
        try:
            with httpx.stream("POST", url, json=payload, timeout=self.timeout) as r:
                if r.status_code >= 400:
                    _raise_http_error(r, self.model, int(opts.get("num_ctx", 0)))
                for line in r.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        break
                    try:
                        data = json.loads(body)
                    except json.JSONDecodeError:
                        continue
                    delta = (data.get("choices") or [{}])[0].get("delta", {})
                    piece = delta.get("content") or ""
                    if piece:
                        yield piece
        except LLMUnavailable:
            raise
        except Exception as exc:
            raise LLMUnavailable(f"LLM isteği başarısız: {exc}") from exc

    def chat(self,
             system: str,
             user: str,
             temperature: Optional[float] = None) -> str:
        return "".join(self.stream_chat(system, user, temperature))
