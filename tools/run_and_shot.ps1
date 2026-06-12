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
    [string]$KeySeq = "",      # only used with -Focus (SendKeys needs focus)
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
    public struct RECT { public int Left, Top, Right, Bottom; }
}
"@

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

if ($Focus) {
    [Win32]::SetForegroundWindow($hwnd) | Out-Null
    Start-Sleep -Milliseconds 300
    if ($KeySeq -ne "") {
        foreach ($step in $KeySeq.Split(",")) {
            $parts = $step.Split(":")
            $key = $parts[0]
            $wait = if ($parts.Length -gt 1) { [double]$parts[1] } else { 0.5 }
            $sk = switch ($key) {
                "ret"   { "{ENTER}" }
                "space" { " " }
                default { $key }
            }
            [System.Windows.Forms.SendKeys]::SendWait($sk)
            Start-Sleep -Seconds $wait
        }
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

$bmp = New-Object System.Drawing.Bitmap($w, $h)
$gfx = [System.Drawing.Graphics]::FromImage($bmp)
$hdc = $gfx.GetHdc()
# 2 = PW_RENDERFULLCONTENT (captures GPU-composited content on Win8.1+)
[Win32]::PrintWindow($hwnd, $hdc, 2) | Out-Null
$gfx.ReleaseHdc($hdc)
$outDir = Split-Path $Out -Parent
if ($outDir -and -not (Test-Path $outDir)) { New-Item -ItemType Directory -Force $outDir | Out-Null }
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
$gfx.Dispose(); $bmp.Dispose()

if (-not $Keep) { Stop-Process -Id $proc.Id -Force }
Write-Output "SHOT ${w}x${h} -> $Out"
