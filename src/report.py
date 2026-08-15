"""Renders results/predictions.json into a self-contained HTML report.

No external assets: the page must work offline and inside a strict CSP.
Colour roles follow a validated palette - Roma = blue, Fiorentina = red,
pareggio = neutral grey (a diverging pair with a neutral midpoint, which is
exactly what a 1X2 market is).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

SEQ = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
       "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281", "#0d366b"]


def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f}%"


def fair(p: float) -> str:
    return f"{1 / p:.2f}" if p > 0 else "-"


def _seq_color(v: float, vmax: float) -> str:
    if vmax <= 0:
        return SEQ[0]
    i = int(round((v / vmax) ** 0.55 * (len(SEQ) - 1)))
    return SEQ[max(0, min(len(SEQ) - 1, i))]


# --------------------------------------------------------------------------
# components
# --------------------------------------------------------------------------

def stat_tiles(p: dict) -> str:
    tiles = [
        ("Vittoria Roma", p["home"], "roma"),
        ("Pareggio", p["draw"], "draw"),
        ("Vittoria Fiorentina", p["away"], "fio"),
    ]
    cells = "".join(
        f'<div class="tile t-{cls}">'
        f'<div class="tile-label">{label}</div>'
        f'<div class="tile-value">{pct(v)}</div>'
        f'<div class="tile-sub">quota equa {fair(v)}</div>'
        f'</div>' for label, v, cls in tiles)
    return f'<div class="tiles">{cells}</div>'


def stacked_methods(rows: list[tuple[str, dict, str]]) -> str:
    """100% stacked bars: one row per method, three segments."""
    bars = []
    for name, p, note in rows:
        h, d, a = p["home"], p["draw"], p["away"]
        seg = (
            f'<div class="seg s-roma" style="flex:{h:.5f}"><span>{pct(h,0)}</span></div>'
            f'<div class="gap"></div>'
            f'<div class="seg s-draw" style="flex:{d:.5f}"><span>{pct(d,0)}</span></div>'
            f'<div class="gap"></div>'
            f'<div class="seg s-fio" style="flex:{a:.5f}"><span>{pct(a,0)}</span></div>'
        )
        bars.append(
            f'<div class="bar-row"><div class="bar-name">{name}'
            f'<em>{note}</em></div><div class="bar">{seg}</div></div>')
    legend = (
        '<div class="legend">'
        '<span><i class="sw s-roma"></i>Roma</span>'
        '<span><i class="sw s-draw"></i>Pareggio</span>'
        '<span><i class="sw s-fio"></i>Fiorentina</span></div>')
    return legend + "".join(bars)


def heatmap(matrix: list[list[float]], n: int = 6) -> str:
    vmax = max(max(r[:n + 1]) for r in matrix[:n + 1])
    head = "".join(f"<th>{j}</th>" for j in range(n + 1))
    rows = []
    for i in range(n + 1):
        cells = []
        for j in range(n + 1):
            v = matrix[i][j]
            dark = v > vmax * 0.45
            cells.append(
                f'<td style="background:{_seq_color(v, vmax)}"'
                f' class="{"hi" if dark else ""}">{v * 100:.1f}</td>')
        rows.append(f"<tr><th>{i}</th>{''.join(cells)}</tr>")
    return (
        '<div class="scroll"><table class="heat">'
        f'<caption>Probabilita % di ogni risultato esatto. Righe = gol Roma, colonne = gol Fiorentina.</caption>'
        f'<thead><tr><th></th>{head}</tr></thead><tbody>{"".join(rows)}</tbody>'
        "</table></div>")


def hbars(items: list[tuple[str, float]], cls: str, vmax: float | None = None) -> str:
    vmax = vmax or max((v for _, v in items), default=1.0)
    out = []
    for label, v in items:
        w = 0 if vmax <= 0 else v / vmax * 100
        out.append(
            f'<div class="hb"><div class="hb-l">{label}</div>'
            f'<div class="hb-t"><div class="hb-f {cls}" style="width:{w:.2f}%"></div></div>'
            f'<div class="hb-v">{pct(v)}</div></div>')
    return "".join(out)


def tornado(rows: list[dict]) -> str:
    span = max(abs(r["delta_p_home_pp"]) for r in rows) or 1.0
    out = []
    for r in rows:
        d = r["delta_p_home_pp"]
        w = abs(d) / span * 50
        left = 50 - w if d < 0 else 50
        cls = "s-fio" if d < 0 else "s-roma"
        out.append(
            f'<div class="tb"><div class="tb-l">{r["param"]} = {r["value"]}</div>'
            f'<div class="tb-t"><div class="tb-axis"></div>'
            f'<div class="tb-f {cls}" style="left:{left:.2f}%;width:{w:.2f}%"></div></div>'
            f'<div class="tb-v">{d:+.1f} pp</div></div>')
    return "".join(out)


def form_split(ctx: dict) -> str:
    """Andata vs ritorno per-game scoring rates for both sides.

    The single most consequential thing in the data, so it gets its own view
    rather than being buried in the ratings breakdown.
    """
    rows = []
    for team, cls in (("Roma", "s-roma"), ("Fiorentina", "s-fio")):
        sp = ctx["teams"][team].get("recent_split")
        if not sp:
            continue
        for half, label in (("first_half", "Andata"), ("second_half", "Ritorno")):
            h = sp[half]
            gf, ga = h["goals_for"] / h["played"], h["goals_against"] / h["played"]
            pts = h.get("points")
            rows.append(
                f'<tr><td><i class="sw {cls}"></i>{team}</td><td>{label}</td>'
                f'<td>{"&mdash;" if pts is None else pts}</td>'
                f"<td>{gf:.2f}</td><td>{ga:.2f}</td><td>{gf - ga:+.2f}</td></tr>")
    return (
        '<div class="scroll"><table>'
        "<thead><tr><th>Squadra</th><th>Girone</th><th>Punti</th>"
        "<th>Gol fatti/partita</th><th>Gol subiti/partita</th><th>Differenza</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody>"
        "<caption>Fra andata e ritorno la Roma peggiora su entrambi i fronti, la Fiorentina "
        "migliora su entrambi. I punti per girone della Roma non erano reperibili; i gol si. "
        "I gol per girone della Fiorentina sono derivati dai punti.</caption></table></div>")


def kv_grid(pairs: list[tuple[str, str]]) -> str:
    return '<div class="kv">' + "".join(
        f'<div><span>{k}</span><strong>{v}</strong></div>' for k, v in pairs) + "</div>"


# --------------------------------------------------------------------------
# page
# --------------------------------------------------------------------------

CSS = """
:root{
  color-scheme:light;
  --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --mono:ui-monospace,"SF Mono","Cascadia Mono",Menlo,Consolas,monospace;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --rule:#c3c2b7; --ring:rgba(11,11,11,.10);
  --roma:#2a78d6; --fio:#e34948; --draw:#c3c2b7; --good:#0ca30c; --warn:#fab219;
  --heat-ink:#0b0b0b;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  color-scheme:dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --rule:#383835; --ring:rgba(255,255,255,.10);
  --roma:#3987e5; --fio:#e66767; --draw:#55544e; --good:#0ca30c; --warn:#fab219;
  --heat-ink:#0b0b0b;
}}
:root[data-theme="dark"]{
  color-scheme:dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#fff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --rule:#383835; --ring:rgba(255,255,255,.10);
  --roma:#3987e5; --fio:#e66767; --draw:#55544e; --good:#0ca30c; --warn:#fab219;
  --heat-ink:#0b0b0b;
}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
  font:15px/1.55 var(--sans);}
