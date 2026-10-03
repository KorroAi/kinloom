@echo off
rem Double-click to play Asagiri Valley (Godot 4.7 .NET + the .NET SDK; set DEEPSEEK_API_KEY or another provider key for the AI minds).
rem Language: French if Windows is in French (press L on the title screen to switch), or set KINLOOM_LANGUAGE=French / English.
cd /d "%~dp0demo\valley"
rem Running cost shown in the HUD. Prices per million tokens for deepseek-flash at PEAK hours (worst case; off-peak is half),
rem from https://api-docs.deepseek.com/quick_start/pricing as read on 2026-09-26. Set your own values to override.
if not defined KINLOOM_PRICE_INPUT set "KINLOOM_PRICE_INPUT=0.3"
if not defined KINLOOM_PRICE_CACHED set "KINLOOM_PRICE_CACHED=0.006"
if not defined KINLOOM_PRICE_OUTPUT set "KINLOOM_PRICE_OUTPUT=1.2"
set "GODOT=%LOCALAPPDATA%\Microsoft\WinGet\Packages\GodotEngine.GodotEngine.Mono_Microsoft.Winget.Source_8wekyb3d8bbwe\Godot_v4.7.2-stable_mono_win64\Godot_v4.7.2-stable_mono_win64.exe"
if not exist "%GODOT%" (
  echo Godot 4.7 .NET not found. Install it with: winget install GodotEngine.GodotEngine.Mono
  pause
  exit /b 1
)
dotnet build Valley.csproj -c Debug -v q
"%GODOT%" --path .
