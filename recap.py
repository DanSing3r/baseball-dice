#!/usr/bin/env python3
"""
Postgame wrap for Baseball Dice.

Hands the whole game log to Claude and asks for the radio call -- what the game
turned on, and why.  Kept in its own module so baseball_dice.py stays dependency
free: nothing here is imported unless you pass --recap.

Needs ANTHROPIC_API_KEY, either in the environment or in config.env beside this
file, and the anthropic SDK (see requirements.txt).
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

MODEL = "claude-opus-5"
CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.env")

VOICE = """\
You are the radio voice wrapping up a baseball game, speaking to the person who
just managed the home club. Precise, dry, unhurried, genuinely invested. You
never inflate what the box score will not support.

The game was decided by dice, but you never mention dice, rolls, charts or odds.
To you it was a ball game and nothing else.

EXACTLY THREE SENTENCES, AND NO MORE THAN 75 WORDS IN TOTAL. This is the hardest
part of the job and the whole point of it. Three long sentences stuffed with
subordinate clauses is a failure, not a solution -- if a clause is the only way
to keep a fact, cut the clause and lose the fact. You have room for the heart of
the game and nothing else.

Write about the home club. Whether they won or lost is the frame: what they did
well, what they failed to do, what the afternoon turned on for them. The
visitors exist only as the thing the home side had to answer.

Give the three sentences roughly this work:

1. The result and the single biggest thing that produced it. Telegraph the heart
   of the game -- one inning, one swing, one collapse -- not a sequence of
   events. "Bayside wins it behind a delirious sixth in which they sent nine men
   to the plate" is the register.
2. What the home club did well or badly across the whole afternoon, the sort of
   thing only the totals reveal: eleven hits and three runs, four leadoff men
   aboard and nothing to show, nothing hit in the air all day, six stranded.
3. Where possible, the manager's own decisions. The facts name every called play
   -- steals, sacrifices, squeezes -- and say whether YOU called it or the bench
   did. A squeeze that scored the tying run, a runner caught stealing to end a
   threat: say whether the call worked. If no called play mattered, use this
   sentence for the sharpest remaining observation instead.

Name at most two players, and only if a sentence genuinely needs one. Prefer the
club, the inning, the moment.

Hard rules:

- Every player, inning, play and number you mention must appear in the log or
  the totals you are given. Invent nothing -- no diving catches, no crowd, no
  weather, no history, no quotes.
- This game tracks no pitchers, no pitch counts and no balls and strikes. Never
  give a count, a number of pitches, or a pitcher's name or performance.
- Use the totals you are handed rather than counting anything off the log
  yourself, and never contradict them.
- If the game was dull, say so plainly. A dull game written up honestly beats a
  dull game inflated.
- Do not sign off, name yourself, or address the listener as "you".
- Three sentences, 75 words maximum. No headings, no lists, no
  paragraph breaks."""


def load_key() -> Optional[str]:
    """Environment first, then config.env beside this file."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        with open(CONFIG) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("ANTHROPIC_API_KEY=") and not line.startswith("#"):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        return value
    except OSError:
        pass
    return None


