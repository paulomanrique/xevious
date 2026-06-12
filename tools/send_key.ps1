# Send a held key press to the Blastem window via PostMessage.
# Usage: powershell -File tools/send_key.ps1 -Key ret [-HoldMs 150]
param(
    [string]$Key = "ret",
    [int]$HoldMs = 150,
    [string]$ProcName = "blastem"
)

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class SendKeyW32 {
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, UIntPtr w, IntPtr l);
    [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint mapType);
}
"@

$vkMap = @{
    "ret" = 0x0D; "a" = 0x41; "s" = 0x53; "d" = 0x44; "u" = 0x55
    "up" = 0x26; "down" = 0x28; "left" = 0x25; "right" = 0x27
}

$vk = [uint32]$vkMap[$Key]
$proc = Get-Process $ProcName -ErrorAction Stop | Select-Object -First 1
$h = $proc.MainWindowHandle
$scan = [SendKeyW32]::MapVirtualKey($vk, 0)
$down = [IntPtr]((($scan -band 0xFF) -shl 16) -bor 1)
$up = [IntPtr][int64](((($scan -band 0xFF) -shl 16) -bor 1) -bor 0xC0000000L)
[SendKeyW32]::PostMessage($h, 0x100, [UIntPtr]$vk, $down) | Out-Null
Start-Sleep -Milliseconds $HoldMs
[SendKeyW32]::PostMessage($h, 0x101, [UIntPtr]$vk, $up) | Out-Null
Write-Output "sent $Key"
