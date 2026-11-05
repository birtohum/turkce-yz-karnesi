"use strict";
const $ = (s) => document.querySelector(s);
const pct = (x, d = 0) => (100 * x).toLocaleString("tr-TR", { maximumFractionDigits: d, minimumFractionDigits: d });
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const NS = "http://www.w3.org/2000/svg";
const tip = $("#tip");

function showTip(e, html) {
  tip.innerHTML = html; tip.hidden = false;
  const x = Math.min(e.clientX + 12, window.innerWidth - tip.offsetWidth - 8);
  tip.style.left = x + "px"; tip.style.top = (e.clientY + 14) + "px";
}
function hideTip() { tip.hidden = true; }

// Yatay çubuk + güven aralığı. rows: [{label, acc, lo, hi, n}]
function barChart(el, rows, baseline, opts = {}) {
  const W = Math.max(300, Math.round(el.clientWidth || 640)), rowH = opts.rowH || 30, left = Math.min(opts.left || 120, Math.round(W * 0.34)), right = 54, top = 6;
  const H = top + rows.length * rowH + 22;
  const x = (v) => left + v * (W - left - right);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.aria || "")}">`;
  for (const t of [0, .25, .5, .75, 1]) {
    s += `<line class="gridl" x1="${x(t)}" x2="${x(t)}" y1="${top}" y2="${H - 20}"/>`;
    s += `<text x="${x(t)}" y="${H - 4}" text-anchor="middle" font-size="11">${pct(t)}%</text>`;
  }
  rows.forEach((r, i) => {
    const y = top + i * rowH, bh = Math.min(14, rowH - 12), by = y + (rowH - bh) / 2;
    s += `<text x="${left - 10}" y="${by + bh / 2 + 4.5}" text-anchor="end">${esc(r.label)}</text>`;
    const w = Math.max(0, x(r.acc) - x(0));
    s += `<path class="bar" d="M${x(0)},${by}h${Math.max(0, w - 4)}a4,4 0 0 1 4,4v${bh - 8}a4,4 0 0 1 -4,4h${-Math.max(0, w - 4)}z"/>`;
    const cy = by + bh / 2;
    s += `<line class="ci" x1="${x(r.lo)}" x2="${x(r.hi)}" y1="${cy}" y2="${cy}"/>`;
    s += `<line class="ci" x1="${x(r.lo)}" x2="${x(r.lo)}" y1="${cy - 5}" y2="${cy + 5}"/>`;
    s += `<line class="ci" x1="${x(r.hi)}" x2="${x(r.hi)}" y1="${cy - 5}" y2="${cy + 5}"/>`;
    s += `<text class="val" x="${x(r.hi) + 6}" y="${cy + 4.5}">${pct(r.acc)}</text>`;
    s += `<rect class="hit" x="0" y="${y}" width="${W}" height="${rowH}" data-i="${i}"/>`;
  });
  if (baseline != null) {
    s += `<line class="base" x1="${x(baseline)}" x2="${x(baseline)}" y1="${top - 2}" y2="${H - 20}"/>`;
  }
  s += "</svg>";
  el.innerHTML = s;
  el.querySelectorAll(".hit").forEach((h) => {
    const r = rows[+h.dataset.i];
    const html = `<b>${esc(r.label)}</b><br>%${pct(r.acc, 1)} (GA %${pct(r.lo, 1)}–%${pct(r.hi, 1)})` +
      (r.n ? `<br>${r.n} soru` : "") + (baseline != null ? `<br>Şans tabanı %${pct(baseline, 1)}` : "");
    h.addEventListener("mousemove", (e) => showTip(e, html));
    h.addEventListener("mouseleave", hideTip);
  });
}

