# Baseball Dice

Nine innings decided by dice. You manage the home team: every at-bat is a roll,
but when to send a runner or lay one down is yours to call.

```
python3 baseball_dice.py             # manage the home team, Enter to roll
python3 baseball_dice.py --auto      # play the whole game out
python3 baseball_dice.py --chart     # show the result chart
python3 baseball_dice.py --sim 10000 # outcome frequencies
```

At the prompt: **Enter** rolls, **d** breaks down the dice of the last play,
**a** plays the rest automatically, **q** quits.

## How an at-bat works

Roll two six-sided dice. The first die picks the row, the second the column:

```
         1     2     3     4     5     6
   1  |  K     K    GO    FO    BB    1B
   2  |  K    GO    GO    FO    BB    1B
   3  |  K    GO     E    FO    PO    1B
   4  |  K    GO    FO    PO    1B    XB
   5  |  K    GO    FO    LO    1B    XB
   6  |  K     K    GO    FO    BB    XB
```

`K` strikeout · `GO` ground ball · `FO` fly ball · `PO` pop up · `LO` line out
· `BB` walk · `1B` single · `XB` extra-base hit · `E` error check

All 36 cells are equally likely. Two of them call for one more die:

- **XB** — 1–3 double, 4 triple, 5–6 home run
- **E** — 1–3 the fielder boots it and the batter reaches, 4–6 it is fielded
  cleanly and plays out as an ordinary ground ball

A single cell is 2.8% of plate appearances, which is twice the real rate of
reaching on an error, so `E` splits: half the time it is an error, half the time
it was just a grounder. That puts errors at 1.4% of plate appearances and 0.55
per team per game, both about what real baseball produces.

A third die settles the close calls:

- a ground ball with a runner on first and under two outs — double play,
  fielder's choice, or the runners move up
- a fly ball with a runner on second or third and under two outs — how deep it
  carried, and so who can advance on it
- a single with runners aboard — do they take the extra base

Two plays go to a fourth die:

- a double with a runner on first — is he waved home
- a fielder's choice with the bases full — forced at the plate, or at second
  with the run scoring

So about three quarters of at-bats are two dice, most of the rest are three,
and roughly one in seventy needs a fourth.

## Reading the output

```
  [5-6|3,5] Whitaker     doubles into the gap to center.  (2 runs)
```

| Piece | Meaning |
| --- | --- |
| `[5-6` | the two dice for the at-bat — first is the row, second the column |
| `\|3,5]` | every extra die the play needed, in the order thrown |
| `Whitaker` | the batter |
| `doubles into the gap to center` | the result; the field location is flavor only |
| `(2 runs)` | runs scored on the play, omitted when none |

Most at-bats show no extra dice at all — a strikeout, walk, pop up or line out
is settled by the chart alone, and so is a single with the bases empty. One
extra die appears whenever the play needs settling, and a second when the bases
are loaded on a ground ball:

```
  [2-6]     Ortega       singles to left.
  [6-6|5]   Blackwell    HOME RUN to center!
  [2-4|4]   Nakamura     lifts a sacrifice fly to center.
  [5-2|1]   Ruiz         grounds to short, into a double play.
  [6-3|3,1] Fenwick      grounds to short; they cut the run down at the plate.
```

- `[2-6]` — a single with the bases empty, so no die was needed
- `|5` — the extra-base die: 5 is a home run
- `|4` — the sacrifice-fly die: 4 or under and the run scores
- `|1` — the ground-ball die: 1 or 2 is a double play
- `|3,1` — 3 made it a fielder's choice, then 1 sent the throw home

The dice are printed in full, so any play in the log can be replayed by hand
against the chart — or press **d** at the prompt and the game will do it for
you, dropping a line from each die to what it settled:

```
   ---- last play, Bayside Bandits ----
  [4-6|2,2]  Bergstrom    doubles into the gap to left-center.
   │ │ │ │
   │ │ │ └─ the runner from first is waved home
   │ │ └─ a double
   │ └─ picks the column -- XB, extra-base hit
   └─ picks the chart row
```

Every die records what it decided at the moment it is thrown, so those labels
are the real branches taken, not a reconstruction. The key only appears once
there is a play from the current half inning to break down.

