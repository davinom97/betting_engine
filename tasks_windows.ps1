#!/usr/bin/env pwsh
# tasks_windows.ps1
# Helper to create and remove Windows Scheduled Tasks equivalent to the project's crontab entries.

$root = "$(Get-Location)"
$repo = $root.Path
$gitbash = "C:\Program Files\Git\bin\bash.exe"

Write-Host "This script will create scheduled tasks that run the project's shell scripts via Git-Bash."
Write-Host "Edit the paths below if Git-Bash is installed elsewhere."

function Create-Tasks {
    Write-Host "Creating tasks..."
    schtasks /Create /SC MINUTE /MO 5 /TN "betting_engine_ingest" /TR "\"$gitbash\" -lc 'cd /c/$($repo -replace ':', '') && ./run_ingest.sh >> /c/$($repo -replace ':', '')/logs/ingest.log 2>&1'" /F
    schtasks /Create /SC DAILY /TN "betting_engine_decision_morning" /ST 10:00 /TR "\"$gitbash\" -lc 'cd /c/$($repo -replace ':', '') && ./run_decision.sh >> /c/$($repo -replace ':', '')/logs/decision.log 2>&1'" /F
    schtasks /Create /SC DAILY /TN "betting_engine_decision_evening" /ST 18:00 /TR "\"$gitbash\" -lc 'cd /c/$($repo -replace ':', '') && ./run_decision.sh >> /c/$($repo -replace ':', '')/logs/decision.log 2>&1'" /F
    schtasks /Create /SC DAILY /TN "betting_engine_feature_archiver" /ST 03:30 /TR "\"$gitbash\" -lc 'cd /c/$($repo -replace ':', '') && ./run_feature_archiver.sh >> /c/$($repo -replace ':', '')/logs/features.log 2>&1'" /F
    schtasks /Create /SC WEEKLY /D SUN /TN "betting_engine_backfill" /ST 04:00 /TR "\"$gitbash\" -lc 'cd /c/$($repo -replace ':', '') && ./run_backfill_utility.sh tierA >> /c/$($repo -replace ':', '')/logs/backfill.log 2>&1'" /F
    Write-Host "Tasks created. Verify with: schtasks /Query /TN betting_engine_*"
}

function Remove-Tasks {
    Write-Host "Removing tasks..."
    schtasks /Delete /TN "betting_engine_ingest" /F
    schtasks /Delete /TN "betting_engine_decision_morning" /F
    schtasks /Delete /TN "betting_engine_decision_evening" /F
    schtasks /Delete /TN "betting_engine_feature_archiver" /F
    schtasks /Delete /TN "betting_engine_backfill" /F
    Write-Host "Tasks removed."
}

param(
    [Switch]$Create,
    [Switch]$Remove
)

if ($Create) { Create-Tasks }
elseif ($Remove) { Remove-Tasks }
else { Write-Host "Usage: .\tasks_windows.ps1 -Create  or .\tasks_windows.ps1 -Remove" }