function render(R, S, Q) {
  const M = R.models, meta = R.meta, cats = Object.keys(meta.categories);
  const name = Object.fromEntries(M.map((m) => [m.id, m.name]));
  const best = M[0], worst = M[M.length - 1];
  $("#lede").innerHTML = `Wikidata'dan otomatik üretilen ${meta.n_items.toLocaleString("tr-TR")} soruyla ${M.length} açık modeli bu bilgisayarda sınadık. ` +
    `En iyisi <b>${esc(best.name)}</b>: %${pct(best.macro.acc)} (rastgele tahmin %${pct(meta.baseline_macro)}). ` +
    `En zayıfı ${esc(worst.name)}: %${pct(worst.macro.acc)}.`;

  redraw(R);

  // komşu modeller arası fark anlamlı mı
  const pairOf = (a, b) => R.pairs.find((p) => (p.a === a && p.b === b));
  const lines = [];
  for (let i = 0; i < M.length - 1; i++) {
    const p = pairOf(M[i].id, M[i + 1].id);
    lines.push(`<p>${esc(M[i].name)} − ${esc(M[i + 1].name)}: ${pct(p.diff, 1)} puan (GA ${pct(p.lo, 1)} – ${pct(p.hi, 1)}) — ${p.sig ? "anlamlı" : "<b>anlamlı değil</b>"}</p>`);
  }
  $("#sig").innerHTML = "<p>Sıralamada yan yana iki model arasındaki fark (eşleştirilmiş bootstrap, aynı sorular):</p>" + lines.join("");

  // sağlamlık tablosu ve geri kalanı aşağıda
  renderRest(R, S, Q, name);
}

function redraw(R) {
  const M = R.models, meta = R.meta, cats = Object.keys(meta.categories);
  barChart($("#board"), M.map((m) => ({ label: m.name, ...m.macro })), meta.baseline_macro, { left: 112, aria: "Model sıralaması" });
  const cg = $("#cats"); cg.innerHTML = "";
  for (const c of cats) {
    const info = meta.categories[c];
    const d = document.createElement("div"); d.className = "cat";
    const n = info.public + info.heldout;
    d.innerHTML = `<h3>${esc(info.label)}</h3><p class="note">${n} soru · şans tabanı %${pct(info.baseline, 1)}</p><div class="chart"></div>`;
    cg.appendChild(d);
    const rows = M.map((m) => ({ label: m.name, ...m.cats[c] })).sort((a, b) => b.acc - a.acc);
    barChart(d.querySelector(".chart"), rows, info.baseline, { rowH: 26, left: 112, aria: info.label });
  }
}

function renderRest(R, S, Q, name) {
  const M = R.models, meta = R.meta;

  // sağlamlık tablosu
  let t = `<thead><tr><th>Model</th><th>İki ifade de doğru</th><th>Yalnız biri doğru</th><th>1. ifade</th><th>2. ifade</th><th>Fark (GA)</th>` +
    `<th>4 şıkta en sık harf</th><th>Doğru şık A/B/C/D iken başarı</th><th>2 şıkta “A” oranı</th><th>Biçim hatası</th><th>Ret</th><th>Açık / saklı bölüm</th></tr></thead><tbody>`;
  for (const m of M) {
    const L = Object.entries(m.letters4).sort((a, b) => b[1] - a[1])[0];
    t += `<tr><td>${esc(m.name)}</td><td>%${pct(m.consistency.both)}</td><td>%${pct(m.consistency.one)}</td>` +
      `<td>%${pct(m.wording.v0)}</td><td>%${pct(m.wording.v1)}</td>` +
      `<td>${m.wording.diff >= 0 ? "+" : ""}${pct(m.wording.diff, 1)} (${pct(m.wording.lo, 1)}…${pct(m.wording.hi, 1)})${m.wording.sig ? "" : " ·"}</td>` +
      `<td>${L[0]} (%${pct(L[1])})</td><td>${"ABCD".split("").map((k) => pct(m.pos_acc4[k])).join(" / ")}</td><td>%${pct(m.pickA2)}</td>` +
      `<td>%${pct(m.status.format, 1)}</td><td>%${pct(m.status.refusal, 1)}</td>` +
      `<td>%${pct(m.split.public)} / %${pct(m.split.heldout)}</td></tr>`;
  }
  $("#robust").innerHTML = t + "</tbody>";
  $("#robustnotes").innerHTML = [
    "Fark sütununda “·” işareti, iki ifade arasındaki farkın %95 güven aralığının sıfırı içerdiğini (anlamlı olmadığını) gösterir.",
    "Doğru cevaplar harflere eşit dağıtıldı; yanlılıksız bir model her harfi yaklaşık %25 (iki şıkta “A”yı %50) seçer.",
    "“Yalnız biri doğru” yüksekse model aynı bilgiyi ifadeye ya da şık sırasına göre farklı yanıtlıyor demektir: bilgiden çok tahmin.",
    `Saklı bölüm (%20) sitede gösterilmez ve depoya konmaz; SHA-256: <code>${meta.heldout_sha256.slice(0, 16)}…</code>. Gelecekte bir modelin açık sorularda saklılara göre belirgin iyi çıkması sızıntı işareti olur.`,
  ].concat((R.aux || []).length ? [
    `Ayrıca denendi, sıralamaya alınmadı: ${R.aux.map((m) => `${esc(m.name)} (yanıtların %${pct(m.status.format)}'i biçim hatası)`).join(", ")}. ` +
    "Bu modeller (bu hesabın önceki Tohum projesinde Qwen3 üzerine yapılmış ince ayarlar) harf yazmak yerine çoğunlukla yeni bir soru ürettiler; doğru sohbet şablonuyla elle denendiğinde de aynısı oldu. Bu bir bilgi ölçümü değil, talimat izleme bozukluğu olduğu için puanları karşılaştırılmadı."
  ] : []).map((x) => `<li>${x}</li>`).join("");

  // örnekler
  $("#samples").innerHTML = S.map((s) => {
    const mm = M.map((m) => {
      const r = s.models[m.id];
      const mark = r.status === "correct" ? `<span class="ok">✓</span>` : r.status === "wrong" ? `<span class="no">✗</span>` : `<span class="no">${r.status === "refusal" ? "ret" : "biçim"}</span>`;
      return `<li>${mark} <span class="m">${esc(m.name)}:</span> ${esc(r.out || "—")}</li>`;
    }).join("");
    return `<div class="sample"><div class="cat">${esc(meta.categories[s.cat].label)}</div><p class="q">${esc(s.prompt)}</p>` +
      `<p class="note" style="margin:0 0 6px">Doğru cevap: <b>${esc(s.answer)}</b></p><ul>${mm}</ul></div>`;
  }).join("");

  quiz(Q, name);
  method(meta, M);
  let rt; window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => redraw(R), 150); });
}

