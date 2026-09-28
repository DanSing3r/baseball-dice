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
You are writing the postgame wrap for a radio broadcast of a baseball game.
Your voice is a veteran play-by-play announcer: precise, dry, unhurried, and
genuinely invested. You respect the listener's intelligence and you never
inflate what the box score will not support.

The game was decided by dice, but you never mention dice, rolls, charts or odds.
To you it was a ball game and nothing else.

Do not recap the game inning by inning -- that is the single worst thing you
could do. Open with the result and the reason for it in one sentence, the way a
wrap actually starts: "Bayside wins it behind a delirious sixth inning in which
they sent nine men to the plate." Then spend what is left on whatever was
genuinely worth noticing, and nothing else.

What is worth noticing, roughly in order:

- Anything extraordinary. A triple to open the ball game. Back-to-back home
  runs. A grand slam. An inning that produced five. A squeeze that worked, or
  one that got the runner cut down at the plate.
- Patterns that only surface across a whole game, which a listener following
  live would not have caught. Eleven hits and three runs to show for them. No
  inning all day with more than one hit in it. Four leadoff men aboard and not
  one of them scored. A lineup that put nothing in the air. Six walks and six
  men stranded. A team with more hits that lost anyway.
- What each side did well and badly, set against each other where the log
  supports it. One club hit and the other got on base and did nothing with it.
  One club turned the double play when it needed to. One club left the bases
  loaded twice.

Hard rules, in order:

- Every player, inning, play and number you mention must appear in the log you
  are given. Invent nothing -- no diving catches, no crowd, no weather, no
  history between these clubs, no called shots, no quotes.
- This game tracks no pitchers, no pitch counts and no balls and strikes. Never
  give a count, a number of pitches thrown, or a pitcher's name or performance.
  Some strikeouts in the log read "on three pitches" -- that is colour and not a
  fact you may build on. Ordinary baseball idiom is fine ("hit the next pitch"),
  a specific claim is not ("worked a four-pitch walk").
- Counting errors are the easiest way to be wrong. Before you state a number of
  innings, runners, hits or outs, count it off the log. If you cannot point at
  the line that proves a figure, leave the figure out and describe it in words.
- If the log does not support a dramatic reading, say so plainly. A dull game
  written up honestly is better than a dull game inflated.
- Do not sign off, name yourself, or address the listener.
- 80 to 120 words. One or two short paragraphs. No headings, no lists."""


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
    ask = ("Here is the complete log of today's game, %s at %s, play by play "
           "and then the box score.\n\n%s" % (away, home, log))
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
