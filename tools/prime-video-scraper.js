/*
 * Prime Video: esporta la cronologia di visione (serie, episodi, film).
 *
 * USO
 *   1. Apri il browser, accedi ad Amazon e vai alla pagina della cronologia:
 *        https://www.primevideo.com/settings/watch-history
 *      (oppure, da Amazon.it: Prime Video > Impostazioni > Cronologia visualizzazioni)
 *   2. Apri la console degli strumenti sviluppatore (F12 > scheda "Console").
 *      Se Chrome chiede di digitare "allow pasting", fallo, poi incolla.
 *   3. Incolla TUTTO questo file e premi Invio.
 *   4. Aspetta: lo script scorre la pagina fino in fondo (anche qualche minuto
 *      se la cronologia e lunga). Al termine scarica due file:
 *        - prime_video_cronologia.csv   (una riga per titolo/episodio, separatore ";")
 *        - prime_video_cronologia.json  (righe + riepilogo per serie + dati grezzi)
 *      Se il browser blocca il secondo download, consenti "download multipli".
 *
 * SICUREZZA
 *   Lo script legge soltanto la pagina. Non clicca MAI su pulsanti di
 *   eliminazione/rimozione: clicca solo su "mostra altro / espandi episodi".
 *   Non invia dati da nessuna parte: tutto resta nel tuo browser.
 *
 * Se qualche campo risulta vuoto, e normale: Amazon cambia spesso l'HTML.
 * Il JSON contiene anche il testo grezzo di ogni riga ("raw") per correggere
 * il parsing senza dover rifare la raccolta. Dopo l'esecuzione, in console
 * trovi `window.__primeHistory` e, con CFG.debug = true, l'HTML dei primi item.
 */
