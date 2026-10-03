@echo off
rem Double-click to play the Kinloom village prototype (needs the .NET 10 SDK).
cd /d "%~dp0"
dotnet run -c Release --project src\Kinloom.Game