function quiz(Q, name) {
  const el = $("#quiz");
  let qs, i, picks;
  function start() {
    const pool = Q.items.slice();
    for (let k = pool.length - 1; k > 0; k--) { const j = Math.floor(Math.random() * (k + 1)); [pool[k], pool[j]] = [pool[j], pool[k]]; }
    qs = pool.slice(0, 10); i = 0; picks = []; show();
  }
  function show() {
    if (i >= qs.length) return done();
    const q = qs[i];
    el.innerHTML = `<p class="prog">Soru ${i + 1} / ${qs.length}</p><p class="qq">${esc(q.q)}</p>` +
      q.o.map((o, k) => `<button class="opt" data-k="${k}">${"ABCD"[k]}) ${esc(o)}</button>`).join("") +
      `<div class="nx"></div>`;
    el.querySelectorAll(".opt").forEach((b) => b.addEventListener("click", () => answer(+b.dataset.k)));
  }
  function answer(k) {
    const q = qs[i]; picks.push(k === q.a);
    el.querySelectorAll(".opt").forEach((b) => {
      b.disabled = true;
      const kk = +b.dataset.k;
      if (kk === q.a) b.classList.add("right"); else if (kk === k) b.classList.add("wrongpick");
    });
    const nx = el.querySelector(".nx");
    nx.innerHTML = `<button class="btn">${i + 1 < qs.length ? "Sonraki" : "Sonucu gör"}</button>`;
    nx.querySelector("button").addEventListener("click", () => { i++; show(); });
  }
  function done() {
    const me = picks.filter(Boolean).length;
    const rows = Q.models.map((m, j) => ({ m, s: qs.reduce((a, q) => a + q.m[j], 0) }));
    rows.push({ m: "_sen", s: me });
    rows.sort((a, b) => b.s - a.s || (a.m === "_sen" ? -1 : 1));
    el.innerHTML = `<p class="prog">Sonuç</p><p class="score">${me} / 10</p>` +
      `<table><tbody>${rows.map((r) => `<tr><td>${r.m === "_sen" ? "<b>Sen</b>" : esc(name[r.m])}</td><td>${r.s} / 10</td></tr>`).join("")}</tbody></table>` +
      `<p class="note" style="margin-top:10px">Modellerin puanı aynı 10 sorunun ilk ifadesindeki yanıtlarından. 10 soruluk bir sınavda birkaç puanlık fark şanstan kaynaklanabilir.</p>` +
      `<button class="btn sec">Yeni 10 soru</button>`;
    el.querySelector("button").addEventListener("click", start);
  }
  start();
}

