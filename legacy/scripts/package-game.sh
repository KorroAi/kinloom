#!/usr/bin/env bash
# Builds a self-contained Windows build of the village prototype (no .NET install needed) and zips it.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=dist/KinloomVillage
rm -rf "$OUT" dist/KinloomVillage-win64.zip
dotnet publish src/Kinloom.Game -c Release -r win-x64 --self-contained true \
  -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:DebugType=None -o "$OUT"
mkdir -p "$OUT/packs" "$OUT/scenarios"
cp packs/medieval.pack.json "$OUT/packs/"
cp scenarios/village-game.json "$OUT/scenarios/"
powershell -NoProfile -Command "Compress-Archive -Path '$OUT\*' -DestinationPath 'dist\KinloomVillage-win64.zip' -Force"
ls -la "$OUT" dist/KinloomVillage-win64.zip
