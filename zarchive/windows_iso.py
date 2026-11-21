"""Copy PS3_GAME from an ISO mounted read-only by Windows."""
from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess


# Pass paths through the environment so PowerShell never interprets them as code.
_COPY_GAME = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$iso = $env:ZARCHIVE_DISC_ISO
$destination = $env:ZARCHIVE_DISC_GAME
$mountedHere = $false

try {
    $image = Get-DiskImage -ImagePath $iso
    if (!$image.Attached) {
        $image = Mount-DiskImage -ImagePath $iso -Access ReadOnly -PassThru
        $mountedHere = $true
    }

    $game = $null
    for ($attempt = 0; $attempt -lt 12 -and !$game; $attempt++) {
        foreach ($volume in @($image | Get-Volume -ErrorAction SilentlyContinue)) {
            if (!$volume.DriveLetter) { continue }
            $candidate = '{0}:\PS3_GAME' -f $volume.DriveLetter
            if (Test-Path -LiteralPath $candidate -PathType Container) {
                $game = $candidate
                break
            }
        }
        if (!$game -and $attempt -lt 11) { Start-Sleep -Milliseconds 500 }
    }
    if (!$game) {
        throw 'Windows could not find PS3_GAME at the root of the ISO. Select a readable, decrypted PS3 disc ISO.'
    }

    $sfo = Join-Path $game 'PARAM.SFO'
    if (!(Test-Path -LiteralPath (Join-Path $game 'USRDIR') -PathType Container) -or
        !(Test-Path -LiteralPath $sfo -PathType Leaf)) {
        throw 'PS3_GAME must contain PARAM.SFO and USRDIR.'
    }
    $file = [IO.File]::OpenRead($sfo)
    try {
        $header = New-Object byte[] 4
        if ($file.Read($header, 0, 4) -ne 4 -or [BitConverter]::ToString($header) -ne '00-50-53-46') {
            throw 'PARAM.SFO is unreadable. Select a decrypted PS3 ISO with a valid PARAM.SFO.'
        }
    }
    finally {
        $file.Dispose()
    }

    & (Join-Path $env:SystemRoot 'System32\robocopy.exe') $game $destination /E /COPY:DT /DCOPY:DT /A-:R /XJ /R:1 /W:1 /NP /NFL /NDL
    if ($LASTEXITCODE -ge 8) {
        throw "Robocopy failed (exit $LASTEXITCODE). Check the output drive and available space."
    }
    # Robocopy's /A-:R handles files. ISO directory attributes can still
    # survive /DCOPY:DT and prevent the helper from removing PS3_GAME.
    & {
        Get-Item -LiteralPath $destination -Force
        Get-ChildItem -LiteralPath $destination -Recurse -Force
    } | ForEach-Object {
        $attributes = $_.Attributes
        if ($attributes -band [IO.FileAttributes]::ReadOnly) {
            $_.Attributes = $attributes -band (-bnot [IO.FileAttributes]::ReadOnly)
        }
    }
}
catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
finally {
    if ($mountedHere) {
        try {
            Dismount-DiskImage -ImagePath $iso | Out-Null
        }
        catch {
            [Console]::Error.WriteLine("Could not eject the ISO. You can eject it in File Explorer. " + $_.Exception.Message)
        }
    }
}
exit 0
"""


def copy_iso_game(source: Path, destination: Path, *, progress=None, extraction_progress=None):
    if progress is not None:
        progress('Mounting the ISO read-only and copying PS3_GAME. Large games may take several minutes.')
    if extraction_progress is not None:
        extraction_progress(0)

    system_root = Path(os.environ.get('SystemRoot', r'C:\Windows'))
    powershell = system_root / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    encoded = base64.b64encode(_COPY_GAME.encode('utf-16-le')).decode('ascii')
    env = dict(os.environ, ZARCHIVE_DISC_ISO=str(source), ZARCHIVE_DISC_GAME=str(destination))
    result = subprocess.run(
        [str(powershell), '-NoLogo', '-NoProfile', '-NonInteractive', '-OutputFormat', 'Text', '-EncodedCommand', encoded],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, encoding='utf-8',
        errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    if result.returncode:
        details = '\n'.join(part.strip() for part in (result.stderr, result.stdout) if part.strip())
        raise RuntimeError(f'Windows ISO extraction failed (exit {result.returncode}).\n{details}'.rstrip())
    if result.stderr.strip() and progress is not None:
        progress(result.stderr.strip())
    if extraction_progress is not None:
        extraction_progress(100)