function method(meta, M) {
  const c = meta.categories;
  $("#method").innerHTML = `
<h3>Sorular</h3>
<p>Tüm sorular Wikidata SPARQL sorgularıyla otomatik üretildi; elle yazılmış soru yok. Kategoriler: ${Object.values(c).map((x) => esc(x.label).toLowerCase()).join(", ")}.
Yalnızca tek ve tutarlı değeri olan kayıtlar kullanıldı: aynı adlı ilçe ya da göl birden fazla ilde geçiyorsa, bir kişinin birden çok ya da kaynaksız doğum tarihi varsa, iki il aynı plaka kodunu taşıyorsa (Wikidata'da Konya 53, Uşak 62 yazıyordu; bu dört il atıldı) soru üretilmedi.
Nüfus karşılaştırmasında her ilin Wikidata'daki en son tarihli nüfus kaydı kullanıldı (çoğunlukla 2021); nüfusları %15'ten yakın iller ve önceki kayıtta sırası ters olan çiftler atıldı. Rakımda farkı 200 metreden az şehir çiftleri atıldı.
Plaka kodu sorularının yarısı serbest yanıtlı (sayı yazılır), geri kalan her şey 2 ya da 4 şıklı.</p>
<h3>Modeller</h3>
<p>${M.map((m) => `${esc(m.name)} (${esc(m.note)})`).join("; ")}. Hepsi Ollama ile, sıcaklık 0, tek tek, bir RTX 3060 (12 GB) üzerinde çalıştırıldı. Qwen tabanlı modellerde “düşünme” kapatıldı. Her soruya aynı Türkçe sistem istemi verildi: yalnızca harfi ya da sayıyı yaz.</p>
<h3>Puanlama ve istatistik</h3>
<p>Yanıt deterministik olarak çözümlendi: baştaki harf, “Cevap: B” kalıbı ya da tek bir seçenek metniyle birebir eşleşme. Hiçbiri yoksa yanıt “biçim hatası” (ya da “bilmiyorum” gibi ifadeler varsa “ret”) sayıldı ve yanlış kabul edildi.
Bir sorunun puanı iki ifadesinin ortalamasıdır; güven aralıkları sorular üzerinde 10.000 tekrarlı yüzdelik bootstrap ile, genel puanda kategori içinde yeniden örnekleyerek hesaplandı. Model farkları aynı sorular üzerinde eşleştirilmiş bootstrap ile sınandı.</p>
<h3>Sınırlar</h3>
<ul>
<li>Doğru cevap Wikidata'nın söylediğidir. Wikidata hatasızsa değil: yukarıdaki plaka örneği gibi yakaladığımız çelişkiler atıldı, yakalayamadıklarımız sorularda kalmış olabilir. Rakım değerleri ölçüm noktasına göre değişir.</li>
<li>Ölçülen şey “küçük, yerel çalışan açık modeller”dir. Büyük ticari modeller (ücretli ya da anahtar gerektiren) bu turda yok.</li>
<li>Çoktan seçmeli biçim bilgiyi olduğundan iyi gösterebilir: yanlış şıklar rastgele seçildiği için bazen eleme ile bulunabilir.</li>
<li>Doğum yılı sorusu, Türkçe Vikipedi maddesi olan ve en çok dilde maddesi bulunan kişilerden seçildi; listede sporcular ağırlıkta.</li>
<li>Tek bir istem kalıbı kullanıldı; başka istemler ya da birkaç örnekli (few-shot) sorma puanları değiştirebilir.</li>
</ul>`;
}

Promise.all(["data/results.json", "data/samples.json", "data/quiz.json"].map((u) => fetch(u).then((r) => r.json())))
  .then(([R, S, Q]) => render(R, S, Q))
  .catch((e) => { $("#lede").textContent = "Veri yüklenemedi: " + e; });
