#!/usr/bin/env bash
# Runs a game's Kinloom headless check: proof/check.sh <game dir> <scripted|nokey|live> [scene]
set -uo pipefail
GAME="$1"; MODE="$2"; SCENE="${3:-res://kinloom/tests/check.tscn}"
GODOT="${GODOT:-$LOCALAPPDATA/Microsoft/WinGet/Packages/GodotEngine.GodotEngine.Mono_Microsoft.Winget.Source_8wekyb3d8bbwe/Godot_v4.7.2-stable_mono_win64/Godot_v4.7.2-stable_mono_win64_console.exe}"
dotnet build "$GAME" -v q -nologo 2>&1 | grep -E " error |Erreur\(s\)" | grep -v " 0 Erreur" || true
export KINLOOM_CHECK_MODE="$MODE"
case "$MODE" in
  scripted) export KINLOOM_PROVIDER=scripted KINLOOM_SCRIPT="$(cd "$GAME" && pwd -W)/kinloom/tests/check-script.json" ;;
  nokey) unset DEEPSEEK_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY KINLOOM_PROVIDER ;;
esac
[ -f "$GAME/.godot/global_script_class_cache.cfg" ] || "$GODOT" --headless --import --path "$GAME" > /dev/null 2>&1
"$GODOT" --headless --quit-after 20000 --path "$GAME" "$SCENE" 2>&1 | grep -E "KINLOOM_CHECK|SCRIPT ERROR|\[kinloom\]" | grep -v "^\s*\[[0-9]\]"
