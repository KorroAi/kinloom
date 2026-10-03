# Devlog post draft (to be posted by the user)

Attach: `site/demo.gif` (or `site/demo.mp4` where video is preferred).
Check the target subreddit's rules first (see `outreach.md`). Replace the waitlist line only if the waitlist is live.

---

**Title:** How do you make NPCs remember what the player did? I tried rumors with a "why" chain for every reaction (no LLM)

I'm prototyping a small simulation layer where NPCs notice what the player does, react, remember, and pass it on. No dialogue model, just perception, memory, opinions and rumors that lose certainty each time they're retold. Every decision is logged with its cause, so you can click any NPC and ask "why?".

In the 7-day test village (seed 42, nothing scripted except the player's actions):

- The player steals bread in front of the baker. She walks to the guard and reports it; when the guard sees the player on the square an hour later, he recognizes him ("heard from Berta the Baker") and makes him give the bread back.
- That evening at the tavern, the story spreads. The next morning the smith charges 11.2 instead of 10. Here is his actual why-chain:

```
[D2 11:00] Hugo the Smith sells to The Stranger for 11.2 (base 10.0, opinion -0.25)
    <- [D1 18:55] Hugo the Smith's opinion of The Stranger: 0.00 -> -0.26
    <- [D1 18:55] Berta the Baker tells Hugo the Smith: The Stranger steal -> Berta the Baker
    <- [D1 10:00] Berta the Baker saw: The Stranger steal -> Berta the Baker (Loaf of Bread)
    <- [D1 10:00] The Stranger steal -> Berta the Baker (Loaf of Bread)
```

- On day 4 the player draws a weapon in the market: the farmer and the innkeeper run home, the guard walks over. On day 6 the player pays the baker back and her opinion goes from -0.44 to +0.04; she sells bread at the normal price again.

Try it in the browser — this link opens the guard's why-chain at the moment he confronts the thief: https://kinloom-lilac.vercel.app/demo.html#t=138&select=guard

It's a console + HTML replay for now; the goal is a Unity package where this sits on top of the AI you already have.

**Question for you:** how do you handle NPC memory and reactions in your own game today? What was the painful part?

(Waitlist: <link, only if live>)
