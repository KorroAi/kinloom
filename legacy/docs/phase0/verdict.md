# Phase 0 verdict

Date of measurements: 2026-09-26
Date of user review: _pending_

## Measurements (real runs, this machine, Release build)

- Tests: `dotnet test` → 94 passed, 0 failed (100% line coverage, 93.5% branch coverage); `python -m unittest discover -s docs/phase0b` → 4 passed.
- Bench 200 agents: `200 agents, 288 ticks: 61 ms total, 0.213 ms/tick, 739 journal entries`
- Bench 1000 agents: `1000 agents, 288 ticks: 380 ms total, 1.320 ms/tick, 3933 journal entries`
- Before the rumor spatial grid: 1000 agents took 1.710 ms/tick (−23% after). The +11 journal entries are the new "still walking" warnings of the bench player, not a behavior change (the seed-42 village story fingerprint is unchanged).

(One tick = 5 in-game minutes. These numbers are a baseline for the Phase 1 performance target, not a promise: the bench player repeats one bad deed every 2 hours, and rumor exchange is O(n²) per tick.)

## What the 7-day village run produced (seed 42)

Generate it again with:

```
dotnet run --project src/Kinloom.Sim -- scenarios/village.json packs/medieval.pack.json out/village
```

Then open `out/village/replay.html` (double-click, or serve the folder locally).

Highlights from `out/village/report.txt`:

- D1 10:00 The Stranger steals bread in front of Berta → she reports to Captain Aldric (10:15) → he recognizes the Stranger on the square (11:05, "heard from Berta") → confronts him and the bread is returned (11:10).
- D1 evening at the tavern, the theft spreads by rumor with falling confidence (Berta 1.00 → Hugo 0.80 → Old Tom 0.64; Mila hears it from the Captain at 0.72).
- D2 11:00 Hugo the Smith charges 11.2 instead of 10, because Berta told him about the theft the night before.
- D4 12:30 the Stranger draws a weapon on the square → Mila and Old Tom flee, the Captain confronts him.
- D5 11:00 Hugo still overcharges (10.9): Old Tom told him about the drawn weapon.
- D6 11:00 the Stranger pays Berta back → her opinion goes from −0.44 to +0.04 → she sells bread at the normal price.

## Questions for the user (answer in your own words)

1. Believable reactions — do NPCs react believably (flee, report, confront, scold) to what the player does?
   _pending_
2. Memory — do they remember (guard recognizes the thief; smith overcharges; baker softens after payment)?
   _pending_
3. Consequences spread — do rumors travel coherently, with lower confidence at each retelling?
   _pending_
4. Why-chain clarity — is the "Why?" chain in the Thought Inspector understandable?
   _pending_

## Decision

GO / PIVOT / STOP — _pending (user decision)_
