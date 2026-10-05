/*
 * Prime Video: esporta la cronologia di visione, EPISODI COMPRESI (v2).
 *
 * USO
 *   1. Vai su https://www.primevideo.com/settings/watch-history e RICARICA la
 *      pagina (F5), cosi tutte le serie sono chiuse.
 *   2. F12 > Console. Incolla TUTTO il file (apri il link "raw" e usa Ctrl+A,
 *      Ctrl+C), premi Invio. Se Chrome lo chiede, scrivi prima `allow pasting`.
 *   3. Aspetta: scorre la pagina e apre ogni "Episodi guardati" per leggere gli
 *      episodi. Con una cronologia lunga possono servire diversi minuti.
 *   4. Scarica: prime_video_cronologia_v2.csv e prime_video_cronologia_v2.json
 *      (il JSON contiene anche TUTTO il testo grezzo della pagina).
 *
 * SICUREZZA
 *   Solo lettura. Non clicca mai su pulsanti con "elimina/rimuovi/delete/remove".
 *   Non invia nulla fuori dal tuo browser.
 */
(async () => {
  const CFG = {
    maxRounds: 800,
    pauseMs: 1000,
    stableRoundsToStop: 5,
    sep: ';',
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();

  // <parse>
  const MONTHS = {
    gen: 1, jan: 1, feb: 2, mar: 3, apr: 4, mag: 5, may: 5, giu: 6, jun: 6,
    lug: 7, jul: 7, ago: 8, aug: 8, set: 9, sep: 9, ott: 10, oct: 10,
    nov: 11, dic: 12, dec: 12,
  };
  const iso = (y, m, d) =>
    m >= 1 && m <= 12 && d >= 1 && d <= 31
      ? `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
      : null;
  function parseDate(str) {
    const s = clean(str).toLowerCase().replace(/\./g, '').replace(/,/g, '');
    let m = s.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$/);
    if (m) {
      const a = +m[1], b = +m[2], y = +m[3];
      if (a > 12) return iso(y, b, a);
      if (b > 12) return iso(y, a, b);
      return /\.com$/.test(location.hostname) ? iso(y, a, b) : iso(y, b, a);
    }
    m = s.match(/^(\d{1,2})\s+([a-zà-ù]+)\s+(\d{4})$/);
    if (m && MONTHS[m[2].slice(0, 3)]) return iso(+m[3], MONTHS[m[2].slice(0, 3)], +m[1]);
    m = s.match(/^([a-zà-ù]+)\s+(\d{1,2})\s+(\d{4})$/);
    if (m && MONTHS[m[1].slice(0, 3)]) return iso(+m[3], MONTHS[m[1].slice(0, 3)], +m[2]);
    return null;
  }

  // Ogni voce parte da una riga-data. Poi: titolo, "Episodi guardati"/"Elimina il
  // film..." (tipo) e, se la serie e aperta, le righe degli episodi (dettagli).
  const CONTROL = [
    [/^episodi guardati$/i, 'serie'],
    [/^watched episodes$/i, 'serie'],
    [/^elimina il film/i, 'film'],
    [/^remove (this )?(movie|film)/i, 'film'],
    [/^elimina un evento/i, 'evento live'],
    [/^elimina gli episodi/i, 'end'],
    [/^remove (these )?episodes/i, 'end'],
  ];
  function parseLines(lines) {
    const out = [];
    let cur = null;
    for (const l of lines) {
      const d = parseDate(l);
      if (d) {
        cur = { data: d, data_testo: l, tipo: '', titolo: '', dettagli: [] };
        out.push(cur);
        continue;
      }
      if (!cur) continue;
      const c = CONTROL.find(([rx]) => rx.test(l));
      if (c) {
        if (c[1] !== 'end' && !cur.tipo) cur.tipo = c[1];
        continue;
      }
      if (!cur.titolo && !cur.tipo) cur.titolo = l;
      else cur.dettagli.push(l);
    }
    return out;
  }
  // </parse>

  // ---------- raccolta: scroll + apertura di ogni "Episodi guardati" ----------
  const container =
    document.querySelector('[data-automation-id="activity-history-items"]') ||
    document.querySelector('main') ||
    document.body;

  const TOGGLE = /^(episodi guardati|watched episodes|mostra altro|mostra di pi[uù]|mostra tutto|show more|show all|vedi altro|altri episodi|more episodes|espandi|expand)$/i;
  const DANGER = /elimin|rimuov|cancell|delete|remove|cancel|nascondi|hide/i;
  const clicked = new WeakSet();
  const toggles = [];

  function expandAll() {
    let n = 0;
    for (const el of container.querySelectorAll('span, div, button, a, p, summary, li')) {
      if (el.children.length > 0 || clicked.has(el)) continue;
      const label = clean(el.textContent);
      if (!label || label.length > 40 || !TOGGLE.test(label) || DANGER.test(label)) continue;
      const host = el.closest('[aria-expanded]');
      if (host && host.getAttribute('aria-expanded') === 'true') { clicked.add(el); continue; }
      clicked.add(el);
      toggles.push(el);
      try { el.click(); n++; } catch (_) { /* ignora */ }
    }
    return n;
  }

  console.log('[prime] Avvio: non chiudere la scheda...');
  let stable = 0, lastH = 0, lastLen = 0;
  for (let i = 0; i < CFG.maxRounds && stable < CFG.stableRoundsToStop; i++) {
    window.scrollTo(0, document.documentElement.scrollHeight);
    const n = expandAll();
    await sleep(CFG.pauseMs);
    const h = document.documentElement.scrollHeight;
    const len = container.innerText.length;
    stable = h === lastH && len === lastLen && n === 0 ? stable + 1 : 0;
    lastH = h; lastLen = len;
    if (i % 5 === 0) console.log(`[prime] giro ${i + 1}: ${len} caratteri, ${toggles.length} serie aperte`);
  }
  window.scrollTo(0, 0);

  // ---------- estrazione ----------
  const lines = container.innerText.split('\n').map(clean).filter(Boolean);
  const entries = parseLines(lines);
  const series = entries.filter((e) => e.tipo === 'serie');
  const withEps = series.filter((e) => e.dettagli.length);
  console.log(`[prime] Voci: ${entries.length} | serie: ${series.length} | con episodi: ${withEps.length} | film: ${entries.filter((e) => e.tipo === 'film').length}`);

  if (series.length && withEps.length < series.length * 0.5) {
    console.warn('[prime] Pochi episodi trovati. Mi serve questo HTML (copialo e incollalo in chat):');
    const t = toggles[0];
    const box = t && (t.closest('li') || (t.parentElement && t.parentElement.parentElement));
    console.log(box ? box.outerHTML.slice(0, 3000) : '(nessun pulsante "Episodi guardati" trovato)');
  }

  // ---------- download ----------
  const csvCell = (v) => {
    const s = String(v ?? '');
    return new RegExp(`[${CFG.sep}"\\n]`).test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const cols = ['data', 'data_testo', 'tipo', 'titolo', 'n_dettagli', 'dettagli'];
  const csv = '﻿' + [
    cols.join(CFG.sep),
    ...entries.map((e) => [e.data, e.data_testo, e.tipo, e.titolo, e.dettagli.length, e.dettagli.join(' / ')].map(csvCell).join(CFG.sep)),
  ].join('\n');

  const download = (name, content, type) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([content], { type }));
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  window.__primeHistory = { entries, lines };
  download('prime_video_cronologia_v2.csv', csv, 'text/csv;charset=utf-8');
  await sleep(800);
  download(
    'prime_video_cronologia_v2.json',
    JSON.stringify({ esportato_il: new Date().toISOString(), url: location.href, entries, lines }, null, 1),
    'application/json'
  );
  console.log('[prime] Fatto. Scaricati prime_video_cronologia_v2.csv e .json');
})();
