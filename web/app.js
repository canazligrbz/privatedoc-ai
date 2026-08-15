/* =====================================================================
   Belge Asistanı — arayüz mantığı
   Bağımlılık yok, CDN yok. Yanıt fetch + ReadableStream ile akıtılır.
   ===================================================================== */

(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const E = {
    thread: $("thread"), intro: $("intro"),
    composer: $("composer"), input: $("input"), send: $("btnSend"),
    clear: $("btnClear"), title: $("appTitle"),
    chip: $("chipStatus"), chipText: $("chipText"),
    panel: $("btnPanel"), close: $("btnClose"), drawer: $("drawer"), scrim: $("scrim"),
    drop: $("dropzone"), file: $("fileInput"), docs: $("docList"), types: $("dropTypes"),
    ingest: $("btnIngest"), rebuild: $("btnRebuild"), msg: $("ingestMsg"),
    filter: $("sourceFilter"), sysinfo: $("sysinfo"),
    finalK: $("rngFinalK"), lFinalK: $("lblFinalK"),
    topK: $("rngTopK"), lTopK: $("lblTopK"),
    minSim: $("rngMinSim"), lMinSim: $("lblMinSim"),
    temp: $("rngTemp"), lTemp: $("lblTemp"), tempWarn: $("tempWarn"),
  };

  let history = [];
  let busy = false;

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function render(text) {
    let h = esc(text).replace(/\[K\s*(\d{1,2})\]/g,
      '<span class="cite" data-n="$1" title="Kaynağa git">K$1</span>');
    const out = [];
    let list = false;
    for (const raw of h.split("\n")) {
      const line = raw.trim();
      if (/^(?:[-*•]|\d+[.)])\s+/.test(line)) {
        if (!list) { out.push("<ul>"); list = true; }
        out.push("<li>" + line.replace(/^(?:[-*•]|\d+[.)])\s+/, "") + "</li>");
      } else {
        if (list) { out.push("</ul>"); list = false; }
        if (line) out.push("<p>" + line + "</p>");
      }
    }
    if (list) out.push("</ul>");
    return out.join("") || "<p></p>";
  }

  const toBottom = () => window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });

  function say(cls, text, ms) {
    E.msg.className = "note " + (cls || "");
    E.msg.textContent = text;
    E.msg.hidden = false;
    if (ms) setTimeout(() => { E.msg.hidden = true; }, ms);
  }

  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

  // ------------------------------------------------------------- başlangıç

  async function boot() {
    try {
      const c = await (await fetch("/api/config")).json();
      if (c.title) { document.title = c.title; E.title.textContent = c.title; }
      if (c.accepted_types?.length) {
        E.types.textContent = c.accepted_types.map((t) => t.replace(".", "").toUpperCase()).join(" · ");
        E.file.accept = c.accepted_types.join(",");
      }
      const t = c.theme || {};
      const vars = {
        "--brand": t.primary, "--brand-dark": t.primary_dark, "--brand-soft": t.primary_light,
        "--bg": t.background, "--surface": t.surface, "--line": t.border,
        "--ink": t.text, "--ink-soft": t.text_muted,
      };
      for (const [k, v] of Object.entries(vars)) if (v) document.documentElement.style.setProperty(k, v);

      const s = c.settings || {};
      init(E.finalK, E.lFinalK, s.final_k, (v) => v);
      init(E.topK, E.lTopK, s.top_k, (v) => v);
      init(E.minSim, E.lMinSim, s.min_similarity, (v) => (+v).toFixed(2));
      init(E.temp, E.lTemp, s.temperature, (v) => (+v).toFixed(2));
    } catch (_) { /* varsayılanlarla devam */ }

    await Promise.all([status(), docs()]);
    setInterval(status, 25000);
  }

  function init(inp, lab, val, fmt) {
    if (val != null) inp.value = val;
    lab.textContent = fmt(inp.value);
  }

  async function status() {
    try {
      const s = await (await fetch("/api/status")).json();
      const ready = s.llm_online && s.model_available;
      E.chip.className = "chip " + (ready ? "ok" : s.llm_online ? "" : "bad");
      E.chipText.textContent = !s.llm_online ? "motor kapalı"
        : !s.model_available ? "model yok"
        : s.chunks > 0 ? `${s.documents} belge · çevrimdışı` : "belge yok";
      E.chip.title = s.llm_message || "";

      E.sysinfo.innerHTML =
        `Model <b>${esc((s.model || "-").split(":")[0])}</b><br>` +
        `Ağ <b>${s.airgap ? "izole" : "açık"}</b><br>` +
        `İndeks <b>${s.documents} belge · ${(s.chunks || 0).toLocaleString("tr-TR")} parça</b>`;

      const keep = new Set([...E.filter.selectedOptions].map((o) => o.value));
      E.filter.innerHTML = "";
      for (const n of s.sources || []) {
        const o = document.createElement("option");
        o.value = n; o.textContent = n; o.selected = keep.has(n);
        E.filter.appendChild(o);
      }
    } catch (_) { /* sunucu yok */ }
  }

  async function docs() {
    try {
      const { documents, problems } = await (await fetch("/api/documents")).json();
      E.docs.innerHTML = documents.length ? "" : '<li class="empty">Henüz belge yok.</li>';
      for (const d of documents) {
        const li = document.createElement("li");
        li.className = "doc-" + d.state;
        const mark = d.state === "ok" ? "●" : d.state === "error" ? "▲" : "○";
        li.innerHTML = `<span class="state" title="${esc(d.note)}">${mark}</span>
          <span class="ext">${esc(d.type)}</span>
          <span class="fname" title="${esc(d.name)}">${esc(d.name)}</span>
          <span class="fsize" title="${esc(d.note)}">${esc(d.note)}</span>`;
        E.docs.appendChild(li);
      }
      // Sorunlu belge varsa üst çubukta uyarı rozeti göster
      E.panel.classList.toggle("alert", problems > 0);
      E.panel.textContent = problems > 0 ? `Belgeler (${problems})` : "Belgeler";
    } catch (_) {}
  }

  // ------------------------------------------------------------- çekmece

  const openDrawer = (on) => {
    E.drawer.classList.toggle("on", on);
    E.scrim.classList.toggle("on", on);
  };
  E.panel.onclick = () => openDrawer(true);
  E.close.onclick = () => openDrawer(false);
  E.scrim.onclick = () => openDrawer(false);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") openDrawer(false); });

  // ------------------------------------------------------------- yükleme

  E.drop.onclick = () => E.file.click();
  E.drop.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); E.file.click(); } };
  ["dragenter", "dragover"].forEach((ev) => E.drop.addEventListener(ev, (e) => {
    e.preventDefault(); E.drop.classList.add("over");
  }));
  ["dragleave", "drop"].forEach((ev) => E.drop.addEventListener(ev, (e) => {
    e.preventDefault(); E.drop.classList.remove("over");
  }));
  E.drop.addEventListener("drop", (e) => upload(e.dataTransfer.files));
  E.file.onchange = () => upload(E.file.files);

  async function upload(list) {
    const files = [...(list || [])];
    if (!files.length) return;
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    say("", `${files.length} dosya yükleniyor…`);
    try {
      const r = await (await fetch("/api/upload", { method: "POST", body: fd })).json();
      let m = `${r.saved.length} dosya kaydedildi.`;
      if (r.skipped.length) m += ` ${r.skipped.length} tanesi desteklenmiyor.`;
      say("ok", m + " 'İndeksi güncelle'ye basın.");
      await docs();
    } catch (e) { say("bad", "Yükleme başarısız: " + e.message); }
    E.file.value = "";
  }

  async function runIngest(rebuild) {
    E.ingest.disabled = E.rebuild.disabled = true;
    say("", rebuild ? "İndeks sıfırdan kuruluyor…" : "Belgeler işleniyor… (taranmış PDF varsa uzun sürebilir)");
    try {
      const r = await (await fetch("/api/ingest", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rebuild: !!rebuild }),
      })).json();
      const bits = [];
      if (r.added?.length) bits.push(`${r.added.length} yeni`);
      if (r.updated?.length) bits.push(`${r.updated.length} güncel`);
      if (r.unchanged?.length) bits.push(`${r.unchanged.length} değişmedi`);
      if (r.removed?.length) bits.push(`${r.removed.length} silindi`);
      let base = (bits.join(" · ") || "değişiklik yok") + ` · ${r.chunks} parça (${r.duration_s} sn)`;
      if (r.ocr_used?.length) base += ` · ${r.ocr_used.length} taranmış belge OCR ile okundu`;

      if (r.failed?.length) {
        say("warn", base + " — Hatalı: " + r.failed.map((f) => `${f.file}: ${f.error}`).join(" | "));
      } else if (r.ocr_low_quality?.length) {
        // Bozuk OCR sessiz bir yanlış bilgi kaynağıdır: model bozuk sayıyı
        // kaynaktan okur ve sayı denetimi de onu onaylar. Kullanıcı hangi
        // sayfaların şüpheli olduğunu bilmeli.
        const list = r.ocr_low_quality
          .map((w) => `${w.file} → sayfa ${w.pages.join(", ")}`).join(" | ");
        say("warn", base + ` — OCR kalitesi düşük: ${list}. Bu sayfalardan gelen ` +
            "sayıları kaynak belgeden doğrulayın.");
      } else {
        say("ok", base);
      }
      await Promise.all([status(), docs()]);
    } catch (e) { say("bad", "İndeksleme başarısız: " + e.message); }
    E.ingest.disabled = E.rebuild.disabled = false;
  }
  E.ingest.onclick = () => runIngest(false);
  E.rebuild.onclick = () => { if (confirm("İndeks silinip yeniden kurulacak. Devam?")) runIngest(true); };

  // ------------------------------------------------------------- ayarlar

  const push = debounce(() => fetch("/api/settings", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      final_k: +E.finalK.value, top_k: +E.topK.value,
      min_similarity: +E.minSim.value, temperature: +E.temp.value,
    }),
  }), 300);

  const bind = (inp, lab, fmt) => inp.addEventListener("input", () => {
    lab.textContent = fmt(inp.value);
    if (inp === E.temp) E.tempWarn.hidden = +inp.value <= 0.001;
    push();
  });
  bind(E.finalK, E.lFinalK, (v) => v);
  bind(E.topK, E.lTopK, (v) => v);
  bind(E.minSim, E.lMinSim, (v) => (+v).toFixed(2));
  bind(E.temp, E.lTemp, (v) => (+v).toFixed(2));

  // ------------------------------------------------------------- sohbet

  const grow = () => {
    E.input.style.height = "auto";
    E.input.style.height = Math.min(E.input.scrollHeight, 160) + "px";
  };
  E.input.addEventListener("input", grow);
  E.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); E.composer.requestSubmit(); }
  });
  E.composer.addEventListener("submit", (e) => { e.preventDefault(); ask(); });

  E.clear.onclick = () => {
    history = [];
    E.thread.innerHTML = "";
    E.thread.appendChild(E.intro);
    E.intro.hidden = false;
  };

  function newTurn(question) {
    if (E.intro.parentNode) E.intro.remove();
    const t = document.createElement("article");
    t.className = "turn";
    t.innerHTML = `<div class="q"></div>
      <div class="wait"><span class="ring"></span><span class="wait-text">Belgeler taranıyor…</span></div>
      <div class="a" hidden></div>
      <div class="a-extra"></div>`;
    t.querySelector(".q").textContent = question;
    E.thread.appendChild(t);
    toBottom();
    return {
      wait: t.querySelector(".wait"),
      waitText: t.querySelector(".wait-text"),
      a: t.querySelector(".a"),
      extra: t.querySelector(".a-extra"),
    };
  }

  async function ask() {
    const question = E.input.value.trim();
    if (!question || busy) return;

    busy = true; E.send.disabled = true;
    E.input.value = ""; grow();

    const ui = newTurn(question);
    const sources = [...E.filter.selectedOptions].map((o) => o.value);
    let buf = "";

    // Yanıt geldiğinde bekleme göstergesini KESİN olarak kaldır.
    const stopWaiting = () => {
      ui.wait.hidden = true;
      ui.wait.remove();
      ui.a.hidden = false;
    };

    try {
      const res = await fetch("/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history: history.slice(-3), sources }),
      });
      if (!res.ok || !res.body) throw new Error("Sunucu yanıt vermedi (HTTP " + res.status + ")");

      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let carry = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        carry += dec.decode(value, { stream: true });
        const frames = carry.split("\n\n");
        carry = frames.pop();

        for (const f of frames) {
          const line = f.trim();
          if (!line.startsWith("data:")) continue;
          let ev;
          try { ev = JSON.parse(line.slice(5).trim()); } catch { continue; }

          if (ev.type === "status") {
            ui.waitText.textContent = ev.text;
          } else if (ev.type === "token") {
            if (!buf) stopWaiting();
            buf += ev.text;
            ui.a.innerHTML = render(buf) + '<span class="caret"></span>';
            toBottom();
          } else if (ev.type === "final") {
            stopWaiting();
            finalize(ui, ev);
            history.push([question, ev.answer]);
          } else if (ev.type === "error") {
            stopWaiting();
            ui.a.innerHTML = "";
            ui.extra.innerHTML = `<div class="note bad">${esc(ev.message)}</div>`;
          }
        }
      }
    } catch (err) {
      stopWaiting();
      ui.extra.innerHTML = `<div class="note bad">Bağlantı hatası: ${esc(err.message)}</div>`;
    } finally {
      // Akış yarıda kesilse bile gösterge asla ekranda kalmaz.
      stopWaiting();
      busy = false; E.send.disabled = false; E.input.focus();
    }
  }

  function finalize(ui, ev) {
    ui.a.innerHTML = render(ev.answer);   // guardrail sonrası doğrulanmış metin

    let h = "";
    if (ev.refused) {
      h += `<div class="note">Belgelerde bu soruya dayanak oluşturacak içerik bulunamadı,
        bu yüzden bilgi üretilmedi.
        ${ev.refusal_reason ? `<br><span class="why">Neden: ${esc(ev.refusal_reason)}</span>` : ""}</div>`;
    } else {
      // Guardrail bazı cümleleri çıkardıysa kullanıcı bunu bilmeli.
      if (ev.refusal_reason) {
        h += `<div class="note">${esc(ev.refusal_reason)}</div>`;
      }
      if (ev.low_confidence) {
        h += `<div class="note warn">Eşleşme skoru düşük (%${Math.round(ev.top_similarity * 100)}).
          Yanıtı kaynaklardan doğrulayın.</div>`;
      }
    }

    if (ev.sources?.length) {
      // Reddedilse bile parçalar gösterilir: "hiç bulunamadı" ile
      // "bulundu ama kullanılmadı" ayrımı teşhis için kritik.
      const used = ev.sources.filter((s) => s.cited).length;
      const label = ev.candidates_only
        ? `Bulunan en yakın ${ev.sources.length} parça — yanıtta kullanılmadı`
        : `Kaynaklar — ${used}/${ev.sources.length} parça kullanıldı`;
      h += `<details class="srcs"${ev.candidates_only ? " open" : ""}><summary>${label}</summary>`;
      for (const s of ev.sources) {
        const cov = s.coverage != null ? ` · kelime %${Math.round(s.coverage * 100)}` : "";
        h += `<div class="src ${s.cited ? "used" : ""} ${s.below_threshold ? "weak" : ""}" id="s${s.n}">
          <div class="src-top">
            <span class="src-n">K${s.n}</span>
            <span class="src-file">${esc(s.file)}</span>
            <span class="src-loc">${esc(s.locator || "")}${s.section ? " · " + esc(s.section) : ""}</span>
            <span class="src-sim">%${Math.round(s.similarity * 100)}${cov}</span>
          </div>
          <div class="src-body">${esc(s.text)}</div></div>`;
      }
      h += `</details>`;
    }
    h += `<div class="meta">${ev.elapsed_s} sn · ${ev.retrieved} aday tarandı · ${ev.used} parça kullanıldı</div>`;
    ui.extra.innerHTML = h;

    ui.a.querySelectorAll(".cite").forEach((c) => {
      c.onclick = () => {
        const d = ui.extra.querySelector(".srcs");
        if (d) d.open = true;
        const el = ui.extra.querySelector("#s" + c.dataset.n);
        if (el) {
          el.scrollIntoView({ block: "center", behavior: "smooth" });
          el.classList.add("flash");
          setTimeout(() => el.classList.remove("flash"), 1200);
        }
      };
    });
  }

  boot();
  E.input.focus();
})();
