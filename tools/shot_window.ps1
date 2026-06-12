# Screenshot the running Blastem window (PrintWindow, no focus needed).
# Usage: powershell -File tools/shot_window.ps1 -Out shot.png [-Burst 5] [-BurstGap 1.0]
param(
    [string]$Out = "obj\md\shot.png",
    [int]$Burst = 1,
    [double]$BurstGap = 1.0,
    [string]$ProcName = "blastem"
)

Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class ShotW32 {
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdc, uint flags);
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

$proc = Get-Process $ProcName -ErrorAction Stop | Select-Object -First 1
$hwnd = $proc.MainWindowHandle
$rect = New-Object ShotW32+RECT
[ShotW32]::GetWindowRect($hwnd, [ref]$rect) | Out-Null
$w = $rect.Right - $rect.Left
$h = $rect.Bottom - $rect.Top
$outDir = Split-Path $Out -Parent
if ($outDir -and -not (Test-Path $outDir)) { New-Item -ItemType Directory -Force $outDir | Out-Null }
for ($i = 0; $i -lt $Burst; $i++) {
    $bmp = New-Object System.Drawing.Bitmap($w, $h)
    $gfx = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $gfx.GetHdc()
    [ShotW32]::PrintWindow($hwnd, $hdc, 2) | Out-Null
    $gfx.ReleaseHdc($hdc)
    $file = $Out
    if ($Burst -gt 1) { $file = $Out -replace "\.png$", ("_{0}.png" -f $i) }
    $bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
    $gfx.Dispose(); $bmp.Dispose()
    if ($i -lt $Burst - 1) { Start-Sleep -Seconds $BurstGap }
}
Write-Output "SHOT ${w}x${h} x$Burst -> $Out"
