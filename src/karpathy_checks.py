"""Diagnostic ladder for the ML layer, after Karpathy's "A Recipe for Training
Neural Networks" (karpathy.github.io/2019/04/25/recipe/).

His central claim is that neural nets fail silently: the code runs, the loss
goes down, and the model is still broken. The defence is a fixed sequence of
cheap experiments where you state what you expect BEFORE running it, so a
surprise is a bug rather than a discovery. That transfers to this project
exactly, and it is worth more here than any extra model would be.

Four of his steps port directly:

  1. INPUT-INDEPENDENT BASELINE. Zero the inputs. The model must get WORSE. If
     it doesn't, it was never using the features and the whole rating pipeline
     is decorative. This is the single highest-value check in the file.

  2. OVERFIT ONE BATCH. Hand the model a handful of examples and let it
     memorise them. It must reach near-zero loss. If it can't, the loss, the
     labels or the optimiser is wrong - no amount of tuning will fix it.

  3. A BASELINE LADDER. Every added ingredient must beat the simpler thing
     below it, measured, not assumed. Anything that doesn't beat its predecessor
     gets deleted.

  4. FIX THE SEED, VARY IT DELIBERATELY. Report the spread across seeds so a
     "gain" smaller than seed noise is never mistaken for a gain.

Run: python3 karpathy_checks.py
"""

from __future__ import annotations

import json

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import log_loss
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import ml

PASS, FAIL = "PASS", "FAIL"


def _fresh():
    return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))


def check_input_independent(df, seed: int = 7) -> dict:
    """Karpathy step: 'verify a decreasing loss against an input-independent
    baseline'. Zero every feature; the model must lose predictive power and
    collapse to the class prior."""
    X = df[ml.FEATURES].values
    y = df["result"].values
    cv = StratifiedKFold(4, shuffle=True, random_state=seed)

    real = log_loss(y, cross_val_predict(_fresh(), X, y, cv=cv,
                                         method="predict_proba"), labels=[0, 1, 2])
    zeroed = log_loss(y, cross_val_predict(_fresh(), np.zeros_like(X), y, cv=cv,
                                           method="predict_proba"), labels=[0, 1, 2])
    prior = np.bincount(y, minlength=3) / len(y)
    prior_ll = log_loss(y, np.tile(prior, (len(y), 1)), labels=[0, 1, 2])

    gain = zeroed - real
    return {
        "check": "input-independent baseline",
        "expectation": "zeroed inputs must be clearly worse than real inputs, and land on the class prior",
        "log_loss_real_inputs": float(real),
        "log_loss_zeroed_inputs": float(zeroed),
        "log_loss_class_prior": float(prior_ll),
        "information_gain_from_features": float(gain),
        "status": PASS if gain > 0.01 and abs(zeroed - prior_ll) < 0.01 else FAIL,
    }


def check_label_shuffle(df, seed: int = 7) -> dict:
    """Complement to the above: shuffle the LABELS. The model must now be
    unable to beat the prior. If it can, the CV is leaking."""
    X = df[ml.FEATURES].values
    y = df["result"].values
    rng = np.random.default_rng(seed)
    y_shuf = rng.permutation(y)
    cv = StratifiedKFold(4, shuffle=True, random_state=seed)
    ll = log_loss(y_shuf, cross_val_predict(_fresh(), X, y_shuf, cv=cv,
                                            method="predict_proba"), labels=[0, 1, 2])
    prior = np.bincount(y_shuf, minlength=3) / len(y_shuf)
    prior_ll = log_loss(y_shuf, np.tile(prior, (len(y_shuf), 1)), labels=[0, 1, 2])
    return {
        "check": "shuffled labels",
        "expectation": "with destroyed labels the model must NOT beat the prior (no leakage)",
        "log_loss_shuffled": float(ll),
        "log_loss_class_prior": float(prior_ll),
        "status": PASS if ll >= prior_ll - 0.005 else FAIL,
    }


def check_overfit_batch(df, k: int = 60, seed: int = 7) -> dict:
    """Karpathy step: 'overfit one batch'.

    His wording matters: increase the CAPACITY of the model and verify it can
    reach the lowest achievable loss. The first version of this check used the
    logistic regression from the ladder and failed - correctly, but for an
    uninteresting reason: a linear model cannot memorise overlapping classes no
    matter how little regularisation it has, so the test was measuring the
    hypothesis class rather than the plumbing. Run it with an unbounded tree,
    which HAS the capacity to memorise, and the check does what it is for: if
    this cannot fit, then labels, features or the loss are wired wrong.

    The linear model is kept in the output as the contrast.
    """
    sub = df.sample(k, random_state=seed)
    X, y = sub[ml.FEATURES].values, sub["result"].values

    big = DecisionTreeClassifier(random_state=seed)          # unbounded depth
    big.fit(X, y)
    ll = log_loss(y, big.predict_proba(X), labels=[0, 1, 2])
    acc = float((big.predict(X) == y).mean())

    lin = make_pipeline(StandardScaler(), LogisticRegression(max_iter=20000, C=1e6))
    lin.fit(X, y)
    lin_acc = float((lin.predict(X) == y).mean())

    return {
        "check": "overfit a single batch",
        "expectation": f"a high-capacity model must memorise {k} examples: accuracy 1.0, loss ~0",
        "n": k,
        "train_log_loss_high_capacity": float(ll),
        "train_accuracy_high_capacity": acc,
        "train_accuracy_linear_for_contrast": lin_acc,
        "note": "the linear model cannot and should not reach 1.0 here - the classes genuinely overlap",
        "status": PASS if acc > 0.99 and ll < 0.05 else FAIL,
    }


