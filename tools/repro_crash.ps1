# Launch Blastem, spam gameplay keys, watch for the Fatal Error dialog.
# Usage: powershell -File tools/repro_crash.ps1 -Rom bin\xevious_md.bin -Seconds 90
param(
    [string]$Rom = "bin\xevious_md.bin",
    [int]$Seconds = 90,
    [string]$Emu = "C:\Games\Sega - Mega Drive\Blastem\blastem.exe"
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class ReproW {
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern IntPtr FindWindow(string cls, string name);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, UIntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint mapType);
}
"@

$romPath = (Resolve-Path $Rom).Path
$proc = Start-Process -FilePath $Emu -ArgumentList "`"$romPath`"" -PassThru
Start-Sleep -Seconds 3
$proc.Refresh()
$h = $proc.MainWindowHandle

# keys: s=zap(B), a=blaster(A), arrows=move, enter=start/coin
$seq = @(0x53, 0x41, 0x26, 0x53, 0x25, 0x41, 0x53, 0x28, 0x27, 0x41, 0x0D)
function Tap([uint32]$vk, [int]$hold) {
    $scan = [ReproW]::MapVirtualKey($vk, 0)
    $down = [IntPtr]((($scan -band 0xFF) -shl 16) -bor 1)
    $up = [IntPtr][int64](((($scan -band 0xFF) -shl 16) -bor 1) -bor 0xC0000000L)
    [ReproW]::PostMessage($h, 0x100, [UIntPtr]$vk, $down) | Out-Null
    Start-Sleep -Milliseconds $hold
    [ReproW]::PostMessage($h, 0x101, [UIntPtr]$vk, $up) | Out-Null
}

$crashed = $false
$elapsed = 3.0
$i = 0
$shotAt = $Seconds / 2
$shotDone = $false
while ($elapsed -lt $Seconds) {
    $vk = $seq[$i % $seq.Length]
    Tap $vk 90
    $i++
    Start-Sleep -Milliseconds 60
    $elapsed += 0.15
    if (-not $shotDone -and $elapsed -ge 12) {
        # mid-run screenshot to confirm gameplay is active
        & "$PSScriptRoot\shot_window.ps1" -Out "obj\md\repro_mid.png" | Out-Null
        $shotDone = $true
    }
    if (($i % 5) -eq 0) {
        $fw = [ReproW]::FindWindow($null, "Fatal Error")
        if ($fw -ne [IntPtr]::Zero) { $crashed = $true; break }
        if ($proc.HasExited) { break }
    }
}
if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
Get-Process blastem -ErrorAction SilentlyContinue | Stop-Process -Force
if ($crashed) { Write-Output "CRASH at ~${elapsed}s" } else { Write-Output "no crash in ${Seconds}s" }
