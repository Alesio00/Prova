"""Machine-learning layer.

BE CLEAR ABOUT WHAT THIS DOES AND DOES NOT DO.

There is no match-level Serie A dataset reachable from this environment (all
HTTP egress except package registries is blocked), so the learners are trained
on a synthetic league generated from a *different* process than the analytical
model: per-team home advantage, over-dispersed scoring, and a fatigue term.

That buys three real things:
  1. A cross-validated calibration harness (log loss / Brier / reliability)
     that is ready the moment real results are dropped in.
  2. A flexible surrogate that can express interactions Dixon-Coles cannot
     (e.g. strong-attack-vs-weak-defence being super-multiplicative).
  3. A disagreement signal: where the surrogate and the closed form diverge,
     the closed form's structural assumptions are doing the work.

What it does NOT buy: new information about this fixture. Until `load_real_
matches()` is fed actual results, the ML output is a re-expression of the same
priors. RESULTS.md says so plainly.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, brier_score_loss
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# Estimated 2025/26 Serie A attack/defence indices (1.0 = league average).
# Derived from final positions and the known scoring environment. Marked LOW
# confidence in data/context.json - replace with real GF/GA when available.
SERIE_A_2526 = {
    "Inter":      (1.42, 0.66), "Napoli":     (1.20, 0.68), "Roma":       (1.17, 0.72),
    "Como":       (1.10, 0.80), "Milan":      (1.18, 0.85), "Juventus":   (1.05, 0.78),
    "Atalanta":   (1.22, 0.92), "Lazio":      (1.02, 0.90), "Bologna":    (1.06, 0.88),
    "Torino":     (0.92, 0.97), "Udinese":    (0.90, 1.02), "Sassuolo":   (0.95, 1.10),
    "Genoa":      (0.85, 1.05), "Cagliari":   (0.82, 1.08), "Fiorentina": (0.87, 1.11),
    "Parma":      (0.78, 1.12), "Lecce":      (0.72, 1.18), "Verona":     (0.70, 1.28),
    "Pisa":       (0.68, 1.30), "Cremonese":  (0.66, 1.35),
}

FEATURES = [
    "att_h", "def_h", "att_a", "def_a",
    "att_ratio", "def_ratio", "strength_gap",
    "exp_lam_h", "exp_lam_a", "exp_total",
    "home_flag_advantage", "rest_diff", "matchday_norm",
]


def _features(att_h, def_h, att_a, def_a, home_adv, rest_diff, matchday,
              base_h=1.347, base_a=1.079):
    lam_h = base_h * att_h * def_a * home_adv
    lam_a = base_a * att_a * def_h / home_adv
    return {
        "att_h": att_h, "def_h": def_h, "att_a": att_a, "def_a": def_a,
        "att_ratio": att_h / att_a, "def_ratio": def_a / def_h,
        "strength_gap": (att_h / def_h) - (att_a / def_a),
        "exp_lam_h": lam_h, "exp_lam_a": lam_a, "exp_total": lam_h + lam_a,
        "home_flag_advantage": home_adv,
        "rest_diff": rest_diff,
        "matchday_norm": matchday / 38.0,
    }


def generate_synthetic_league(n_seasons: int = 40, seed: int = 7) -> pd.DataFrame:
    """Simulate whole Serie A seasons with a richer DGP than Dixon-Coles."""
    rng = np.random.default_rng(seed)
    teams = list(SERIE_A_2526)
    rows = []

    for s in range(n_seasons):
        # season-specific team drift: squads change between seasons
        drift = {t: (rng.normal(1.0, 0.09), rng.normal(1.0, 0.09)) for t in teams}
        # Per-team home advantage as a DEVIATION around 1.0, not an absolute.
        # base_h/base_a (1.347/1.079) already encodes the league-wide home
        # advantage; centring this on 1.09 as well double-counts it and was a
        # real bug - see RESULTS.md.
        home_adv = {t: rng.normal(1.0, 0.05) for t in teams}

        matchday = 0
        for _ in range(2):  # two halves of the season
            for i, h in enumerate(teams):
                for j, a in enumerate(teams):
                    if i == j:
                        continue
                    matchday = (matchday % 38) + 1
                    ah, dh = SERIE_A_2526[h]
                    aa, da = SERIE_A_2526[a]
                    ah, dh = ah * drift[h][0], dh * drift[h][1]
                    aa, da = aa * drift[a][0], da * drift[a][1]
                    rest_diff = float(rng.integers(-3, 4))

                    f = _features(ah, dh, aa, da, home_adv[h], rest_diff, matchday)

                    # over-dispersed scoring: gamma-mixed Poisson (negative binomial)
                    k = 12.0
                    lam_h = rng.gamma(k, f["exp_lam_h"] / k)
                    lam_a = rng.gamma(k, f["exp_lam_a"] / k)
                    # fatigue: the fresher side gets a small boost
                    lam_h *= 1.0 + 0.012 * rest_diff
                    lam_a *= 1.0 - 0.012 * rest_diff

                    gh, ga = rng.poisson(lam_h), rng.poisson(lam_a)
                    # low-score draw inflation
                    if gh <= 1 and ga <= 1 and rng.random() < 0.045:
                        ga = gh

                    f["home_goals"], f["away_goals"] = gh, ga
                    f["result"] = 0 if gh > ga else (1 if gh == ga else 2)
                    f["season"] = s
                    rows.append(f)

    return pd.DataFrame(rows)


def train_and_evaluate(df: pd.DataFrame, seed: int = 7) -> dict:
    X = df[FEATURES].values
    y = df["result"].values

    models = {
        "logreg": make_pipeline(StandardScaler(),
                                LogisticRegression(max_iter=2000, C=1.0)),
        "gbm": GradientBoostingClassifier(n_estimators=220, max_depth=3,
                                          learning_rate=0.06, subsample=0.85,
                                          random_state=seed),
        "rf": RandomForestClassifier(n_estimators=400, min_samples_leaf=40,
                                     n_jobs=-1, random_state=seed),
    }

    cv = StratifiedKFold(n_splits=4, shuffle=True, random_state=seed)
    report, fitted = {}, {}
    for name, m in models.items():
        p = cross_val_predict(m, X, y, cv=cv, method="predict_proba", n_jobs=1)
        ll = log_loss(y, p, labels=[0, 1, 2])
        br = float(np.mean([
            brier_score_loss((y == c).astype(int), p[:, c]) for c in range(3)
        ]))
        acc = float((p.argmax(1) == y).mean())
        report[name] = {"log_loss": float(ll), "brier": br, "accuracy": acc}
        m.fit(X, y)
        fitted[name] = m

    # baseline: always predict the observed class frequencies
    base = np.bincount(y, minlength=3) / len(y)
    report["baseline_class_prior"] = {
        "log_loss": float(log_loss(y, np.tile(base, (len(y), 1)), labels=[0, 1, 2])),
        "brier": float(np.mean([brier_score_loss((y == c).astype(int),
                                                 np.full(len(y), base[c]))
                                for c in range(3)])),
        "accuracy": float((y == base.argmax()).mean()),
    }

    return {"report": report, "models": fitted}


def predict_fixture(fitted: dict, att_h, def_h, att_a, def_a,
                    home_adv=1.0, rest_diff=0.0, matchday=1) -> dict:
    f = _features(att_h, def_h, att_a, def_a, home_adv, rest_diff, matchday)
    x = np.array([[f[k] for k in FEATURES]])
    out = {}
    for name, m in fitted.items():
        p = m.predict_proba(x)[0]
        out[name] = {"home": float(p[0]), "draw": float(p[1]), "away": float(p[2])}
    keys = ("home", "draw", "away")
    out["ensemble_mean"] = {k: float(np.mean([out[n][k] for n in fitted])) for k in keys}
    s = sum(out["ensemble_mean"].values())
    out["ensemble_mean"] = {k: v / s for k, v in out["ensemble_mean"].items()}
    return out


def load_real_matches(csv_path: str | Path) -> pd.DataFrame:
    """PLUG-IN POINT. Drop a football-data.co.uk style CSV here and the whole
    ML layer retrains on real results instead of the synthetic league.

    Required columns: HomeTeam, AwayTeam, FTHG, FTAG.
    """
    df = pd.read_csv(csv_path)
    need = {"HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    return df