def check_baseline_ladder(df, seed: int = 7, noise_floor: float = 0.0159) -> dict:
    """Every rung must beat the one below it BY MORE THAN THE NOISE FLOOR.

    Comparing rungs at 1e-4 tolerance was the wrong test: it calls a 0.002
    difference meaningful when the seed-to-seed spread is 0.016. Rungs that tie
    within the noise floor are reported as ties - and a tie is itself a finding,
    because it means the extra features are not earning their place.
    """
    y = df["result"].values
    n = len(y)
    cv = StratifiedKFold(4, shuffle=True, random_state=seed)

    rungs = {}
    prior = np.bincount(y, minlength=3) / n
    rungs["0_class_prior"] = float(log_loss(y, np.tile(prior, (n, 1)), labels=[0, 1, 2]))

    always_home = np.tile([0.98, 0.01, 0.01], (n, 1))
    rungs["1_always_home"] = float(log_loss(y, always_home, labels=[0, 1, 2]))

    # rung 2: only the two expected-goal features
    X2 = df[["exp_lam_h", "exp_lam_a"]].values
    rungs["2_expected_goals_only"] = float(log_loss(
        y, cross_val_predict(_fresh(), X2, y, cv=cv, method="predict_proba"),
        labels=[0, 1, 2]))

    # rung 3: raw ratings, no engineered features
    X3 = df[["att_h", "def_h", "att_a", "def_a"]].values
    rungs["3_raw_ratings"] = float(log_loss(
        y, cross_val_predict(_fresh(), X3, y, cv=cv, method="predict_proba"),
        labels=[0, 1, 2]))

    # rung 4: the full feature set
    X4 = df[ml.FEATURES].values
    rungs["4_full_features"] = float(log_loss(
        y, cross_val_predict(_fresh(), X4, y, cv=cv, method="predict_proba"),
        labels=[0, 1, 2]))

    order = ["0_class_prior", "2_expected_goals_only", "3_raw_ratings", "4_full_features"]
    steps, regressions = [], []
    for i in range(len(order) - 1):
        lo, hi = order[i], order[i + 1]
        delta = rungs[lo] - rungs[hi]          # positive = the higher rung is better
        verdict = ("migliora" if delta > noise_floor else
                   "peggiora" if delta < -noise_floor else "pari (dentro il rumore)")
        steps.append({"from": lo, "to": hi, "delta_log_loss": float(delta),
                      "verdict": verdict})
        if delta < -noise_floor:
            regressions.append(f"{lo} -> {hi}")

    return {
        "check": "baseline ladder",
        "expectation": "no rung may be WORSE than the one below by more than the noise floor; ties mean the added features are not earning their place",
        "noise_floor_used": noise_floor,
        "log_loss_by_rung": rungs,
        "steps": steps,
        "regressions": regressions,
        "verdict": ("nessuna feature aggiuntiva batte le sole lambda attese: "
                    "il set completo si puo potare" if not regressions
                    else "una rung peggiora oltre il rumore"),
        "status": PASS if not regressions else FAIL,
    }


def check_seed_spread(seeds=(1, 7, 13, 21, 42), n_seasons: int = 4) -> dict:
    """Karpathy step: fix the seed, then vary it on purpose. Any 'improvement'
    smaller than this spread is noise, not a result."""
    lls = []
    for s in seeds:
        df = ml.generate_synthetic_league(n_seasons=n_seasons, seed=s)
        X, y = df[ml.FEATURES].values, df["result"].values
        cv = StratifiedKFold(4, shuffle=True, random_state=s)
        lls.append(log_loss(y, cross_val_predict(_fresh(), X, y, cv=cv,
                                                 method="predict_proba"),
                            labels=[0, 1, 2]))
    lls = np.array(lls)
    return {
        "check": "seed spread",
        "expectation": "report the noise floor so smaller 'gains' are not believed",
        "seeds": list(seeds),
        "log_losses": [float(x) for x in lls],
        "mean": float(lls.mean()),
        "std": float(lls.std()),
        "noise_floor_2sigma": float(2 * lls.std()),
        "status": PASS,
    }


def run_all(n_seasons: int = 8, seed: int = 7) -> dict:
    df = ml.generate_synthetic_league(n_seasons=n_seasons, seed=seed)
    checks = [
        check_input_independent(df, seed),
        check_label_shuffle(df, seed),
        check_overfit_batch(df, seed=seed),
        check_baseline_ladder(df, seed),
        check_seed_spread(),
    ]
    return {
        "rows": int(len(df)),
        "checks": checks,
        "all_passed": all(c["status"] == PASS for c in checks),
    }


if __name__ == "__main__":
    r = run_all()
    for c in r["checks"]:
        print(f"[{c['status']}] {c['check']}")
        print(f"        atteso: {c['expectation']}")
        for k, v in c.items():
            if k in ("check", "status", "expectation"):
                continue
            print(f"        {k}: {v}")
        print()
    print("TUTTI I CHECK PASSATI" if r["all_passed"] else "QUALCOSA E ROTTO")
