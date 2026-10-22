<#
.SYNOPSIS
  Apply the "one owner per map enemy" native patch to a copy of OpenOL 2.1.0's OLGame.exe, without Python.
.EXAMPLE
  .\apply-native-patch.ps1 -Exe "D:\Games\Outlast-coop\Binaries\Win64\OLGame.exe" -Out OLGame_patched.exe
  # then, after checking it runs, replace the game copy's exe with the patched one (keep the original).
.NOTES
  PowerShell port of ..\exe-patch\apply_patch.py (the reference). Reads the input, never writes to it, and
  refuses any file whose SHA-256 is not the OpenOL 2.1.0 exe. Appends one PE section (.olfix) with the code from olfix.json
  and redirects two call sites to it. Touches no Steam file, no firewall and no network. Patch every player's copy, or the
  dedupe only happens on the side of whoever has it.
#>
param(
    [Parameter(Mandatory)][string]$Exe,
    [Parameter(Mandatory)][string]$Out,
    [string]$Blob = (Join-Path $PSScriptRoot "..\exe-patch\olfix.json")
)
$ErrorActionPreference = "Stop"

$EXPECT   = "2e58afbb1203d04476581f34216428d1dfc96228e5f3df8c6881323c56c93346"  # OLGame.exe of OpenOL 2.1.0, Outlast Steam build 576074
$RESULT   = "6ee34bd030353dcfc17b3b107b50685e36ccc0e20c57cdf361b0280c54fd89cd"  # the patched exe this script must produce
$SITE_AS  = 0x172B0B4   # E8 rel32: call ApplySpawn in OnBinaryPacket
$SITE_SS  = 0x1736CAB   # FF 90 68 02 00 00: vtable call SendSpawn in TickSend

if (-not (Test-Path $Exe)) { throw "input not found: $Exe" }
$inFull  = (Resolve-Path -LiteralPath $Exe).Path
$outFull = if ([System.IO.Path]::IsPathRooted($Out)) { [System.IO.Path]::GetFullPath($Out) } else { [System.IO.Path]::GetFullPath((Join-Path (Get-Location).Path $Out)) }
if ($inFull -ieq $outFull) { throw "output must be a different file than the input (never overwrite the exe you are reading)" }

$data = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $Exe))
$sha  = ([System.BitConverter]::ToString((New-Object Security.Cryptography.SHA256Managed).ComputeHash($data)) -replace '-').ToLower()
if ($sha -ne $EXPECT) { throw "refusing: input SHA-256 is $sha; this patch is for $EXPECT (OpenOL 2.1.0 on Steam build 576074). Install OpenOL 2.1.0 over a game copy first." }

$j    = Get-Content -Raw $Blob | ConvertFrom-Json
$code = for ($i = 0; $i -lt $j.hex.Length; $i += 2) { [Convert]::ToByte($j.hex.Substring($i, 2), 16) }
$code = [byte[]]$code

function U16($o) { [BitConverter]::ToUInt16($data, $o) }
function U32($o) { [BitConverter]::ToUInt32($data, $o) }
function Put16($arr, $o, $v) { [Array]::Copy([BitConverter]::GetBytes([uint16]$v), 0, $arr, $o, 2) }
function Put32($arr, $o, $v) { [Array]::Copy([BitConverter]::GetBytes([uint32]$v), 0, $arr, $o, 4) }
function Align($v, $a) { [long][math]::Floor(([long]$v + $a - 1) / $a) * $a }

$pe = U32 0x3C
if ([System.Text.Encoding]::ASCII.GetString($data, $pe, 2) -ne "PE") { throw "not a PE file" }
$opt    = $pe + 24
if ((U16 $opt) -ne 0x20B) { throw "not a 64-bit PE" }
$nsec   = U16 ($pe + 6)
$optsz  = U16 ($pe + 20)
$secal  = U32 ($opt + 32)
$fileal = U32 ($opt + 36)
$st     = $opt + $optsz

