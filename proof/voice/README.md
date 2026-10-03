# Voice: characters that speak, players heard through a microphone

2026-09-30. No voice key was available: hosted
providers (OpenAI, ElevenLabs) are written from their API references (read 2026-09-30) and tested against local copies
of those APIs (`python/tests/test_voice.py`), **never called live**. What ran for real is below.

## The system voice, offline (`run.py`, Windows 11, French system)

| | Result |
|---|---|
| Installed | voices Hortense (fr-FR) and Zira (en-US); recognition only in the system's language (fr-FR here: the other listed recognizers cannot be opened from 64-bit Windows PowerShell) |
| Start (one PowerShell kept open) | 0.58 s, once |
| Speaking a line (to WAV) | 0.08 s median, 0.13 s max (13 lines, French and English) |
| Hearing a line back (French) | 0.55 s median; 88 % of the words found (in order), 5 of 10 lines exact |

The recognition score is an upper bound: the recording is a machine voice with no room noise. Sample: "Apporte-moi
trois bûches avant la tombée de la nuit." heard "Apportent mois trois bûches avant la tombée de la nuit". macOS `say`
and Linux espeak are written but not run here.

## In a real browser (Playwright, Chromium, scripted model and scripted server voice)

- Talk page (`kinloom` then the Talk tab): voice on, a message sent -> `/v1/chat` streamed, `/v1/speak` called, a WAV
  played (`data:audio/wav;base64,UklGR...`). Microphone (a synthetic tone as the microphone: the real one was not
  used): 1.5 s recorded by MediaRecorder (21.5 KB of WebM) -> `/v1/listen` -> the text sent to the character, who
  answered aloud.
- Web talk box (`talkBox(kl, "Orrin", {voice: true})` on a page of its own): same, hold-to-talk button, 23.5 KB WebM,
  two lines played. Console: no error but a missing favicon.

## Every client (conformance, scripted voice on the server)

`speak` then `listen` of what was spoken, and both with no server: Python, JavaScript, TypeScript, C#, Rust, Java,
C++, Godot (the WAV loads as an `AudioStreamWAV`; `AIDialogue.voice` on), LuaJIT and Lua 5.4: 10/10 PASS.

## Coding agents asked for voice (`proof/universal/run.py`, DeepSeek v4.1 flash, 4 requests x 3 answers)

| Kit | AGENTS.md only | + `kinloom recipe` | Cost |
|---|---|---|---|
| first voice kit | 83 % | 58 % | $0.015 |
| + the `if audio:` check shown in every example | 83 % | 67 % | $0.016 |

The first run found a real trap: `speak` gives `None` when no voice can speak and 3 answers used `audio.path` without
checking; after the examples showed the check, none did. What still fails is the model's own code (a stand-in it did
not define, a `pygame` import the test machine does not have). 12 answers per row: a small sample.

## Not measured

A real microphone and a human voice (the machine has one; it was not switched on without the user), the hosted voices
live (no key), Pygame's microphone capture on real hardware (the code path runs with the dummy driver), Godot's
microphone (`AudioEffectRecord`: needs Project Settings > Audio > Driver > Enable Input), latency of a hosted voice
per sentence while a reply streams.
