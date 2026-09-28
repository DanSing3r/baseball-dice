#!/usr/bin/env python3
"""
Baseball Dice
=============

Nine innings decided entirely by dice.

Every at-bat is one roll of two six-sided dice.  The 36 equally likely
combinations map onto a result chart (run with --chart to see it).  A handful
of those results call for one extra die to settle how far the ball carried or
how the runners moved -- double plays, sacrifice flies, a runner trying to go
first to third.

    python3 baseball_dice.py                 # interactive, press Enter to roll
    python3 baseball_dice.py --auto          # let the dice fly
    python3 baseball_dice.py --chart         # print the result chart
    python3 baseball_dice.py --sim 10000     # outcome frequencies
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

# --------------------------------------------------------------------------
# The chart: rows are the first die, columns the second.  36 cells, each 1/36.
# --------------------------------------------------------------------------
CHART = [
    # 2nd die:  1     2     3     4     5     6
    ["K",  "K",  "GO", "FO", "BB", "1B"],   # 1st die = 1
    ["K",  "GO", "GO", "FO", "BB", "1B"],   # 1st die = 2
    ["K",  "GO", "E",  "FO", "PO", "1B"],   # 1st die = 3
    ["K",  "GO", "FO", "PO", "1B", "XB"],   # 1st die = 4
    ["K",  "GO", "FO", "LO", "1B", "XB"],   # 1st die = 5
    ["K",  "K",  "GO", "FO", "BB", "XB"],   # 1st die = 6
]

LEGEND = {
    "K":  "strikeout",
    "GO": "ground ball",
    "E":  "error check -- roll once more",
    "FO": "fly ball",
    "PO": "pop up",
    "LO": "line out",
    "BB": "walk",
    "1B": "single",
    "XB": "extra-base hit -- roll once more",
}

# An error check: this or under and the fielder boots it, else play it out.
ERROR_ON = 3

# A steal is safe on this or better -- 3 gives 67%, 4 gives 50%, 2 gives 83%.
# 67% sits near the real break-even, which is what makes the bench manager's
# one-in-six running rate defensible rather than a systematic leak.
STEAL_SAFE_ON = 3

# Sub-roll for XB: 1-3 double, 4 triple, 5-6 home run.
XB_TABLE = {1: "2B", 2: "2B", 3: "2B", 4: "3B", 5: "HR", 6: "HR"}

OUTFIELD = ["to left", "to left-center", "to center", "to right-center", "to right"]
INFIELD = ["to short", "to second", "to third", "to first", "back to the mound"]
K_FLAVOR = ["swinging", "looking", "on three pitches", "chasing one low and away"]

PLAY_KEYS = {"steal": "(s)teal", "bunt": "(b)unt"}

NAMES_AWAY = ["Ortega", "Blackwell", "Nakamura", "Ruiz", "Fenwick",
              "Okafor", "Delgado", "Halloran", "Petrosian"]
NAMES_HOME = ["Whitaker", "Castellanos", "Bergstrom", "Aziz", "Moody",
              "Ferreira", "Lindqvist", "Sanjay", "Rooney"]


def d6() -> int:
    return random.randint(1, 6)


# --------------------------------------------------------------------------
# Teams and players
# --------------------------------------------------------------------------
@dataclass
class Player:
    name: str
    ab: int = 0
    r: int = 0
    h: int = 0
    rbi: int = 0
    bb: int = 0
    so: int = 0
    sb: int = 0
    cs: int = 0
    sac: int = 0
    sf: int = 0
    hr: int = 0

    @property
    def avg(self) -> str:
        if self.ab == 0:
            return " .---"
        return ("%.3f" % (self.h / self.ab)).lstrip("0").rjust(5)


@dataclass
class Team:
    name: str
    lineup: List[Player]
    spot: int = 0
    runs: int = 0
    hits: int = 0
    errors: int = 0
    retired_row: int = 0            # batters retired in a row while fielding
    k_row: int = 0                  # strikeouts in a row while fielding
    line: List[int] = field(default_factory=list)
    bases: List[Optional[Player]] = field(default_factory=lambda: [None, None, None])

    def due_up(self) -> Player:
        return self.lineup[self.spot]

    def next_batter(self) -> None:
        self.spot = (self.spot + 1) % len(self.lineup)

    # -- baserunning -------------------------------------------------------
    def clear_bases(self) -> None:
        self.bases = [None, None, None]

    def advance_all(self, n: int) -> List[Player]:
        """Push every runner n bases.  Returns the runners who scored."""
        scored, new = [], [None, None, None]
        for i in range(2, -1, -1):
            runner = self.bases[i]
            if runner is None:
                continue
            if i + n >= 3:
                scored.append(runner)
            else:
                new[i + n] = runner
        self.bases = new
        return scored

    def walk_in(self, batter: Player) -> List[Player]:
        """Force-advance only the runners who have to move."""
        b = self.bases
        if b[0] is None:
            b[0] = batter
            return []
        if b[1] is None:
            b[1], b[0] = b[0], batter
            return []
        if b[2] is None:
            b[2], b[1], b[0] = b[1], b[0], batter
            return []
        scored = [b[2]]
        b[2], b[1], b[0] = b[1], b[0], batter
        return scored

    def diagram(self) -> str:
        filled = ["*" if r else "o" for r in self.bases]
        return "1B:%s 2B:%s 3B:%s" % (filled[0], filled[1], filled[2])


def make_team(name: str, names: List[str]) -> Team:
    return Team(name=name, lineup=[Player(n) for n in names])


# --------------------------------------------------------------------------
# The game
# --------------------------------------------------------------------------
class Game:
    def __init__(self, away: Team, home: Team, innings: int = 9,
                 interactive: bool = True, delay: float = 0.0,
                 coach: str = "home", watch_delay: float = 1.5):
        self.away = away
        self.home = home
        self.regulation = innings
        self.interactive = interactive
        self.delay = delay
        self.coach = coach
        self.watch_delay = watch_delay
        self.watching = False
        self.last_play = None
        self.went_deep = False          # was the batter before this one a homer
        self.lead = 0                   # who was ahead before the last play
        self.half_k = 0                 # strikeouts this half inning
        self.on_row = 0                 # batters reaching in a row this half
        self.prev_half_runs = 0         # runs in the half just finished
        self.log_width = 68

    # -- output helpers ----------------------------------------------------
    def beat(self) -> float:
        """How long to hold between lines right now.  --delay paces
        everything; otherwise a half you are only watching unspools at a
        readable clip instead of landing in one block."""
        if self.delay:
            return self.delay
        if self.interactive and self.watching:
            return self.watch_delay
        return 0.0

    def hold(self) -> None:
        """Wait one beat without printing anything."""
        pause = self.beat()
        if pause:
            time.sleep(pause)

    def say(self, text: str = "") -> None:
        print(text)
        if text.strip():
            self.hold()

    def explain(self) -> None:
        """Drop a line from each die in the last play down to what it did."""
        if self.last_play is None:
            print("   Nothing rolled yet.")
            return
        roll, who, text, side, labels = self.last_play
        at = [i for i, ch in enumerate(roll) if ch.isdigit()]
        n = min(len(at), len(labels))
        pad = "  "

        # Say plainly that this is a recap -- at the top of your half the last
        # play belongs to the other team, and a play line appearing here would
        # otherwise read as a fresh roll.
        print()
        print("   ---- last play, %s ----" % side)
        print("%s%-10s %-12s %s" % (pad, roll, who, text))
        print(pad + "".join("\u2502" if i in at[:n] else " "
                            for i in range(at[n - 1] + 1)))
        for k in range(n - 1, -1, -1):
            stem = "".join("\u2502" if i in at[:k] else " "
                           for i in range(at[k]))
            print(pad + stem + "\u2514\u2500 " + labels[k])
        print()

    def note(self, words: str) -> None:
        self.say("     -- %s" % words)

    def call_the_game(self, batting: Team, fielding: Team, batter: Player,
                      text: str, scored: list, outs: int, inning: int,
                      faced: int) -> None:
        """One line of colour when something is actually going on.  At most one
        per play, most notable first, so it stays an aside rather than a wall."""
        homer = "HOME RUN" in text
        struck_out = "strikes out" in text
        got_a_hit = ("single" in text or "double" in text or "triple" in text
                     or homer)
        reached = (batter in batting.bases or batter in scored)

        # Streaks.  Reaching on an error or a fielder's choice is not being
        # retired, even though an out was made on the play.
        retired = not reached and not got_a_hit and "walk" not in text
        fielding.retired_row = fielding.retired_row + 1 if retired else 0
        fielding.k_row = fielding.k_row + 1 if struck_out else 0
        self.on_row = self.on_row + 1 if reached else 0
        if struck_out:
            self.half_k += 1

        was_deep, self.went_deep = self.went_deep, homer
        lead_was, self.lead = self.lead, (
            (self.home.runs > self.away.runs) - (self.home.runs < self.away.runs))

        if homer and len(scored) == 4:
            return self.note("A grand slam!")
        if scored and self.away.runs + self.home.runs == len(scored):
            return self.note("The first runs of the day.")
        if homer and was_deep:
            return self.note("Back to back!  %s have gone deep twice running."
                             % batting.name)
        if homer and batter.hr > 1:
            return self.note("That is number %d on the day for %s."
                             % (batter.hr, batter.name))
        if scored and lead_was and self.lead and self.lead != lead_was:
            return self.note("The lead changes hands.")
        if scored and lead_was and not self.lead:
            return self.note("All square again.")
        if faced == 10:
            return self.note("That is the order all the way around.")
        if "double play" in text and outs < 3:
            return self.note("The double play takes the air right out of it.")
        if fielding.retired_row and fielding.retired_row % 6 == 0:
            return self.note("%s have retired %d in a row."
                             % (fielding.name, fielding.retired_row))
        if fielding.k_row == 3:
            return self.note("Three straight on strikes for %s." % fielding.name)
        if self.on_row == 3:
            return self.note("Three men aboard in a row -- this is a rally.")
        if got_a_hit and batting.hits == 1 and inning >= 6:
            return self.note("First hit of the day for %s." % batting.name)
        if got_a_hit and batter.h == 3:
            return self.note("Three hits on the day for %s." % batter.name)
        if all(batting.bases) and outs == 2:
            return self.note("Bases full, two away.")

    def call_the_half(self, batting: Team, fielding: Team, inning: int,
                      runs: int, top: bool) -> None:
        """Colour for the half inning as a whole, once it is over."""
        left = sum(1 for r in batting.bases if r is not None)
        answered, self.prev_half_runs = self.prev_half_runs and runs, runs

        if runs >= 4:
            self.note("A %d-run inning." % runs)
        elif self.half_k == 3:
            self.note("%s struck out the side." % fielding.name)
        elif batting.hits == 0 and inning >= 5:
            self.note("Through %d, %s have not allowed a hit."
                      % (inning, fielding.name))
        elif answered:
            self.note("An answer right back.")
        elif left == 3:
            self.note("The bases are left full.")
        elif (not top and inning >= 4
              and not self.away.runs and not self.home.runs):
            self.note("Still nothing on the board for either side.")

    def scorebug(self, batting: Team, outs: int) -> str:
        """Bases and outs, as shown before every play."""
        return "[%s | %d out%s]" % (
            batting.diagram(), outs, "" if outs == 1 else "s")

    def available_plays(self, batting: Team, outs: int) -> List[str]:
        """Plays that are legal in this situation, before the pitch."""
        plays = []
        if batting.bases[0] is not None and batting.bases[1] is None:
            plays.append("steal")
        # Anybody on and under two outs: a man on first or second can be moved
        # up, and a man on third can be squeezed home.
        if outs < 2 and any(batting.bases):
            plays.append("bunt")
        return plays

    def coaches_batting_team(self, top: bool) -> bool:
        """Are you the one swinging this half inning?"""
        if self.coach == "both":
            return True
        if self.coach == "none":
            return False
        return self.coach == ("away" if top else "home")

    def cpu_call(self, plays: List[str], batting: Team, outs: int,
                 inning: int) -> Optional[str]:
        """A conservative bench manager: small ball late, and not much of it."""
        squeeze = batting.bases[2] is not None and outs < 2
        move_up = batting.bases[1] is not None and outs == 0
        if "bunt" in plays and (squeeze or move_up) and inning >= 7 and d6() <= 2:
            return "bunt"
        if "steal" in plays and outs < 2 and d6() == 1:
            return "steal"
        return None

    def coach_call(self, batting: Team, outs: int, inning: int,
                   top: bool) -> str:
        """Ask whoever is managing what to do, then get on with the pitch."""
        plays = self.available_plays(batting, outs)
        # Every play is the batting team's; a defensive call would split here.
        yours = self.coaches_batting_team(top)
        mine, theirs = (plays, []) if yours else ([], plays)

        if theirs:
            call = self.cpu_call(theirs, batting, outs, inning)
            if call:
                return call

        # Only stop for you when you have something to decide: every pitch of
        # your own half, but in the field only when a play is actually on.
        if self.interactive and (self.coaches_batting_team(top) or mine):
            return self.prompt(batting, outs, mine)
        return self.cpu_call(mine, batting, outs, inning) or "roll"

    def prompt(self, batting: Team, outs: int, plays: List[str]) -> str:
        """Wait for the manager.  May switch to auto or quit the game."""
        menu = ", ".join(["Enter to roll"]
                         + [PLAY_KEYS[p] for p in plays]
                         + (["(d)ice"] if self.last_play else [])
                         + ["(a)uto", "(q)uit"])
        line = "   %s  %s > " % (self.scorebug(batting, outs), menu)
        while True:
            try:
                answer = input(line).strip().lower()
            except EOFError:
                print()
                self.interactive = False
                return "roll"
            if answer == "":
                return "roll"
            if (answer.startswith("d") or answer == "?") and self.last_play:
                self.explain()
                continue
            if answer.startswith("a"):
                self.interactive = False
                return "roll"
            if answer.startswith("q"):
                self.say("\nCalled on account of dice.")
                sys.exit(0)
            for play in plays:
                if answer[0] == play[0]:
                    return play
            print("   Not an option here -- %s" % menu)

    # -- plays called before the pitch -------------------------------------
    def try_steal(self, batting: Team):
        """Runner on first goes.  One die: 3 or better and he has it."""
        runner = batting.bases[0]
        die = d6()
        roll = "[%d]" % die
        if die >= STEAL_SAFE_ON:
            batting.bases[1], batting.bases[0] = runner, None
            runner.sb += 1
            text = "steals second."
            label = "safe -- %d or better does it" % STEAL_SAFE_ON
        else:
            batting.bases[0] = None
            runner.cs += 1
            text = "is caught stealing."
            label = "caught -- needed a %d" % STEAL_SAFE_ON
        self.last_play = (roll, runner.name, text, batting.name, [label])
        return runner, roll, text, 1 if label.startswith("caught") else 0

    def sacrifice(self, batting: Team, outs: int):
        """Lay one down.  Same return shape as an at-bat.

        Two different plays share this die.  Moving a runner up only asks the
        batter to get the ball on the ground away from a fielder, and it works
        most of the time.  A squeeze asks a runner to beat a throw to the
        plate, which is a far harder thing, so it gets a narrower band and a
        second way to go wrong."""
        batter = batting.due_up()
        batting.next_batter()
        die = d6()
        roll = "[%d]" % die
        squeeze = batting.bases[2] is not None

        def remember(text, label):
            self.last_play = (roll, batter.name, text, batting.name, [label])
            return text

        if die <= (3 if squeeze else 4):          # the play as drawn up
            batter.sac += 1
            scored = batting.advance_all(1)
            if scored:
                return batter, roll, remember(
                    "lays down the squeeze; the run comes home.",
                    "the squeeze, as drawn up"), scored, 1
            return batter, roll, remember("sacrifices; the runners move up.",
                                          "the sacrifice, as drawn up"), scored, 1

        if die == (4 if squeeze else 5):          # too good to field
            batter.ab += 1
            batter.h += 1
            batting.hits += 1
            scored = batting.advance_all(1)
            batting.bases[0] = batter
            return batter, roll, remember("beats out a bunt single!",
                                          "too well placed to field"), scored, 0

        if squeeze and die == 5:                  # popped up, run stays put
            batter.ab += 1
            return batter, roll, remember(
                "pops the bunt up; the runner has to stay at third.",
                "bunted into the air -- the run holds"), [], 1

        # They get the most advanced runner they can reach, and the batter
        # takes first.  A runner is only ever *forced* when every base behind
        # him is occupied, so which play is even available depends on the
        # situation: with first base empty there is no force anywhere, and the
        # defense has to tag instead.
        batter.ab += 1
        if batting.bases[2] is not None:
            # The throw goes home, so the squeeze does not pay off.
            batting.bases[2] = None
            text = "bunts, but they throw home and cut the run down."
            label = "they get the runner at the plate -- no run"
        elif batting.bases[1] is not None:
            batting.bases[1] = None
            forced = batting.bases[0] is not None
            text = ("bunts, and they %s the lead runner at third."
                    % ("force" if forced else "cut down"))
            label = "they get the lead runner at third"
        else:
            batting.bases[0] = None
            text = "bunts, and the runner is forced at second."
            label = "the runner is forced at second"
        scored = batting.advance_all(1)
        batting.bases[0] = batter
        return batter, roll, remember(text, label), scored, 1

    def ground_ball(self, batter: Player, batting: Team, outs: int,
                    sub_roll, meant) -> tuple:
        """Resolve a ball on the ground.  Shared by GO and by an error check
        the fielder handles cleanly, so the two behave identically."""
        where = random.choice(INFIELD)
        scored: List[Player] = []

        if batting.bases[0] is not None and outs < 2:
            sub = sub_roll()
            loaded = all(batting.bases)
            if sub <= 2:
                # Two for the price of one.  The lead runner is forced at
                # second and the batter thrown out at first; everyone else
                # moves up, so a man on third trots home -- unless this is
                # the third out, which the caller wipes.
                meant("a double play -- 1 or 2")
                batting.bases[0] = None
                scored = batting.advance_all(1)
                return "grounds %s, into a double play." % where, scored, 2
            if sub <= 4:
                meant("a fielder's choice -- 3 or 4")
                if loaded:
                    if sub_roll() <= 3:
                        # Bases full: cut the run down at the plate instead.
                        meant("bases full, so they take it at the plate")
                        batting.bases[2] = None
                        scored = batting.advance_all(1)
                        batting.bases[0] = batter
                        return ("grounds %s; they cut the run down at the "
                                "plate." % where, scored, 1)
                    meant("bases full, but they take it at second")
                batting.bases[0] = None
                scored = batting.advance_all(1)
                batting.bases[0] = batter
                return ("grounds %s; the runner is forced at second." % where,
                        scored, 1)
            meant("no double play -- 5 or 6")
            scored = batting.advance_all(1)
            return "grounds out %s; the runners move up." % where, scored, 1

        if any(batting.bases):
            if sub_roll() <= 3:
                meant("the runners move up -- 3 or under")
                scored = batting.advance_all(1)
                return "grounds out %s; the runners move up." % where, scored, 1
            meant("the runners hold -- needed 3 or under")
        return "grounds out %s." % where, scored, 1

    # -- one at-bat --------------------------------------------------------
    def at_bat(self, batting: Team, outs: int,
               fielding: Optional[Team] = None):
        """Resolve one plate appearance.  Returns (runs, outs_made, text)."""
        batter = batting.due_up()
        batting.next_batter()

        a, b = d6(), d6()
        code = CHART[a - 1][b - 1]
        scored: List[Player] = []
        outs_made = 0

        subs: List[list] = []           # [value, what it settled]

        def sub_roll(label: str = "settles the play") -> int:
            """A die thrown to settle the play; remembered for the log."""
            value = d6()
            subs.append([value, label])
            return value

        def meant(label: str) -> None:
            """Say what the die just thrown actually decided."""
            subs[-1][1] = label

        if code == "K":
            batter.ab += 1
            batter.so += 1
            outs_made = 1
            text = "strikes out %s." % random.choice(K_FLAVOR)

        elif code == "BB":
            batter.bb += 1
            scored = batting.walk_in(batter)
            text = "draws a walk."

        elif code == "PO":
            batter.ab += 1
            outs_made = 1
            text = "pops it up %s." % random.choice(INFIELD)

        elif code == "LO":
            batter.ab += 1
            outs_made = 1
            text = "lines out %s." % random.choice(OUTFIELD)

        elif code == "FO":
            outs_made = 1
            where = random.choice(OUTFIELD)
            on_third, on_second = batting.bases[2], batting.bases[1]

            if outs < 2 and (on_third is not None or on_second is not None):
                # One die for how deep it was: 1-2 is off the track and moves
                # everybody, 3-4 is enough to bring a man in from third, 5-6
                # is caught too shallow for anyone to risk it.
                deep = sub_roll()
                tagged = deep <= 2 and on_second is not None

                if on_third is not None and deep <= 4:
                    batting.bases[2] = None
                    scored = [on_third]
                    if tagged:
                        batting.bases[2], batting.bases[1] = on_second, None
                        meant("deep -- the run scores and the runner takes third")
                    else:
                        meant("deep enough -- the run scores")
                    batter.sf += 1          # a sacrifice fly is not an at-bat
                    text = "lifts a sacrifice fly %s." % where
                elif on_third is None and tagged:
                    batting.bases[2], batting.bases[1] = on_second, None
                    batter.ab += 1
                    meant("deep enough -- the runner tags up and takes third")
                    text = "flies out %s; the runner tags up and takes third." % where
                else:
                    batter.ab += 1
                    meant("too shallow -- nobody moves")
                    text = "flies out %s." % where
            else:
                batter.ab += 1
                text = "flies out %s." % where

        elif code == "GO":
            batter.ab += 1
            text, scored, outs_made = self.ground_ball(
                batter, batting, outs, sub_roll, meant)

        elif code == "E":
            batter.ab += 1
            if sub_roll() <= ERROR_ON:
                meant("booted -- the batter reaches")
                if fielding is not None:
                    fielding.errors += 1
                scored = batting.walk_in(batter)
                text = ("grounds %s, and reaches on the error."
                        % random.choice(INFIELD))
            else:
                meant("fielded cleanly -- play it out")
                text, scored, outs_made = self.ground_ball(
                    batter, batting, outs, sub_roll, meant)

        elif code == "1B":
            batter.ab += 1
            batter.h += 1
            batting.hits += 1
            if any(batting.bases) and sub_roll() <= 2:
                meant("the runners take an extra base")
                scored = batting.advance_all(2)
                text = "singles %s, and the runners take an extra base!" % \
                    random.choice(OUTFIELD)
            else:
                if subs:
                    meant("station to station")
                scored = batting.advance_all(1)
                text = "singles %s." % random.choice(OUTFIELD)
            batting.bases[0] = batter

        else:  # XB -- one more die decides how far it went
            kind = XB_TABLE[sub_roll()]
            meant({"2B": "a double", "3B": "a triple",
                   "HR": "a home run"}[kind])
            batter.ab += 1
            batter.h += 1
            batting.hits += 1
            if kind == "2B":
                runner_on_first = batting.bases[0] is not None
                scored = batting.advance_all(2)
                if runner_on_first:
                    if sub_roll() <= 3:
                        # He was on first and is waved around third.
                        meant("the runner from first is waved home")
                        scored += batting.advance_all(1)
                    else:
                        meant("the runner from first holds at third")
                batting.bases[1] = batter
                text = "doubles into the gap %s." % random.choice(OUTFIELD)
            elif kind == "3B":
                scored = batting.advance_all(3)
                batting.bases[2] = batter
                text = "drives one %s -- triple!" % random.choice(OUTFIELD)
            else:
                scored = batting.advance_all(3) + [batter]
                batting.clear_bases()
                batter.hr += 1
                text = "HOME RUN %s!" % random.choice(OUTFIELD)

        roll = "[%d-%d%s]" % (
            a, b, "|" + ",".join(str(v) for v, _ in subs) if subs else "")
        self.last_play = (roll, batter.name, text, batting.name,
                          ["picks the chart row",
                           "picks the column -- %s, %s"
                           % (code, LEGEND[code].split(" --")[0])]
                          + [label for _, label in subs])

        # A double play can end the inning before the trail runner scores; the
        # caller trims that, so credit runs there rather than here.
        return batter, roll, text, scored, outs_made

    # -- half inning -------------------------------------------------------
    def half_inning(self, inning: int, top: bool) -> None:
        batting = self.away if top else self.home
        self.watching = False           # the banner never crawls
        self.last_play = None           # nothing from this half to explain yet
        self.half_k = 0
        self.on_row = 0
        label = "Top" if top else "Bottom"
        suffix = "th" if 11 <= inning % 100 <= 13 else \
            {1: "st", 2: "nd", 3: "rd"}.get(inning % 10, "th")

        self.say()
        self.say("-" * self.log_width)
        self.say(" %s %d%s  |  %s %d, %s %d" % (
            label, inning, suffix, self.away.name, self.away.runs,
            self.home.name, self.home.runs))
        self.say("-" * self.log_width)

        self.watching = not self.coaches_batting_team(top)
        if inning == self.regulation + 1 and top:
            self.note("Free baseball.")
        batting.clear_bases()
        outs = 0
        runs_this_inning = 0
        batters_faced = 0
        reached = False

        while outs < 3:
            if self.watching and self.interactive:
                # You are not being asked anything here, but you should still
                # see what the situation is before the play resolves.
                self.say("   %s" % self.scorebug(batting, outs))
            call = self.coach_call(batting, outs, inning, top)

            if call == "steal":
                runner, roll, text, outs_made = self.try_steal(batting)
                outs += outs_made
                self.say("  %-10s %-12s %s" % (roll, runner.name, text))
                continue

            if call == "bunt":
                play = self.sacrifice(batting, outs)
            else:
                play = self.at_bat(batting, outs,
                                   self.home if top else self.away)

            batter, roll, text, scored, outs_made = play
            batters_faced += 1
            reached = reached or bool(scored) or any(batting.bases)

            # Runs only count if the third out wasn't made on the play.
            if outs + outs_made >= 3:
                outs = 3
                if outs_made >= 1:
                    scored = []
            else:
                outs += outs_made

            for runner in scored:
                runner.r += 1
                batter.rbi += 1
                batting.runs += 1
                runs_this_inning += 1

            line = "  %-10s %-12s %s" % (roll, batter.name, text)
            if scored:
                line += "  (%d run%s)" % (len(scored), "" if len(scored) == 1 else "s")
            self.say(line)
            self.call_the_game(batting, self.home if top else self.away,
                               batter, text, scored, outs, inning, batters_faced)

            # Walk-off: home team takes the lead in the last of the ninth.
            if (not top and inning >= self.regulation
                    and self.home.runs > self.away.runs):
                batting.line.append(runs_this_inning)
                self.say("  *** Ballgame. %s win it at home. ***" % self.home.name)
                return

        batting.line.append(runs_this_inning)
        self.call_the_half(batting, self.home if top else self.away,
                           inning, runs_this_inning, top)
        if runs_this_inning == 0:
            self.say("  Three up, three down."
                     if batters_faced == 3 and not reached else "  No runs.")
        else:
            self.say("  %d run%s in." % (runs_this_inning,
                                         "" if runs_this_inning == 1 else "s"))

    # -- full game ---------------------------------------------------------
    def play(self) -> None:
        self.say("=" * self.log_width)
        self.say(" BASEBALL DICE -- %s at %s" % (self.away.name, self.home.name))
        self.say("=" * self.log_width)

        inning = 1
        while True:
            self.half_inning(inning, top=True)

            home_wins_without_batting = (
                inning >= self.regulation and self.home.runs > self.away.runs)
            if home_wins_without_batting:
                self.home.line.append("X")
                break

            self.half_inning(inning, top=False)

            if inning >= self.regulation and self.home.runs != self.away.runs:
                break
            inning += 1
            if inning > 30:  # nobody wants a 31-inning dice game
                break

        self.final(inning)

    # -- box score ---------------------------------------------------------
    def final(self, innings_played: int) -> None:
        self.watching = False
        self.say()
        self.say("=" * self.log_width)
        width = max(len(self.away.name), len(self.home.name))

        header = " " * (width + 2) + "".join("%3d" % i for i in range(1, innings_played + 1))
        self.say(header + "   R  H  E")
        for team in (self.away, self.home):
            cells = "".join("%3s" % c for c in team.line)
            pad = "   " * (innings_played - len(team.line))
            self.say("  %-*s%s%s %3d %2d %2d" % (
                width, team.name, cells, pad,
                team.runs, team.hits, team.errors))
        self.say("=" * self.log_width)

        winner, loser = ((self.home, self.away) if self.home.runs > self.away.runs
                         else (self.away, self.home))
        self.say(" %s win, %d-%d." % (winner.name, winner.runs, loser.runs)
                 if winner.runs != loser.runs else " Tied after 30. Call it.")
        for team in (self.away, self.home):
            sb = sum(p.sb for p in team.lineup)
            cs = sum(p.cs for p in team.lineup)
            sac = sum(p.sac for p in team.lineup)
            sf = sum(p.sf for p in team.lineup)
            bits = []
            if sb or cs:
                bits.append("%d for %d stealing" % (sb, sb + cs))
            if sac:
                bits.append("%d sacrifice bunt%s" % (sac, "" if sac == 1 else "s"))
            if sf:
                bits.append("%d sacrifice fl%s" % (sf, "y" if sf == 1 else "ies"))
            if bits:
                self.say(" %s: %s." % (team.name, ", ".join(bits)))
        self.say()

        for team in (self.away, self.home):
            self.say(" %s" % team.name)
            self.say("  %-14s %3s %3s %3s %3s %3s %3s %6s" %
                     ("", "AB", "R", "H", "RBI", "BB", "SO", "AVG"))
            for p in team.lineup:
                self.say("  %-14s %3d %3d %3d %3d %3d %3d  %s" %
                         (p.name, p.ab, p.r, p.h, p.rbi, p.bb, p.so, p.avg))
            self.say()


# --------------------------------------------------------------------------
# Extras
# --------------------------------------------------------------------------
def print_chart() -> None:
    print()
    print("  THE CHART -- first die picks the row, second die the column")
    print()
    print("        " + "".join("%6d" % c for c in range(1, 7)))
    print("      +" + "-" * 36)
    for i, row in enumerate(CHART, start=1):
        print("   %d  |" % i + "".join("%6s" % cell for cell in row))
    print()
    counts = {}
    for row in CHART:
        for cell in row:
            counts[cell] = counts.get(cell, 0) + 1
    for code, desc in LEGEND.items():
        n = counts[code]
        print("   %-3s %-32s %2d/36  %5.1f%%" % (code, desc, n, 100 * n / 36))
    print()
    print("   XB sub-roll:  1-3 double, 4 triple, 5-6 home run")
    print("   E  sub-roll:  1-3 reaches on an error, 4-6 play it out as a grounder")
    print()


def simulate(n: int) -> None:
    tally = {}
    for _ in range(n):
        code = CHART[d6() - 1][d6() - 1]
        if code == "XB":
            code = XB_TABLE[d6()]
        elif code == "E":
            code = "ROE" if d6() <= ERROR_ON else "GO"
        tally[code] = tally.get(code, 0) + 1
    print()
    print("  %d plate appearances" % n)
    for code, count in sorted(tally.items(), key=lambda kv: -kv[1]):
        print("   %-3s %7d  %5.2f%%" % (code, count, 100 * count / n))
    on_base = sum(tally.get(c, 0) for c in ("BB", "1B", "2B", "3B", "HR", "ROE"))
    print("   %-3s %7d  %5.2f%%" % ("OBP", on_base, 100 * on_base / n))
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="A baseball game played with dice.")
    ap.add_argument("--away", default="Riverton Reds", help="visiting team name")
    ap.add_argument("--home", default="Bayside Bandits", help="home team name")
    ap.add_argument("--innings", type=int, default=9, help="regulation length")
    ap.add_argument("--auto", action="store_true", help="play it out without prompting")
    ap.add_argument("--delay", type=float, default=0.0,
                    help="seconds between every line (applies in auto mode too)")
    ap.add_argument("--watch-delay", type=float, default=1.5, metavar="SECONDS",
                    help="pacing for the half you only watch (default: 1.5)")
    ap.add_argument("--coach", default="home",
                    choices=["home", "away", "both", "none"],
                    help="which dugout you manage from (default: home)")
    ap.add_argument("--seed", type=int, help="seed the dice for a repeatable game")
    ap.add_argument("--chart", action="store_true", help="print the result chart and exit")
    ap.add_argument("--sim", type=int, metavar="N",
                    help="roll N at-bats and report the frequencies")
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
    if args.chart:
        print_chart()
        return
    if args.sim:
        simulate(args.sim)
        return

    game = Game(make_team(args.away, NAMES_AWAY),
                make_team(args.home, NAMES_HOME),
                innings=args.innings,
                interactive=not args.auto,
                delay=args.delay,
                coach=args.coach,
                watch_delay=args.watch_delay)
    game.play()


if __name__ == "__main__":
    main()
