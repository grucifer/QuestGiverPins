<#
  Installs/updates Quest Giver Pins from the latest GitHub release.
  Run manually, or register a daily Windows scheduled task with:
    powershell -ExecutionPolicy Bypass -File Update-QuestGiverPins.ps1 -Register
#>
param(
    [string]$AddOnsPath = "",
    [string]$Repo = "grucifer/QuestGiverPins",
    [switch]$Register
)

$ErrorActionPreference = "Stop"

function Find-ForeverAddOns {
    $roots = @()
    # Battle.net records the WoW install folder in the registry
    foreach ($key in "HKLM:\SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft",
                     "HKLM:\SOFTWARE\Blizzard Entertainment\World of Warcraft") {
        $ip = (Get-ItemProperty $key -ErrorAction SilentlyContinue).InstallPath
        if ($ip) { $roots += (Split-Path ($ip.TrimEnd("\")) -Parent); $roots += $ip }
    }
    foreach ($drive in "D:", "C:", "E:") {
        $roots += "$drive\World of Warcraft", "$drive\Games\World of Warcraft",
                  "$drive\Program Files (x86)\World of Warcraft", "$drive\Program Files\World of Warcraft",
                  "$drive\Battle.net\World of Warcraft", "$drive\Blizzard\World of Warcraft"
    }
    foreach ($r in $roots) {
        $forever = Join-Path $r "_forever_"
        if (Test-Path $forever) {
            $addons = Join-Path $forever "Interface\AddOns"
            New-Item -ItemType Directory $addons -Force | Out-Null
            return $addons
        }
    }
    return $null
}

if (-not $AddOnsPath) {
    $AddOnsPath = Find-ForeverAddOns
    if (-not $AddOnsPath) { throw "Couldn't find WoW Forever (_forever_ folder). Re-run with -AddOnsPath ""<WoW folder>\_forever_\Interface\AddOns""" }
    Write-Host "Found WoW Forever AddOns folder: $AddOnsPath"
}

if ($Register) {
    $script = $MyInvocation.MyCommand.Path
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`" -AddOnsPath `"$AddOnsPath`""
    $trigger = New-ScheduledTaskTrigger -Daily -At 6:00am
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
    Register-ScheduledTask -TaskName "Update QuestGiverPins" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "Scheduled task 'Update QuestGiverPins' registered (daily 6:00am, runs late if the PC was off)."
}

if (-not (Test-Path $AddOnsPath)) { throw "AddOns folder not found: $AddOnsPath  (pass -AddOnsPath)" }

$headers = @{ "User-Agent" = "QuestGiverPins-updater" }
$release = Invoke-RestMethod -Headers $headers "https://api.github.com/repos/$Repo/releases/latest"
$asset = $release.assets | Where-Object { $_.name -like "QuestGiverPins-*.zip" } | Select-Object -First 1
if (-not $asset) { throw "No zip found in the latest release" }

$latest = $release.tag_name.TrimStart("v")
$toc = Join-Path $AddOnsPath "QuestGiverPins\QuestGiverPins.toc"
$installed = if (Test-Path $toc) { (Select-String -Path $toc -Pattern "^## Version: (.+)$").Matches.Groups[1].Value } else { "" }

if ($installed -eq $latest) { Write-Host "Quest Giver Pins is up to date ($installed)."; return }

$tmp = Join-Path $env:TEMP "QuestGiverPins-update"
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $tmp | Out-Null
$zip = Join-Path $tmp $asset.name
Invoke-WebRequest -Headers $headers $asset.browser_download_url -OutFile $zip
Expand-Archive $zip -DestinationPath $tmp

$dest = Join-Path $AddOnsPath "QuestGiverPins"
Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $tmp "QuestGiverPins") $dest -Recurse
Remove-Item $tmp -Recurse -Force
Write-Host "Quest Giver Pins updated: '$installed' -> $latest. /reload in game if you're logged in."
