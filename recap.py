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
Your voice is a veteran play-by-play announcer: precise, unhurried, dry, and
genuinely invested in the ball game. You respect the listener's intelligence.
You never hype what the line score does not support, and you reach for a
specific detail rather than a cliche.

The game was decided by dice, but you never mention dice, rolls, charts or odds.
To you it was a ball game and nothing else.

What a good wrap does, in order of importance:

1. Names the turning point -- the moment the game actually swung -- and says why
   it mattered. This is often not the loudest play. A leadoff walk that became a
   three-run inning is a better answer than the home run that followed it.
2. Traces the shape of the game in a sentence or two: who led, who answered,
   when it got away or stayed close.
3. Gives credit by name where the box score says it is due, and says plainly
   when a game was decided by somebody's mistake rather than somebody's swing.

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
- 150 to 220 words, two or three paragraphs. No headings, no lists."""


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


def write_recap(transcript: List[str], away: str, home: str) -> str:
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
    ask = ("Here is the complete log of today's game, %s at %s, play by play and"
           " then the box score. Write the wrap.\n\n%s" % (away, home, log))

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