Where the ball went and where a runner was retired are two different things,
and the wording keeps them apart. A fielder always follows the verb for the
batted ball — `grounds to short`, `pops it up to second`, `flies out to left`.
A base is only ever named after a semicolon or the word "at", and that is where
someone was put out — `the runner is forced at second`.

So `grounds to third; the runner is forced at second` is a ball hit to the
third baseman with the force play taken at second, and `grounds to second, and
reaches on the error` is a ball booted by the second baseman, with the batter
standing on first.

In interactive mode the prompt shows the situation before you roll:

```
   [1B:* 2B:o 3B:o | 1 out]  Enter to roll, (a)uto, (q)uit >
```

`*` is an occupied base, `o` an empty one — here, a runner on first with one
out.

## Coaching decisions

You manage the home team. Your half of the inning stops for Enter on every
single pitch, whether or not there is a play to call — the prompt just shows
fewer options when nothing is on:

```
   [1B:* 2B:o 3B:o | 0 outs]  Enter to roll, (s)teal, (b)unt, (a)uto, (q)uit >
```

The visitors' half plays itself out start to finish — their at-bats and the
bench manager's steals and bunts just scroll past, with nothing for you to
decide, since every play in the game currently belongs to the team at bat.

Each of their plays shows the same bases-and-outs bug your own prompt does,
then holds a beat before the result — the pause where your Enter would go:

```
   [1B:* 2B:o 3B:o | 1 out]
  [5-1]      Nakamura     strikes out swinging.
```

So the half reads like it is being played rather than landing in one block.
The inning banner goes up immediately and the beat falls before the first
outcome, so nothing arrives the instant the half begins.

`--watch-delay` sets the beat (default 1.5 seconds, `0` turns it off). It
applies only while you are still stepping through the game — press `a` for auto
and the rest runs at whatever `--delay` says, which is full speed unless you
set it.

There are two keys, but the bunt is really two plays depending on who is on
base:

| Play | Offered when | Works |
| --- | --- | --- |
| Steal | runner on first, second base open, any number of outs | 67% |
| Bunt — sacrifice | runner on first or second, nobody on third, under two outs | 83% |
| Bunt — squeeze | runner on third, under two outs | 67% |

Those percentages are not comparable as they stand: a successful steal costs
nothing, while a successful sacrifice still spends an out. What each one is worth
is further down.

**Steal** — a runner on first with second base open. One die, 3 or better and
he has it: 67% safe. A caught stealing is an out and the batter stays up.

That sits just under the real break-even of about 70%, so running is close to a
wash and slightly negative — worth doing when the situation calls for it rather
than for the value. The bench manager runs at one chance in six, which costs it
about 1.2 points of win rate against a manager who never runs at all.

**Bunt** — anybody on base, under two outs. One die, but it is really two
different plays. Moving a runner up only asks the batter to get the ball on the
ground away from a fielder. A squeeze asks a runner to beat a throw to the
plate, which is far harder, so it gets a narrower band and a second way to go
wrong.

With nobody on third — the sacrifice:

| Die | Result |
| --- | --- |
| 1–4 | the play as drawn up — batter out, runners move up |
| 5 | too well placed to field — bunt single, everyone advances |
| 6 | they get the lead runner; batter safe at first |

With a runner on third — the squeeze:

| Die | Result |
| --- | --- |
| 1–3 | the run comes home, batter out |
| 4 | bunt single, and the run scores |
| 5 | popped into the air — the runner has to stay at third |
| 6 | they throw home and cut the run down |

So a sacrifice moves the runner **83%** of the time and a squeeze brings the run
in **67%** — measured at 83.3% and 65.4% over 800 games.

On a 6 the defense gets the most advanced runner it can reach, and a runner is
only *forced* when every base behind him is occupied, so with first base empty
there is no force anywhere and the throw has to beat the runner:

| Runners | What a 6 costs you |
| --- | --- |
| first only | forced at second |
| second only | cut down at third — a tag play, no force exists |
| first and second | forced at third |
| any runner on third | the throw goes home and the run is cut down |

A sacrifice is not charged as an at-bat; every other outcome is.

Where bunting is right:

