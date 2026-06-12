# Run Blastem with a ROM for N seconds; report if a "Fatal Error" dialog appears.
# Usage: powershell -File tools/watch_crash.ps1 -Rom bin\xevious_md.bin -Seconds 80
param(
    [string]$Rom = "bin\xevious_md.bin",
    [int]$Seconds = 80,
    [string]$Emu = "C:\Games\Sega - Mega Drive\Blastem\blastem.exe"
)

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class FindW {
    [DllImport("user32.dll", CharSet=CharSet.Unicode)]
    public static extern IntPtr FindWindow(string cls, string name);
}
"@

$romPath = (Resolve-Path $Rom).Path
$proc = Start-Process -FilePath $Emu -ArgumentList "`"$romPath`"" -PassThru
$crashed = $false
$elapsed = 0
while ($elapsed -lt $Seconds) {
    Start-Sleep -Milliseconds 500
    $elapsed += 0.5
    $h = [FindW]::FindWindow($null, "Fatal Error")
    if ($h -ne [IntPtr]::Zero) {
        $crashed = $true
        break
    }
    if ($proc.HasExited) { break }
}
if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force }
Get-Process blastem -ErrorAction SilentlyContinue | Stop-Process -Force
if ($crashed) {
    Write-Output "CRASH at ~${elapsed}s"
} else {
    Write-Output "no crash in ${Seconds}s"
}
