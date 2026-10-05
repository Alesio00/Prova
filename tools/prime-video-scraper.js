/*
 * Prime Video: esporta la cronologia di visione, EPISODI COMPRESI (v3).
 *
 * USO
 *   1. Vai su https://www.primevideo.com/settings/watch-history e ricarica (F5).
 *   2. F12 > Console. Incolla TUTTO il file (apri il link "raw", Ctrl+A, Ctrl+C),
 *      premi Invio. Se Chrome lo chiede, scrivi prima `allow pasting`.
 *   3. Aspetta: carica tutta la cronologia scorrendo, poi apre ogni "Episodi
 *      guardati" a gruppi di 20 e legge gli episodi. Alla fine scarica
 *      prime_video_cronologia_v3.csv e prime_video_cronologia_v3.json.
 *
 * SICUREZZA
 *   Solo lettura. Clicca soltanto le etichette "Episodi guardati" (aprono un
 *   menu a tendina) e, se esiste, un pulsante "mostra altro". Non tocca mai
 *   i pulsanti "Elimina ..." ne i form di cancellazione. Nulla esce dal browser.
 */
(async () => {
  const CFG = {
    maxRounds: 800,
    pauseMs: 1200,       // attesa tra uno scroll e l'altro
    stableRounds: 6,     // giri senza nuovi elementi prima di fermarsi
    batch: 20,           // quante serie aprire alla volta
    batchPauseMs: 500,
    sep: ';',
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const linesOf = (el) => (el.innerText || '').split('\n').map(clean).filter(Boolean);

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
  // </parse>

  const ITEM = 'li[data-automation-id^="wh-item-"]';
  const container =
    document.querySelector('[data-automation-id="activity-history-items"]') ||
    document.querySelector('main') ||
    document.body;
  const count = () => container.querySelectorAll(ITEM).length;

  // ---------- 1. carica tutta la cronologia ----------
  const MORE = /^(mostra|carica|vedi|visualizza|show|load|view|see)\b.*\b(altr\w*|more|tutt\w*|all)\b/i;
  const DANGER = /elimin|rimuov|cancell|delete|remove|cancel|nascondi|hide/i;
  const clickLoadMore = () => {
    for (const b of container.querySelectorAll('button, [role="button"], a[role="button"]')) {
      const t = clean(b.innerText || b.getAttribute('aria-label'));
      if (!t || t.length > 50 || DANGER.test(t) || !MORE.test(t) || b.closest('form')) continue;
      try { b.click(); return true; } catch (_) { /* ignora */ }
    }
    return false;
  };

  console.log('[prime] Carico la cronologia: non chiudere la scheda...');
  let stable = 0, last = -1;
  for (let i = 0; i < CFG.maxRounds && stable < CFG.stableRounds; i++) {
    const items = container.querySelectorAll(ITEM);
    if (items.length) items[items.length - 1].scrollIntoView({ block: 'end' });
    window.scrollTo(0, document.documentElement.scrollHeight);
    const clicked = clickLoadMore();
    await sleep(CFG.pauseMs);
    const c = count();
    stable = c === last && !clicked ? stable + 1 : 0;
    last = c;
    if (i % 5 === 0) console.log(`[prime] giro ${i + 1}: ${c} elementi`);
  }
  console.log(`[prime] Cronologia caricata: ${count()} elementi.`);

  // ---------- 2. apre ogni "Episodi guardati" ----------
  const labels = [...container.querySelectorAll('[data-testid^="wh-episodes-watched"] label')]
    .filter((l) => !(l.control && l.control.checked) && !DANGER.test(clean(l.textContent)));
  console.log(`[prime] Serie da aprire: ${labels.length}`);

  if (labels.length) {
    // prova sul primo elemento: se non compaiono episodi, avvisa e stampa l'HTML
    const first = labels[0];
    const firstItem = first.closest(ITEM);
    const before = linesOf(firstItem).length;
    first.click();
    await sleep(1500);
    const after = linesOf(firstItem).length;
    console.log(`[prime] Prova sul primo: righe ${before} -> ${after}`);
    if (after <= before) {
      console.warn('[prime] Dopo il click non compaiono nuove righe. HTML del primo elemento (incollamelo in chat):');
      console.log(firstItem.outerHTML.slice(0, 4000));
    }
    for (let i = 1; i < labels.length; i += CFG.batch) {
      labels.slice(i, i + CFG.batch).forEach((l) => { try { l.click(); } catch (_) { /* ignora */ } });
      await sleep(CFG.batchPauseMs);
      if (i % 200 < CFG.batch) console.log(`[prime] aperte ${Math.min(i + CFG.batch, labels.length)} / ${labels.length}`);
    }
    await sleep(2000);
  }

  // ---------- 3. estrazione dalla struttura reale ----------
  const entries = [];
  let curDate = '', curDateIso = '';
  for (const li of container.querySelectorAll('li')) {
    if (li.matches(ITEM)) {
      const links = [...li.querySelectorAll('a[href*="/detail/"]')];
      const titleA = links.find((a) => clean(a.textContent)) || links[0];
      const title = clean(titleA ? titleA.textContent : '') || clean(li.querySelector('img') && li.querySelector('img').alt);
      const href = titleA ? titleA.getAttribute('href') : '';
      const asin = (href.match(/\/detail\/([A-Za-z0-9]+)/) || [])[1] || '';
      const del = li.querySelector('form button[type="submit"]');
      const delText = del ? clean(del.textContent) : '';
      const tipo = /film/i.test(delText) ? 'film' : /episod/i.test(delText) ? 'serie' : /diretta|live/i.test(delText) ? 'evento live' : 'altro';
      const righe = linesOf(li);
      const dettagli = righe.filter(
        (l) => l !== title && !/^episodi guardati$/i.test(l) && !/^watched episodes$/i.test(l) && !/^(elimina|remove|delete)\b/i.test(l)
      );
      entries.push({
        data: curDateIso, data_testo: curDate, tipo, titolo: title, asin,
        id: li.getAttribute('data-automation-id'), dettagli, righe,
      });
    } else {
      const first = clean((li.innerText || '').split('\n')[0]);
      const d = parseDate(first);
      if (d) { curDate = first; curDateIso = d; }
    }
  }

  const series = entries.filter((e) => e.tipo === 'serie');
  const withEps = series.filter((e) => e.dettagli.length);
  console.log(`[prime] Voci: ${entries.length} | serie: ${series.length} (con episodi: ${withEps.length}) | film: ${entries.filter((e) => e.tipo === 'film').length} | senza data: ${entries.filter((e) => !e.data).length}`);
  if (series.length && withEps.length < series.length * 0.5) {
    console.warn('[prime] Pochi episodi letti. HTML di una serie dopo l\'apertura (incollamelo in chat):');
    const li = container.querySelector(ITEM + ' [data-testid^="wh-episodes-watched"]');
    console.log(li ? li.closest(ITEM).outerHTML.slice(0, 4000) : '(nessuna serie trovata)');
  }

  // ---------- 4. download ----------
  const csvCell = (v) => {
    const s = String(v ?? '');
    return new RegExp(`[${CFG.sep}"\\n]`).test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const cols = ['data', 'data_testo', 'tipo', 'titolo', 'n_episodi_letti', 'dettagli', 'asin'];
  const csv = '﻿' + [
    cols.join(CFG.sep),
    ...entries.map((e) => [e.data, e.data_testo, e.tipo, e.titolo, e.dettagli.length, e.dettagli.join(' / '), e.asin].map(csvCell).join(CFG.sep)),
  ].join('\n');
  const download = (name, content, type) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([content], { type }));
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };
  window.__primeHistory = { entries };
  download('prime_video_cronologia_v3.csv', csv, 'text/csv;charset=utf-8');
  await sleep(800);
  download('prime_video_cronologia_v3.json', JSON.stringify({ esportato_il: new Date().toISOString(), url: location.href, entries }, null, 1), 'application/json');
  console.log('[prime] Fatto. Scaricati prime_video_cronologia_v3.csv e .json');
})();
