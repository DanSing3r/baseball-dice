#!/usr/bin/env python3
"""
Checks for Baseball Dice.  Run this before and after any change:

    python3 check.py            # a couple of seconds
    python3 check.py --long     # wider samples, tighter tolerances

Two kinds of check.  The invariants must hold in every game -- runs must
reconcile with the line score, a player must not be on two bases at once.  The
baselines are statistical: the game is tuned to produce roughly real baseball,
and a rules change that quietly moves the run environment is a regression even
when nothing crashes.  Tolerances are set wide enough not to flake and tight
enough to catch a real shift; if you change the rules on purpose, update the
expected value here in the same commit.

No dependencies, and it runs on the system python.
"""

from __future__ import annotations

import random
import sys

import baseball_dice as bd

FAILURES: list = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print("  %-46s %s%s" % (name, "ok" if ok else "FAIL",
                            "" if ok else "  <- " + detail))
    if not ok:
        FAILURES.append(name)


def near(name: str, got: float, want: float, tol: float, unit: str = "") -> None:
    check("%s %.2f%s (want %.2f +/- %.2f)" % (name, got, unit, want, tol),
          abs(got - want) <= tol, "off by %.2f" % abs(got - want))


# --------------------------------------------------------------------------
def chart_integrity() -> None:
    cells = [c for row in bd.CHART for c in row]
    check("chart has 36 cells", len(cells) == 36, str(len(cells)))
    check("every cell is in the legend",
          all(c in bd.LEGEND for c in cells),
          str(set(cells) - set(bd.LEGEND)))
    counts = {c: cells.count(c) for c in set(cells)}
    expected = {"K": 8, "GO": 7, "FO": 6, "1B": 5, "BB": 3, "XB": 3,
                "PO": 2, "LO": 1, "E": 1}
    check("cell counts unchanged", counts == expected, str(counts))
    check("XB table covers all six faces", sorted(bd.XB_TABLE) == list(range(1, 7)))


def one_game_invariants(g: bd.Game) -> None:
    """Everything that must be true of any finished game."""
    for t in (g.away, g.home):
        assert sum(p.r for p in t.lineup) == t.runs, "player runs vs team runs"
        assert sum(p.rbi for p in t.lineup) == t.runs, "rbi vs runs"
        assert sum(p.h for p in t.lineup) == t.hits, "player hits vs team hits"
        assert sum(c for c in t.line if c != "X") == t.runs, "line score vs runs"
        assert all(p.h <= p.ab for p in t.lineup), "hits exceed at-bats"
        assert all(p.r >= 0 and p.rbi >= 0 for p in t.lineup), "negative stat"
        halves = [h for h in g.halves if h["team"] == t.name]
        assert sum(h["runs"] for h in halves) == t.runs, "half runs"
        assert sum(h["hits"] for h in halves) == t.hits, "half hits"
        assert len(t.line) <= len(halves) + 1, "more line entries than halves"
    assert g.away.runs != g.home.runs, "game finished tied"


def games(n: int) -> None:
    for coach in ("home", "away", "both", "none"):
        random.seed(1)
        bad = ""
        for _ in range(n):
            g = bd.Game(bd.make_team("A", bd.NAMES_AWAY),
                        bd.make_team("H", bd.NAMES_HOME),
                        interactive=False, coach=coach)
            g.say = lambda *a, **k: None
            try:
                g.play()
                one_game_invariants(g)
            except AssertionError as exc:
                bad = str(exc)
                break
        check("%d games, --coach %-4s invariants" % (n, coach), not bad, bad)


def baserunning(trials: int) -> None:
    """No runner may be on two bases, and a play cannot make negative outs."""
    g = bd.Game(bd.make_team("A", bd.NAMES_AWAY), bd.make_team("H", bd.NAMES_HOME),
                interactive=False)
    random.seed(5)
    bad = ""
    for _ in range(trials):
        for filled in range(8):
            bases = [(filled >> i) & 1 for i in range(3)]
            for outs in (0, 1, 2):
                for play in ("at_bat", "sacrifice", "steal"):
                    t = bd.make_team("T", bd.NAMES_AWAY)
                    t.bases = [bd.Player("R%d" % i) if b else None
                               for i, b in enumerate(bases)]
                    if play == "steal" and t.bases[0] is None:
                        continue
                    if play == "sacrifice" and not any(t.bases):
                        continue
                    if play == "at_bat":
                        _, _, _, scored, made = g.at_bat(t, outs, g.home)
                    elif play == "sacrifice":
                        _, _, _, scored, made = g.sacrifice(t, outs)
                    else:
                        _, _, _, made = g.try_steal(t)
                        scored = []
                    on = [r.name for r in t.bases if r is not None]
                    if len(on) != len(set(on)):
                        bad = "%s put a runner on two bases: %s" % (play, on)
                    if made < 0 or made > 2:
                        bad = "%s made %d outs" % (play, made)
                    if any(r is not None and r.name in on for r in scored):
                        bad = "%s left a scoring runner on base" % play
                    if bad:
                        break
    check("baserunning legality, every base/out state", not bad, bad)


