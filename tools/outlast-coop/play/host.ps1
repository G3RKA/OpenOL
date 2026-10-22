<#
.SYNOPSIS
  Run the OpenOL relay for a friend to connect to, and print what the host still has to do by hand.
.EXAMPLE
  .\host.ps1 -Relay "D:\OpenOL-Relay\OpenOL_Relay.exe"
  .\host.ps1 -Relay "D:\OpenOL-Relay\OpenOL_Relay.exe" -Port 7777 -TriggerRadius 3000
.NOTES
  Starts only the relay you name, in this window (Ctrl+C stops it). It never changes the firewall or the router: if Windows
  shows a Firewall prompt, you choose "Allow" yourself. Makes no network calls besides the relay's own UDP port.
  The standalone relay creates the room PUBLIC. -TriggerRadius needs the patched relay in tools/outlast-coop/relay-patches.
#>
param(
    [Parameter(Mandatory)][string]$Relay,
    [int]$Port = 7777,
    [int]$TriggerRadius = 0
)
$ErrorActionPreference = "Stop"
if (-not (Test-Path $Relay)) { throw "Relay not found: $Relay" }
Write-Host "Addresses of this PC (give the friend the one on the network you share, e.g. the Radmin/ZeroTier/VPN one):"
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -ne "127.0.0.1" } |
    ForEach-Object { Write-Host ("  {0}  ({1})" -f $_.IPAddress, $_.InterfaceAlias) }
Write-Host ""
Write-Host "Over the internet: forward UDP $Port on your router to this PC, or use a VPN-style LAN, then give the friend your public address."
Write-Host "Room code: PUBLIC. You also join as a player: run join.ps1 with -HostIp 127.0.0.1."
Write-Host "Windows Firewall: if a prompt appears, allow the relay on private networks yourself."
Write-Host ""
$argsList = @("--port", "$Port")
if ($TriggerRadius -gt 0) { $argsList += @("--trigger-radius", "$TriggerRadius") }
Set-Location (Split-Path -Parent (Resolve-Path $Relay))   # the relay keeps relay.db next to itself
& $Relay @argsList