def facts(game) -> str:
    """Everything the wrap would otherwise have to count off the log itself.

    Counting across two hundred lines is where a recap goes wrong -- totals,
    runners stranded, how many leadoff men came to nothing.  So we do the
    arithmetic here and hand over the answers."""
    lines = []
    for team in (game.away, game.home):
        halves = [h for h in game.halves if h["team"] == team.name]
        lead_on = [h for h in halves if h["leadoff_on"]]
        lead_scored = [h for h in lead_on if h["runs"]]
        multi = [h for h in halves if h["hits"] > 1]
        big = max(halves, key=lambda h: h["runs"]) if halves else None
        bb = sum(p.bb for p in team.lineup)
        so = sum(p.so for p in team.lineup)
        lob = sum(h["left_on"] for h in halves)
        lines.append("%s: %d runs, %d hits, %d error%s, %d walk%s, %d strikeouts."
                     % (team.name, team.runs, team.hits,
                        team.errors, "" if team.errors == 1 else "s",
                        bb, "" if bb == 1 else "s", so))
        lines.append("  runners left on base: %d" % lob)
        lines.append("  half-innings with more than one hit: %d of %d"
                     % (len(multi), len(halves)))
        lines.append("  leadoff man reached in %d half-innings; %d of those scored"
                     % (len(lead_on), len(lead_scored)))
        if big and big["runs"]:
            lines.append("  biggest inning: %d runs in the %s of the %d%s"
                         % (big["runs"], "top" if big["top"] else "bottom",
                            big["inning"], ordinal(big["inning"])))
        hitters = sorted((p for p in team.lineup if p.h >= 2),
                         key=lambda p: -p.h)
        if hitters:
            lines.append("  multi-hit games: " + ", ".join(
                "%s %d-for-%d" % (p.name, p.h, p.ab) for p in hitters))
        # A perfect day only reads as one with three or more trips.
        reached_all = [p for p in team.lineup
                       if p.ab + p.bb >= 3 and p.h == p.ab]
        if reached_all:
            lines.append("  reached every time up: " + ", ".join(
                p.name for p in reached_all))
    if getattr(game, "calls", None):
        lines.append("")
        lines.append("Called plays (a manager's decision, not something that "
                     "merely happened):")
        for c in game.calls:
            lines.append("  %s %d%s, %d out%s, %s -- %s called a %s: %s"
                         % ("top of the" if c["top"] else "bottom of the",
                            c["inning"], ordinal(c["inning"]), c["outs"],
                            "" if c["outs"] == 1 else "s", c["bases"],
                            "YOU" if c["by_you"] else "the bench",
                            c["kind"], c["text"]))
    return "\n".join(lines)


def ordinal(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def write_recap(transcript: List[str], away: str, home: str,
                numbers: str = "") -> str:
    """Return the wrap, or a one-line explanation of why there isn't one."""
    key = load_key()
    if not key:
        return ("No recap: set ANTHROPIC_API_KEY, or put it in config.env "
                "(see config.env.example).")
    try:
        import anthropic
    except ImportError:
        # Almost always this: the game was run on the system python, while the
        # SDK lives in the project venv.  Say exactly what to run instead.
        here = os.path.dirname(os.path.abspath(__file__))
        venv = os.path.join(here, ".venv", "bin", "python")
        if os.path.exists(venv) and os.path.abspath(sys.executable) != venv:
            return ("No recap: this python has no anthropic package. Run the "
                    "game with the project's instead:\n"
                    "    .venv/bin/python baseball_dice.py --recap")
        return ("No recap: the anthropic package is not installed. Set it up "
                "with:\n"
                "    python3.12 -m venv .venv\n"
                "    .venv/bin/pip install -r requirements.txt")

    log = "\n".join(transcript)
    ask = ("Here is the complete log of today's game, %s at %s -- %s are the "
           "home club, the one being managed, and the one to write about. Play "
           "by play, then the box score.\n\n%s" % (away, home, home, log))
    if numbers:
        ask += ("\n\nThese totals have already been counted for you off that "
                "log. They are correct -- use them rather than counting "
                "anything yourself, and do not contradict them:\n\n%s"
                % numbers)
    ask += "\n\nWrite the wrap."

    try:
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model=MODEL,
            # Thinking tokens count against max_tokens, and on this model they
            # can run past a thousand on their own -- too small a cap returns a
            # perfectly valid response with no text in it at all.
            max_tokens=4000,
            system=[{"type": "text", "text": VOICE,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": ask}],
        )
    except Exception as exc:                      # network, auth, rate limit
        return "No recap: %s: %s" % (type(exc).__name__, exc)

    if response.stop_reason == "refusal":
        return "No recap: the request was declined."
    text = "".join(b.text for b in response.content
                   if b.type == "text").strip()
    if not text:
        return ("No recap: the model returned no text (stop_reason %s)."
                % response.stop_reason)
    return text


def wrap(text: str, width: int = 68, indent: str = " ") -> List[str]:
    """Fold the wrap to the log's width, keeping paragraph breaks."""
    import textwrap
    out: List[str] = []
    if text.startswith("No recap:"):        # keep the command on its own line
        return [indent + line for line in text.split("\n")]
    for para in [p for p in text.split("\n") if p.strip()]:
        out.extend(textwrap.wrap(para.strip(), width=width - len(indent),
                                 initial_indent=indent, subsequent_indent=indent))
        out.append("")
    return out[:-1] if out else out
