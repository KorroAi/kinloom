# Security

## Reporting a vulnerability

Please do not open a public issue. Report it privately through the repository's **Security** tab ("Report a
vulnerability"), with the version, the SDK or command involved, and the steps to reproduce.

## What Kinloom protects, by design

- **API keys** are read from environment variables only; Kinloom never writes them to files, logs, journals,
  recordings or MCP output. `kinloom ship` looks for keys left in a game's files.
- **A key inside a game players download can be read by them.** Ship with a relay (`kinloom serve` / `kinloom deploy`:
  player tokens, rate limits, spending caps) or let each player bring their own key.
- **The model proposes, validation decides:** every answer is checked against the shape the game gave (and the
  content filter) before it reaches the game; with no valid answer, the offline answer is used.
- **The local server** checks `Host` and `Origin` (DNS rebinding, `Origin: null` pages), compares tokens in constant
  time, bounds bodies, names, sessions and numbers, and signs saves loaded with a player token.
- **Secrets given to characters** are kept by code as well as by the prompt (`souls.leaks`): a reply that says one is
  asked again, then cut.

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x | yes |
| legacy C# runtime (`legacy/`) | as is |