.wrap{max-width:1080px;margin:0 auto;padding:36px 20px 64px;
  display:flex;flex-direction:column;gap:38px}
header{border-bottom:1px solid var(--rule);padding-bottom:22px}
.eyebrow{font:600 11px/1 var(--mono);letter-spacing:.13em;text-transform:uppercase;
  color:var(--muted);margin:0 0 12px}
h1{font-size:30px;line-height:1.15;margin:0 0 8px;letter-spacing:-.02em;text-wrap:balance}
.sub{color:var(--ink2);font-size:14px;margin:0}
.stamp{font:11.5px/1.5 var(--mono);color:var(--muted);margin-top:10px}
section{display:flex;flex-direction:column;gap:14px}
h2{font-size:18px;margin:0;letter-spacing:-.01em;text-wrap:balance}
h2+.note{margin-top:-8px}
.note{color:var(--ink2);font-size:13.5px;margin:0;max-width:68ch}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:12px;padding:20px}
a:focus-visible,td:focus-visible{outline:2px solid var(--roma);outline-offset:2px}

.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:12px;
  padding:18px 18px 16px;border-top:3px solid var(--rule)}
.tile.t-roma{border-top-color:var(--roma)} .tile.t-fio{border-top-color:var(--fio)}
.tile.t-draw{border-top-color:var(--muted)}
.tile-label{font:600 11px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--ink2)}
.tile-value{font-size:42px;line-height:1.05;margin:10px 0 3px;letter-spacing:-.025em}
.tile-sub{font:12px/1.4 var(--mono);color:var(--muted)}