(async () => {
  const CFG = {
    maxRounds: 600,        // limite di sicurezza sui cicli di scroll
    pauseMs: 1200,         // attesa dopo ogni scroll/click
    stableRoundsToStop: 4, // cicli senza novita prima di fermarsi
    debug: false,          // true: stampa l'HTML dei primi item in console
    sep: ';',              // separatore CSV (";" per Excel italiano)
  };

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();

  // ---------- date ----------
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

  // ---------- raccolta: scroll + espansione ----------
  const container =
    document.querySelector('[data-automation-id="activity-history-items"]') ||
    document.querySelector('main') ||
    document.body;

  const MORE = /(mostra|carica|vedi|visualizza|show|load|view|see)\s*(altri|altro|more|all|tutt)|altri episodi|more episodes|espandi|expand/i;
  const DANGER = /elimin|rimuov|cancell|delete|remove|cancel|nascondi|hide/i;
  const clicked = new WeakSet();

  function leavesCount() {
    return [...container.querySelectorAll('li')].filter((li) => !li.querySelector('li')).length;
  }

  function clickExpanders() {
    let n = 0;
    const cands = container.querySelectorAll('button, [role="button"], a[role="button"], [aria-expanded="false"]');
    for (const el of cands) {
      if (clicked.has(el)) continue;
      const label = clean(el.innerText || el.getAttribute('aria-label') || '');
      if (DANGER.test(label) || DANGER.test(el.getAttribute('aria-label') || '')) continue;
      const isToggle = el.getAttribute('aria-expanded') === 'false';
      if (!isToggle && !MORE.test(label)) continue;
      clicked.add(el);
      try { el.click(); n++; } catch (_) { /* ignora */ }
    }
    return n;
  }

  console.log('[prime] Avvio raccolta: non chiudere la scheda...');
  let stable = 0, lastH = 0, lastCount = 0;
  for (let i = 0; i < CFG.maxRounds && stable < CFG.stableRoundsToStop; i++) {
    window.scrollTo(0, document.documentElement.scrollHeight);
    const clickedNow = clickExpanders();
    await sleep(CFG.pauseMs);
    const h = document.documentElement.scrollHeight;
    const c = leavesCount();
    if (h === lastH && c === lastCount && clickedNow === 0) stable++;
    else stable = 0;
    lastH = h; lastCount = c;
    if (i % 5 === 0) console.log(`[prime] giro ${i + 1}: ${c} elementi trovati`);
  }
  window.scrollTo(0, 0);
  console.log(`[prime] Scroll finito: ${lastCount} elementi. Estraggo i dati...`);

  // ---------- estrazione ----------
  const EP_RE = /(?:episodio|episode|ep\.?)\s*(\d+)/i;
  const SEASON_RE = /(?:stagione|season)\s*(\d+)/i;
  const SE_COMPACT = /\bS(\d{1,2})\s*[,·\-]?\s*E(\d{1,3})\b/i;

  const titleOf = (el) => {
    const h = el.querySelector('h1,h2,h3,h4,[role="heading"],a[href*="/detail/"],a');
    return clean(h ? h.innerText : (el.innerText || '').split('\n')[0]);
  };
  const asinOf = (el) => {
    const a = el.querySelector('a[href*="/detail/"]');
    const m = a && a.getAttribute('href').match(/\/detail\/([A-Z0-9]{10})/i);
    return m ? m[1] : '';
  };
  const linesOf = (el) =>
    (el.innerText || '').split('\n').map(clean).filter(Boolean);

  let leaves = [...container.querySelectorAll('li')].filter((li) => !li.querySelector('li'));

  // Fallback: nessuna <li>, usa i link ai titoli e risali finche non trovi una data
  if (!leaves.length) {
    const seen = new Set();
    leaves = [...container.querySelectorAll('a[href*="/detail/"]')]
      .map((a) => {
        let el = a;
        for (let i = 0; i < 5 && el.parentElement; i++) {
          el = el.parentElement;
          if (linesOf(el).some((l) => parseDate(l))) break;
        }
        return el;
      })
      .filter((el) => (seen.has(el) ? false : seen.add(el)));
  }

  const rows = [];
  let currentDate = '';
  for (const el of leaves) {
    const lines = linesOf(el);
    const raw = lines.join(' | ');
    let dateLine = lines.find((l) => parseDate(l));
    if (dateLine) currentDate = dateLine;      // la data vale anche per gli item successivi
    const dateRaw = dateLine || currentDate;

    const parentLi = el.parentElement && el.parentElement.closest('li');
    const parentTitle = parentLi ? titleOf(parentLi) : '';
    const ownTitle = titleOf(el);

    const text = raw;
    const sm = text.match(SE_COMPACT);
    const season = sm ? +sm[1] : (text.match(SEASON_RE) || [])[1] || '';
    const episode = sm ? +sm[2] : (text.match(EP_RE) || [])[1] || '';
    const isEpisode = !!(season || episode || parentTitle);

    // Titolo serie: dal li genitore se esiste, altrimenti il titolo dell'item
    const series = isEpisode ? (parentTitle || ownTitle) : '';
    // Titolo episodio: la riga che non e data/stagione/episodio-solo
    const epTitle = isEpisode
      ? lines.find((l) => !parseDate(l) && l !== series && !/^(stagione|season|episodio|episode)\s*\d+$/i.test(l)) || ''
      : '';

    rows.push({
      tipo: isEpisode ? 'episodio' : 'film_o_titolo',
      titolo: isEpisode ? series : ownTitle,
      stagione: season,
      episodio: episode,
      titolo_episodio: isEpisode && epTitle !== series ? epTitle : '',
      data_visione: parseDate(dateRaw || '') || '',
      data_testo: dateRaw || '',
      asin: asinOf(el),
      raw,
    });
  }

  // ---------- riepilogo per serie ----------
  const bySeries = new Map();
  for (const r of rows.filter((r) => r.tipo === 'episodio')) {
    const s = bySeries.get(r.titolo) || { serie: r.titolo, episodi_visti: 0, stagioni: new Set(), prima: '', ultima: '' };
    s.episodi_visti++;
    if (r.stagione) s.stagioni.add(+r.stagione);
    if (r.data_visione) {
      if (!s.prima || r.data_visione < s.prima) s.prima = r.data_visione;
      if (!s.ultima || r.data_visione > s.ultima) s.ultima = r.data_visione;
    }
    bySeries.set(r.titolo, s);
  }
  const summary = [...bySeries.values()]
    .map((s) => ({ ...s, stagioni: [...s.stagioni].sort((a, b) => a - b) }))
    .sort((a, b) => b.episodi_visti - a.episodi_visti);

  const films = rows.filter((r) => r.tipo !== 'episodio');
  console.log(`[prime] Totale righe: ${rows.length} | serie: ${summary.length} | film/altro: ${films.length}`);
  console.table(summary.slice(0, 25));

  if (CFG.debug) {
    leaves.slice(0, 3).forEach((el, i) => console.log(`[prime][debug] item ${i}:`, el.outerHTML.slice(0, 1500)));
  }

  // ---------- download ----------
  const csvCell = (v) => {
    const s = String(v ?? '');
    return new RegExp(`[${CFG.sep}"\\n]`).test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const cols = ['tipo', 'titolo', 'stagione', 'episodio', 'titolo_episodio', 'data_visione', 'data_testo', 'asin', 'raw'];
  const csv = '﻿' + [cols.join(CFG.sep), ...rows.map((r) => cols.map((c) => csvCell(r[c])).join(CFG.sep))].join('\n');

  const download = (name, content, type) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([content], { type }));
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  window.__primeHistory = { rows, summary };
  download('prime_video_cronologia.csv', csv, 'text/csv;charset=utf-8');
  await sleep(800);
  download(
    'prime_video_cronologia.json',
    JSON.stringify({ esportato_il: new Date().toISOString(), url: location.href, rows, summary }, null, 2),
    'application/json'
  );
  console.log('[prime] Fatto. File scaricati: prime_video_cronologia.csv e .json');
})();