def outcome_rates(n: int) -> None:
    random.seed(11)
    tally = {}
    for _ in range(n):
        code = bd.CHART[bd.d6() - 1][bd.d6() - 1]
        if code == "XB":
            code = bd.XB_TABLE[bd.d6()]
        elif code == "E":
            code = "ROE" if bd.d6() <= bd.ERROR_ON else "GO"
        tally[code] = tally.get(code, 0) + 1
    pct = lambda k: 100.0 * tally.get(k, 0) / n
    near("strikeouts", pct("K"), 22.2, 0.6, "%")
    near("walks     ", pct("BB"), 8.3, 0.4, "%")
    near("singles   ", pct("1B"), 13.9, 0.5, "%")
    near("home runs ", pct("HR"), 2.8, 0.3, "%")
    near("reach on error", pct("ROE"), 1.4, 0.2, "%")
    on_base = sum(pct(k) for k in ("BB", "1B", "2B", "3B", "HR", "ROE"))
    near("on-base   ", on_base, 31.8, 0.7, "%")


def called_play_odds(n: int) -> None:
    random.seed(21)
    safe = sum(1 for _ in range(n) if bd.d6() >= bd.STEAL_SAFE_ON)
    near("steal safe", 100.0 * safe / n, 66.7, 1.5, "%")

    def bunt_rate(bases, wanted):
        random.seed(22)
        good = 0
        for _ in range(n):
            t = bd.make_team("T", bd.NAMES_AWAY)
            t.bases = [bd.Player(x) if x else None for x in bases]
            _, _, text, scored, _ = bd.Game(
                t, bd.make_team("A", bd.NAMES_HOME),
                interactive=False).sacrifice(t, 0)
            good += wanted(t, scored, text)
        return 100.0 * good / n

    near("sacrifice advances the runner",
         bunt_rate([None, "B", None],
                   lambda t, s, x: t.bases[2] is not None), 83.3, 1.5, "%")
    near("squeeze scores the run",
         bunt_rate([None, None, "C"], lambda t, s, x: bool(s)), 66.7, 1.5, "%")


def run_environment(n: int) -> None:
    random.seed(31)
    runs = errors = hits = ab = sb = cs = 0
    for _ in range(n):
        g = bd.Game(bd.make_team("A", bd.NAMES_AWAY), bd.make_team("H", bd.NAMES_HOME),
                    interactive=False, coach="none")
        g.say = lambda *a, **k: None
        g.play()
        for t in (g.away, g.home):
            runs += t.runs
            errors += t.errors
            hits += t.hits
            ab += sum(p.ab for p in t.lineup)
            sb += sum(p.sb for p in t.lineup)
            cs += sum(p.cs for p in t.lineup)
    teams = n * 2
    near("runs per team per game", runs / teams, 4.25, 0.25)
    near("errors per team per game", errors / teams, 0.55, 0.12)
    near("league batting average", 1000.0 * hits / ab, 245, 8)
    if sb + cs:
        near("live steal success", 100.0 * sb / (sb + cs), 66.7, 4.0, "%")


def cli_smoke() -> None:
    import subprocess
    py = sys.executable
    for args in (["--chart"], ["--sim", "500"], ["--auto", "--seed", "5"]):
        r = subprocess.run([py, "baseball_dice.py"] + args,
                           capture_output=True, text=True)
        check("cli %s" % " ".join(args), r.returncode == 0 and r.stdout.strip() != "",
              r.stderr.strip()[:80])
    r = subprocess.run([py, "baseball_dice.py", "--seed", "3", "--watch-delay", "0"],
                       input="\n" * 80, capture_output=True, text=True)
    check("cli interactive play-through", r.returncode == 0, r.stderr.strip()[:80])
    # --recap must degrade politely, never crash, when the SDK is absent
    r = subprocess.run([py, "baseball_dice.py", "--auto", "--seed", "5", "--recap"],
                       capture_output=True, text=True)
    ok = r.returncode == 0 and ("THE WRAP" in r.stdout)
    check("cli --recap degrades without crashing", ok, r.stderr.strip()[:80])


def main() -> None:
    long = "--long" in sys.argv
    print("\n  CHART")
    chart_integrity()
    print("\n  INVARIANTS")
    games(400 if long else 120)
    baserunning(6 if long else 2)
    print("\n  OUTCOME RATES")
    outcome_rates(400000 if long else 60000)
    called_play_odds(200000 if long else 40000)
    print("\n  RUN ENVIRONMENT")
    run_environment(2000 if long else 400)
    print("\n  CLI")
    cli_smoke()
    print()
    if FAILURES:
        print("  %d FAILED: %s\n" % (len(FAILURES), ", ".join(FAILURES)))
        sys.exit(1)
    print("  all checks passed\n")


if __name__ == "__main__":
    main()