# section table -> RVA/offset map, and the last section
$secs = for ($i = 0; $i -lt $nsec; $i++) {
    $o = $st + $i * 40
    [pscustomobject]@{ vs = U32 ($o + 8); va = U32 ($o + 12); rs = U32 ($o + 16); rp = U32 ($o + 20) }
}
function RvaToOff($rva) {
    foreach ($s in $secs) {
        if ($rva -ge $s.va -and $rva -lt $s.va + [Math]::Max($s.vs, $s.rs)) {
            if ($rva - $s.va -ge $s.rs) { throw "RVA $rva is in the zero-filled tail of a section" }
            return $s.rp + ($rva - $s.va)
        }
    }
    throw "RVA $rva is in no section"
}

# --- append the .olfix section ---
$hdrEnd = $st + $nsec * 40
if ($hdrEnd + 40 -gt $secs[0].rp) { throw "no room for another section header" }
for ($k = 0; $k -lt 40; $k++) { if ($data[$hdrEnd + $k] -ne 0) { throw "section header slack is not empty" } }
$last = $secs | Sort-Object va | Select-Object -Last 1
$va   = Align ($last.va + [Math]::Max($last.vs, $last.rs)) $secal
$rp   = Align $data.Length $fileal
$rs   = Align $code.Length $fileal

$img = New-Object System.Collections.Generic.List[byte]
$img.AddRange($data)
while ($img.Count -lt $rp) { $img.Add(0) }
$img.AddRange($code)
while ($img.Count -lt $rp + $rs) { $img.Add(0) }
$buf = $img.ToArray()

$hdr = New-Object byte[] 40
[Array]::Copy([System.Text.Encoding]::ASCII.GetBytes(".olfix"), $hdr, 6)
Put32 $hdr 8  $code.Length
Put32 $hdr 12 $va
Put32 $hdr 16 $rs
Put32 $hdr 20 $rp
Put32 $hdr 36 ([uint32]0x60000020)   # CODE | EXECUTE | READ
[Array]::Copy($hdr, 0, $buf, $hdrEnd, 40)
Put16 $buf ($pe + 6)  ($nsec + 1)
Put32 $buf ($opt + 56) (Align ($va + $code.Length) $secal)   # SizeOfImage
Put32 $buf ($opt + 64) 0                                      # CheckSum (not used by the loader for an exe)

# --- redirect the two call sites (offsets are the same in $buf: everything was appended after them) ---
$asOff = RvaToOff $SITE_AS
if ($buf[$asOff] -ne 0xE8) { throw "unexpected bytes at the ApplySpawn call site" }
$rel = $va + [int]$j.entries.my_ApplySpawn - ($SITE_AS + 5)
[Array]::Copy([BitConverter]::GetBytes([int]$rel), 0, $buf, $asOff + 1, 4)

$ssOff = RvaToOff $SITE_SS
$want  = [byte[]](0xFF,0x90,0x68,0x02,0x00,0x00)
for ($k = 0; $k -lt 6; $k++) { if ($buf[$ssOff + $k] -ne $want[$k]) { throw "unexpected bytes at the SendSpawn call site" } }
$buf[$ssOff] = 0xE8
$rel = $va + [int]$j.entries.my_SendSpawn - ($SITE_SS + 5)
[Array]::Copy([BitConverter]::GetBytes([int]$rel), 0, $buf, $ssOff + 1, 4)
$buf[$ssOff + 5] = 0x90   # NOP the 6th byte of the old instruction

[System.IO.File]::WriteAllBytes($Out, $buf)
$osha = ([System.BitConverter]::ToString((New-Object Security.Cryptography.SHA256Managed).ComputeHash($buf)) -replace '-').ToLower()
Write-Host "patched copy written: $Out"
Write-Host "  new section .olfix at RVA 0x$('{0:x}' -f $va), $($code.Length) bytes"
Write-Host "  sha256 $osha"
if ($osha -ne $RESULT) { Write-Warning "sha256 differs from the reference patched exe ($RESULT); check the inputs." }
