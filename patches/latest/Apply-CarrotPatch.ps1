param(
    [Parameter(Mandatory)]
    [string]$Serial,

    [string]$Adb = 'D:\Software\MuMuPlayer\nx_main\adb.exe',

    [switch]$Restore
)

$ErrorActionPreference = 'Stop'
$package = 'com.feiyu.luobo4'
$data = "/data/user/0/$package/files"
$cache = "$data/hotupdate/1.4.1"
$backup = "$data/.carrot-original-1.4.1"
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'manifest.json') -Raw | ConvertFrom-Json

function Invoke-Adb([string[]]$Command) {
    $result = & $Adb -s $Serial @Command
    if ($LASTEXITCODE -ne 0) {
        throw "ADB failed: $($Command -join ' ')"
    }
    $result
}

function Get-RemoteHash([string]$File) {
    $line = Invoke-Adb @('shell', "sha256sum '$File'")
    ($line -split '\s+')[0]
}

if ((Invoke-Adb @('shell', 'id -u')) -ne '0') {
    throw 'Enable Root on the selected MuMu instance, restart it, then run adb -s <serial> root.'
}

$installed = Invoke-Adb @('shell', "pm path $package")
if ($installed -notmatch '^package:(/data/app/[^\s\x27]+/base\.apk)$') {
    throw 'Install the original 1.4.1 APK on this instance first.'
}
if ((Get-RemoteHash $Matches[1]) -ne $manifest.apk) {
    throw 'The installed APK differs from the original 1.4.1 package.'
}

$work = @(
    foreach ($entry in $manifest.files) {
        if ($entry.path -notmatch '^[0-9a-f]{32}/src/[0-9]+/[0-9]+$') {
            throw 'Unexpected patch path.'
        }
        $remote = "$cache/$($entry.path)"
        $saved = "$backup/$($entry.path)"
        $current = Get-RemoteHash $remote
        $knownHashes = @($entry.original, $entry.patched) + @($entry.previous)
        if ($current -notin $knownHashes) {
            throw "Unrecognized update file: $($entry.path)"
        }

        if ($Restore) {
            if ($current -eq $entry.original) { continue }
            if ((Get-RemoteHash $saved) -ne $entry.original) {
                throw "Invalid backup: $($entry.path)"
            }
            $expected = $entry.original
            $local = $null
        } else {
            if ($current -eq $entry.patched) { continue }
            $local = Join-Path (Join-Path $PSScriptRoot 'payload') $entry.path
            if ((Get-FileHash -Algorithm SHA256 -LiteralPath $local).Hash -ne $entry.patched) {
                throw "Invalid patch file: $($entry.path)"
            }
            if ($current -in @($entry.previous) -and (Get-RemoteHash $saved) -ne $entry.original) {
                throw "Invalid original backup: $($entry.path)"
            }
            $expected = $entry.patched
        }

        [pscustomobject]@{
            Path = $remote
            Backup = $saved
            Local = $local
            Expected = $expected
            Current = $current
            SaveOriginal = $current -eq $entry.original
        }
    }
)

if ($work.Count -eq 0) {
    Write-Output 'Files are already in the requested state.'
    return
}

Invoke-Adb @('shell', "am force-stop $package") | Out-Null
$stage = "/data/local/tmp/carrot-$([guid]::NewGuid().ToString('N'))"
try {
    foreach ($item in $work) {
        $file = $item.Path
        $saved = $item.Backup
        if ((Get-RemoteHash $file) -ne $item.Current) {
            throw "Update file changed during preflight: $file"
        }
        if ($Restore) {
            $source = $saved
        } else {
            if ($item.SaveOriginal) {
                $parent = $saved.Substring(0, $saved.LastIndexOf('/'))
                Invoke-Adb @('shell', "set -e; mkdir -p '$parent'; chmod 700 '$backup'; cp -p '$file' '$saved.tmp'; mv -f '$saved.tmp' '$saved'") | Out-Null
            }
            Invoke-Adb @('push', $item.Local, $stage) | Out-Null
            $source = $stage
        }

        Invoke-Adb @('shell', "set -e; cp -p '$file' '$file.carrot.tmp'; cat '$source' > '$file.carrot.tmp'; restorecon '$file.carrot.tmp'; mv -f '$file.carrot.tmp' '$file'") | Out-Null
        if ((Get-RemoteHash $file) -ne $item.Expected) {
            throw "Verification failed: $file"
        }
    }
} finally {
    Invoke-Adb @('shell', "rm -f '$stage'") | Out-Null
}

if ($Restore) {
    Write-Output 'Original update files restored.'
} else {
    Write-Output 'Co-op now uses normal range and local 10x gold. Solo modes retain 10x gold and full-map range. Launch Carrot Fantasy 4 normally.'
}