| Situation | Swing away | Bunt |
| --- | --- | --- |
| man on third, one out | 0.88 runs, 61% score | 0.90 runs, **73%** |
| first and third, one out | 1.14 runs, 63% score | 1.09 runs, **74%** |
| man on second, nobody out | 1.03 runs, 55% score | 0.96 runs, **60%** |
| man on third, nobody out | 1.28 runs, 80% score | 1.17 runs, 81% |
| man on second, one out | 0.61 runs, 35% score | 0.45 runs, 29% |

The pattern: bunting trades expected runs for the odds of getting one across,
which is the trade you want when a single run wins the game and a bad one when
you need a crooked number. The squeeze with a man on third and one out is the
sharpest version — it costs essentially nothing in expected runs and buys twelve
points of scoring chance. With one out and a man on second it is a straight
giveaway.

`--coach` decides which dugout you sit in:

| Value | You call |
| --- | --- |
| `home` (default) | the home team only — its steals and bunts, in the bottom half |
| `away` | the visitors instead |
| `both` | every play for both teams — the solitaire way |
| `none` | nothing; the bench manager handles it |

Whatever you do not call, a conservative bench manager does. It takes one
running chance in six, which works out to about 0.9 steal attempts per team per
game at a 67% success rate, and it only bunts from the seventh inning on.

## Sacrifice flies and tagging up

A fly ball with a runner on second or third and under two outs goes to one die
for how deep it carried:

| Die | Result |
| --- | --- |
| 1–2 | off the track — a runner on third scores *and* a runner on second takes third |
| 3–4 | deep enough to bring a man in from third; a runner on second holds |
| 5–6 | caught too shallow, nobody risks it |

A run scoring this way is a sacrifice fly: the batter is credited the run batted
in and is *not* charged an at-bat, the same treatment the sacrifice bunt gets.
Tagging up from second is not a sacrifice, so that one is charged normally.

Sacrifice flies come out at 0.22 per team per game against a real 0.25, and a
runner tags up from second about 0.16 times a game.

## Errors

A booted ball puts the batter on first and pushes only the runners who are
forced — nobody takes an extra base on it, and the batter is charged an at-bat
with no hit. The fielding team wears it in the `E` column of the line score:

```
                   1  2  3  4  5  6  7  8  9   R  H  E
  Riverton Reds    1  0  0  0  0  0  0  0  0   1  6  0
  Bayside Bandits  0  0  1  1  0  0  0  2  X   4  8  1
```

One simplification: a run forced home by an error is credited as a run batted
in here, where real scoring would call it unearned and credit nobody.

## The numbers it produces

Over 200,000 plate appearances: 22.1% strikeouts, 8.3% walks, 14.0% singles,
4.2% doubles, 1.4% triples, 2.8% home runs, 1.4% reached on an error, .318 on
base. About 4.2 runs per team per game, measured over 2,000 games — real
baseball is nearer 4.4.

Close throughout except for triples, which the chart is generous with at 1.4%
against a real 0.4% — they're more fun than they are frequent.

## The wrap

`--recap` hands the whole game log to Claude after the box score and prints the
radio call:

```
python3 baseball_dice.py --auto --recap
```

It is asked for what a good postgame wrap does: name the turning point and say
why it mattered, trace the shape of the game, give credit where the box score
says it is due — and never inflate a dull game. It reads the log and nothing
else, so it can notice things no canned rule would, like a hitter going
four-for-five without driving in a run.

Setup, once:

```
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.env.example config.env     # then put your key in it
```

`config.env` is gitignored. The key can also come from `ANTHROPIC_API_KEY` in
the environment.

The game itself stays dependency free — `recap.py` is only imported when you
pass the flag, so without it `baseball_dice.py` still runs anywhere with no
install and no key. Without a key or the SDK, `--recap` prints one line saying
why and leaves the game alone.

About 4 to 5 cents a game on Claude Opus 5, so roughly 20 recaps per dollar.

## Other flags

`--away NAME` · `--home NAME` · `--innings N` · `--coach home|away|both|none`
· `--watch-delay SECONDS` (pacing for the half you watch) · `--delay SECONDS`
(pacing for every line, auto mode included) · `--recap` · `--seed N` (replay
the exact same game)

Extra innings are played until someone wins; the home team doesn't bat in the
last of the ninth with a lead, and a walk-off ends the game on the spot.