.legend{display:flex;gap:18px;font:11.5px/1 var(--mono);letter-spacing:.06em;text-transform:uppercase;align-items:center;color:var(--ink2);margin-bottom:14px;flex-wrap:wrap}
.legend i,td .sw{display:inline-block;width:11px;height:11px;border-radius:3px;
  margin-right:7px;vertical-align:-1px;flex:none}
.sw.s-roma,.seg.s-roma,.hb-f.s-roma,.tb-f.s-roma{background:var(--roma)}
.sw.s-fio,.seg.s-fio,.hb-f.s-fio,.tb-f.s-fio{background:var(--fio)}
.sw.s-draw,.seg.s-draw{background:var(--draw)}

.bar-row{display:grid;grid-template-columns:170px 1fr;gap:14px;align-items:center;
  margin-bottom:10px}
.bar-name{font-size:13.5px}
.bar-name em{display:block;font:11px/1.35 var(--mono);font-style:normal;color:var(--muted);margin-top:3px}
.bar{display:flex;height:30px;border-radius:5px;overflow:hidden}
.gap{width:2px;background:var(--surface);flex:none}
.seg{display:flex;align-items:center;justify-content:center;min-width:0}
.seg span{font-size:11.5px;color:#fff;font-variant-numeric:tabular-nums;
  padding:0 2px;white-space:nowrap;overflow:hidden}
.seg.s-draw span{color:var(--ink)}

.hb{display:grid;grid-template-columns:150px 1fr 58px;gap:10px;align-items:center;
  margin-bottom:7px;font-size:13px}
.hb-t{height:12px;background:var(--grid);border-radius:4px;overflow:hidden}
.hb-f{height:100%;border-radius:4px}
.hb-v{text-align:right;color:var(--ink2);font-variant-numeric:tabular-nums;font-size:12.5px}

.tb{display:grid;grid-template-columns:210px 1fr 72px;gap:10px;align-items:center;
  margin-bottom:7px;font:11.5px/1.4 var(--mono)}
.tb-t{position:relative;height:14px;background:var(--grid);border-radius:4px}
.tb-axis{position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:var(--rule)}
.tb-f{position:absolute;top:0;height:100%;border-radius:3px}
.tb-v{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink2)}

.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1px;
  background:var(--grid);border:1px solid var(--grid);border-radius:10px;overflow:hidden}
.kv div{background:var(--surface);padding:13px 15px}
.kv span{display:block;font:600 10.5px/1 var(--mono);letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.kv strong{font-size:19px;font-weight:600;letter-spacing:-.01em}

.scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:13px}
caption{caption-side:bottom;text-align:left;color:var(--muted);font-size:12px;padding-top:12px;line-height:1.5;max-width:68ch}
th,td{padding:8px 10px;text-align:right;font-variant-numeric:tabular-nums;
  border-bottom:1px solid var(--grid)}
