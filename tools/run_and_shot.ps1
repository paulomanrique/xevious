# Launch an emulator with a ROM, screenshot its window after a delay, then kill it.
# Captures via PrintWindow (PW_RENDERFULLCONTENT) so the window does NOT need focus
# and the user is not disturbed.
# Usage: powershell -File tools/run_and_shot.ps1 -Rom bin\xevious_md.bin -Out shot.png [-Delay 3]
#        [-Emu path] [-EmuArgs "-g"] [-KeySeq "ret:2.0,a:0.5"] [-Keep]
param(
    [string]$Rom = "bin\xevious_md.bin",
    [string]$Out = "obj\md\shot.png",
    [double]$Delay = 3.0,
    [string]$Emu = "C:\Games\Sega - Mega Drive\Blastem\blastem.exe",
    [string]$EmuArgs = "",
    [string]$KeySeq = "",
    [int]$Burst = 1,           # number of screenshots (suffix _0, _1, ...)
    [double]$BurstGap = 0.8,
    [switch]$Focus,
    [switch]$Keep
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, uint msg, UIntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint mapType);
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

$script:targetHwnd = [IntPtr]::Zero

function Press-Key([uint32]$vk, [int]$holdMs = 120) {
    $scan = [Win32]::MapVirtualKey($vk, 0)
    $down = [IntPtr]((($scan -band 0xFF) -shl 16) -bor 1)
    $up   = [IntPtr][int64](((($scan -band 0xFF) -shl 16) -bor 1) -bor 0xC0000000L)
    [Win32]::PostMessage($script:targetHwnd, 0x100, [UIntPtr]$vk, $down) | Out-Null
    Start-Sleep -Milliseconds $holdMs
    [Win32]::PostMessage($script:targetHwnd, 0x101, [UIntPtr]$vk, $up) | Out-Null
}

$vkMap = @{
    "ret" = 0x0D; "a" = 0x41; "s" = 0x53; "d" = 0x44
    "up" = 0x26; "down" = 0x28; "left" = 0x25; "right" = 0x27
}

$romPath = (Resolve-Path $Rom).Path
$argList = @()
if ($EmuArgs -ne "") { $argList += $EmuArgs.Split(" ") }
$argList += "`"$romPath`""
$proc = Start-Process -FilePath $Emu -ArgumentList $argList -PassThru
Start-Sleep -Seconds $Delay

if ($proc.HasExited) {
    Write-Output "EMULATOR EXITED EARLY (code $($proc.ExitCode))"
    exit 1
}

$proc.Refresh()
$hwnd = $proc.MainWindowHandle
if ($hwnd -eq [IntPtr]::Zero) {
    Write-Output "NO WINDOW FOUND"
    if (-not $Keep) { Stop-Process -Id $proc.Id -Force }
    exit 1
}

$script:targetHwnd = $hwnd
if ($KeySeq -ne "") {
    foreach ($step in $KeySeq.Split(",")) {
        $parts = $step.Split(":")
        $key = $parts[0]
        $wait = if ($parts.Length -gt 1) { [double]$parts[1] } else { 0.5 }
        if ($vkMap.ContainsKey($key)) {
            Press-Key $vkMap[$key]
        }
        Start-Sleep -Seconds $wait
    }
}

$rect = New-Object Win32+RECT
[Win32]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
$w = $rect.Right - $rect.Left
$h = $rect.Bottom - $rect.Top
if ($w -le 0 -or $h -le 0) {
    Write-Output "BAD WINDOW SIZE ${w}x${h}"
    if (-not $Keep) { Stop-Process -Id $proc.Id -Force }
    exit 1
}

$outDir = Split-Path $Out -Parent
if ($outDir -and -not (Test-Path $outDir)) { New-Item -ItemType Directory -Force $outDir | Out-Null }
for ($i = 0; $i -lt $Burst; $i++) {
    $bmp = New-Object System.Drawing.Bitmap($w, $h)
    $gfx = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $gfx.GetHdc()
    # 2 = PW_RENDERFULLCONTENT (captures GPU-composited content on Win8.1+)
    [Win32]::PrintWindow($hwnd, $hdc, 2) | Out-Null
    $gfx.ReleaseHdc($hdc)
    $file = $Out
    if ($Burst -gt 1) {
        $file = $Out -replace "\.png$", ("_{0}.png" -f $i)
    }
    $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
    $gfx.Dispose(); $bmp.Dispose()
    if ($i -lt $Burst - 1) { Start-Sleep -Seconds $BurstGap }
}

if (-not $Keep) { Stop-Process -Id $proc.Id -Force }
Write-Output "SHOT ${w}x${h} -> $Out (x$Burst)"
