[CmdletBinding()]
param(
    [string]$TaskName = "Crypto Quant Daily Paper Portfolio",
    [string]$LocalRunTime = "08:15"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DailyScript = Join-Path $ProjectRoot "scripts\run_daily.ps1"

if (-not (Test-Path -LiteralPath $DailyScript)) {
    throw "Daily runner not found at $DailyScript"
}

$At = [datetime]::Today.Add([timespan]::Parse($LocalRunTime))
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$DailyScript`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $At
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Fetch closed Binance daily candles, refit signals, and update the paper portfolio." `
    -Force

Write-Host "Installed '$TaskName' for $LocalRunTime local time."
Write-Host "For Singapore time, 08:15 runs 15 minutes after the 00:00 UTC daily close."
