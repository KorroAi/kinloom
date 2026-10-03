#!/usr/bin/env bash
# Installs the Kinloom addon into a copy of the test project with `kinloom init` (like a user would),
# builds it and runs it headless. Prints KINLOOM_TEST PASS/FAIL and exits accordingly.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GODOT="${GODOT:-$LOCALAPPDATA/Microsoft/WinGet/Packages/GodotEngine.GodotEngine.Mono_Microsoft.Winget.Source_8wekyb3d8bbwe/Godot_v4.7.2-stable_mono_win64/Godot_v4.7.2-stable_mono_win64_console.exe}"
WORK="$(mktemp -d)/kinloom-godot-test"
cp -r "$ROOT/adapters/godot/test-project" "$WORK"
dotnet build "$ROOT/src/Kinloom.Cli" -v q -nologo > /dev/null
dotnet "$ROOT/src/Kinloom.Cli/bin/Debug/net10.0/kinloom.dll" init "$WORK" > "$WORK/init.log"
dotnet build "$WORK" -v q -nologo
"$GODOT" --headless --quit-after 1200 --path "$WORK" 2>&1 | tee "$WORK/run.log" | grep -E "KINLOOM_TEST|ERROR|error" || true
grep -q "KINLOOM_TEST PASS" "$WORK/run.log"