th:first-child,td:first-child{text-align:left;font-variant-numeric:normal}
thead th{color:var(--muted);font:600 10.5px/1 var(--mono);letter-spacing:.09em;text-transform:uppercase;white-space:nowrap;padding-bottom:10px}
table.heat td{text-align:center;color:var(--heat-ink);border:2px solid var(--surface);
  border-radius:3px;min-width:46px;font-size:12px}
table.heat td.hi{color:#fff}
table.heat th{color:var(--ink2);background:transparent;border-bottom:none;text-align:center}

.two{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:720px){.two{grid-template-columns:1fr}
  .bar-row{grid-template-columns:1fr}.hb{grid-template-columns:110px 1fr 52px}
  .tb{grid-template-columns:140px 1fr 62px}}
ul.caveats{margin:0;padding-left:20px;color:var(--ink2);font-size:13.5px}
ul.caveats li{margin-bottom:7px}
.pill{display:inline-block;font:10.5px/1.7 var(--mono);letter-spacing:.06em;text-transform:uppercase;padding:2px 9px;border-radius:20px;
  border:1px solid var(--ring);color:var(--ink2);margin-left:8px;vertical-align:2px}
.pos{color:var(--good)} .neg{color:var(--ink2)}
footer{padding-top:20px;border-top:1px solid var(--rule);
  color:var(--muted);font-size:12.5px;line-height:1.6;max-width:78ch}
"""


def build(pred: dict, sens: list[dict], ctx: dict) -> str:
    p = pred["probabilities"]
    fin = p["fused_FINAL"]
    mc = pred["monte_carlo"]
    dm = pred["derived_markets"]
    lam = pred["lambdas"]

    methods = stacked_methods([
        ("Modello (Dixon-Coles)", p["model_only"], "solo forza squadre + contesto"),
        ("Mercato (Shin de-vig)", p["market_shin"], "quote Betfair ripulite dal margine"),
        ("Monte Carlo", p["monte_carlo"], f"{mc['n']:,} simulazioni".replace(",", ".")),
        ("FUSIONE FINALE", fin, "log-pooling, peso mercato 60%"),
    ])

    ml = pred.get("ml", {})
    ml_html = ""
    if ml.get("enabled"):
        cv = ml["cv_report"]
        ens = ml["fixture_prediction"]["ensemble_mean"]
        dis = ml["disagreement_vs_analytical"]
        rows = "".join(
            f"<tr><td>{k}</td><td>{v['log_loss']:.4f}</td><td>{v['brier']:.4f}</td>"
            f"<td>{pct(v['accuracy'])}</td></tr>"
            for k, v in cv.items())
        ml_html = f"""
<section>
  <h2>Layer machine learning <span class="pill">scaffolding, non nuova informazione</span></h2>
  <p class="note">Tre learner (regressione logistica, gradient boosting, random forest)
  addestrati su {ml['training_rows']:,} partite sintetiche generate da un processo
  <em>diverso</em> da Dixon-Coles (vantaggio casa per squadra, scoring sovradisperso,
  effetto fatica). Servono a due cose: una pipeline di calibrazione gia pronta e un
  segnale di disaccordo col modello analitico. Non aggiungono informazione su questa
  partita finche non si caricano risultati reali.</p>
  <div class="card">
    <div class="scroll"><table>
      <thead><tr><th>Modello</th><th>Log loss (CV)</th><th>Brier</th><th>Accuratezza</th></tr></thead>
      <tbody>{rows}</tbody>
      <caption>Cross-validation 4-fold. Il baseline e la frequenza di classe: qualsiasi
      modello che non lo batte non sta imparando niente.</caption>
    </table></div>
    <p class="note" style="margin-top:16px">Previsione ensemble su questa partita:
      <strong>{pct(ens['home'])}</strong> Roma / <strong>{pct(ens['draw'])}</strong> X /
      <strong>{pct(ens['away'])}</strong> Fiorentina &mdash; disaccordo col Dixon-Coles
      analitico: {dis['home'] * 100:+.1f} pp sulla Roma.</p>
  </div>
</section>"""

    edges = "".join(
        f"<tr><td>{r['selection']}</td><td>{r['price']:.2f}</td>"
        f"<td>{pct(r['implied_prob'])}</td><td>{pct(r['model_prob'])}</td>"
        f"<td class=\"{'pos' if r['ev_per_unit'] > 0 else 'neg'}\">{r['ev_per_unit'] * 100:+.1f}%</td>"
        f"<td>{r['kelly_quarter'] * 100:.1f}%</td></tr>"
        for r in pred["value_bets"])

    scorers_roma = sorted(pred["scorers"]["Roma"].items(),
                          key=lambda kv: -kv[1]["anytime"])[:8]
    scorers_fio = sorted(pred["scorers"]["Fiorentina"].items(),
                         key=lambda kv: -kv[1]["anytime"])[:8]
    vmax = max(scorers_roma[0][1]["anytime"], scorers_fio[0][1]["anytime"])

    caveats = "".join(f"<li>{c}</li>" for c in pred["known_unknowns"])

    return f"""<title>Roma-Fiorentina Forecast</title>
<style>{CSS}</style>
<div class="wrap">
<header>
  <p class="eyebrow">Serie A 2026/27 &middot; Giornata 1</p>
  <h1>Roma &ndash; Fiorentina &middot; modello predittivo</h1>
  <p class="sub">{pred['fixture']['competition']} &middot; {pred['fixture']['venue']}
     &middot; lunedi 24 agosto 2026, 20:45 CEST</p>
  <p class="stamp">Generato il {pred['generated_at'][:16].replace('T', ' ')} UTC &middot;
     {mc['n']:,} simulazioni Monte Carlo &middot; peso mercato 60%</p>
</header>

<section>
  <h2>Risultato finale del modello</h2>
  <p class="note">Fusione di modello statistico e mercato. La quota equa e 1/probabilita:
  se il bookmaker offre di piu, c'e valore teorico.</p>
  {stat_tiles(fin)}
</section>

<section>
  <h2>Da dove viene il numero</h2>
  <p class="note">Quattro viste sulla stessa partita. Il modello puro e piu prudente sulla
  Roma del mercato: il mercato conosce infortuni e formazioni che qui non abbiamo. La
  fusione geometrica prende il 60% dal mercato e il 40% dal modello.</p>
  <div class="card">{methods}</div>
</section>

<section>
  <h2>Perche non basta guardare la classifica</h2>
  <p class="note">Sull'aggregato di 38 giornate questa e terza contro quindicesima. Sulle ultime 19
  e una Roma in calo contro una Fiorentina in crescita: i viola hanno chiuso il girone di ritorno
  al settimo posto con 29 punti, davanti a Milan e Bologna. Il modello pesa il ritorno al 40%,
  dimezzato per la Fiorentina perche l'allenatore che ha prodotto quella forma (Vanoli) non c'e piu.</p>
  <div class="card">{form_split(ctx)}</div>
</section>

<section>
  <h2>Gol attesi e mercati derivati</h2>
  <p class="note">Tutti questi numeri escono dalla stessa matrice dei risultati esatti,
  quindi sono coerenti fra loro per costruzione.</p>
  {kv_grid([
      ("xG Roma", f"{lam['fused']['home']:.2f}"),
      ("xG Fiorentina", f"{lam['fused']['away']:.2f}"),
      ("Totale gol attesi", f"{mc['goals']['expected_total']:.2f}"),
      ("Over 1.5", pct(dm['totals']['over_1.5'])),
      ("Over 2.5", pct(dm['totals']['over_2.5'])),
      ("Under 2.5", pct(dm['totals']['under_2.5'])),
      ("Over 3.5", pct(dm['totals']['over_3.5'])),
      ("Gol/Gol (BTTS)", pct(dm['btts']['btts_yes'])),
      ("Clean sheet Roma", pct(dm['clean_sheets']['home_clean_sheet'])),
      ("Clean sheet Fiorentina", pct(dm['clean_sheets']['away_clean_sheet'])),
      ("Roma vince di 2+", pct(mc['margin']['p_home_by_2plus'])),
      ("Handicap Roma -1", pct(dm['asian_handicap']['home_-1.0']['home_cover'])),
      ("Doppia chance 1X", pct(dm['double_chance']['1X'])),
  ])}
</section>

<section>
  <h2>Matrice dei risultati esatti</h2>
  <p class="note">Il risultato singolo piu probabile e
  <strong>{dm['top_scorelines'][0]['score']}</strong> con {pct(dm['top_scorelines'][0]['prob'])},
  ma nessuno supera il 13%: e questo il punto. Un pronostico su risultato esatto e quasi
  sempre sbagliato anche quando il modello e giusto.</p>
  <div class="card">{heatmap(pred['score_matrix_fused'])}</div>
</section>

<section>
  <h2>Marcatori (probabilita di segnare almeno un gol)</h2>
  <p class="note">Livello piu debole del modello: le quote-gol per giocatore sono stime a
  priori su formazioni non ancora confermate. Da leggere come ordinamento, non come numeri.</p>
  <div class="two">
    <div class="card">
      <div class="legend"><span><i class="sw s-roma"></i>Roma</span></div>
      {hbars([(k, v['anytime']) for k, v in scorers_roma], 's-roma', vmax)}
    </div>
    <div class="card">
      <div class="legend"><span><i class="sw s-fio"></i>Fiorentina</span></div>
      {hbars([(k, v['anytime']) for k, v in scorers_fio], 's-fio', vmax)}
    </div>
  </div>
</section>

<section>
  <h2>Sensibilita: cosa muove davvero la previsione</h2>
  <p class="note">Effetto di ogni parametro su P(vittoria Roma), in punti percentuali
  rispetto al caso base. Un parametro che muove meno di 1 pp e decorazione. Quello che
  muove di piu e il rinforzo stimato della Fiorentina sul mercato: e li che serve
  informazione vera, non altro tuning.</p>
  <div class="card">{tornado(sens)}</div>
</section>

{ml_html}

<section>
  <h2>Valore rispetto alle quote</h2>
  <p class="note">EV per unita puntata alle quote Betfair osservate. Kelly frazionario
  (un quarto) e la sizing prudente standard. EV negativo su tutte e tre le vie significa
  semplicemente che il mercato e efficiente e il modello non ha trovato niente.</p>
  <div class="card"><div class="scroll"><table>
    <thead><tr><th>Esito</th><th>Quota</th><th>Implicita</th><th>Modello</th>
      <th>EV</th><th>Kelly 1/4</th></tr></thead>
    <tbody>{edges}</tbody>
  </table></div></div>
</section>

<section>
  <h2>Cosa non sappiamo</h2>
  <p class="note">Elenco esplicito dei buchi nei dati. Ogni voce e un punto in cui il
  modello puo sbagliare per mancanza di input, non per errore di metodo.</p>
  <div class="card"><ul class="caveats">{caveats}</ul></div>
</section>

<footer>
  Modello: Dixon-Coles con correzione bassi punteggi (rho={pred['config']['rho']}),
  shrinkage stagionale {pred['config']['shrink']}, Monte Carlo con incertezza sui
  parametri (sigma {mc['sigma_used']:.2f}), fusione log-lineare col mercato de-viggato
  alla Shin. Dati raccolti via ricerca web: nessun feed statistico diretto era
  raggiungibile da questo ambiente. Non e un consiglio di scommessa.
</footer>
</div>"""


def main() -> Path:
    import pipeline
    import ratings
    pred = json.loads((RESULTS / "predictions.json").read_text(encoding="utf-8"))
    ctx = ratings.load_context()
    sens = pipeline.sensitivity()
    keep = [r for r in sens if abs(r["delta_p_home_pp"]) > 1e-9]
    keep.sort(key=lambda r: -abs(r["delta_p_home_pp"]))
    html = build(pred, keep[:12], ctx)
    out = RESULTS / "report.html"
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    print(main())
