# Run a Ghidra headless script on the analyzed OLGame project (project and scripts are reached through a space-free junction).
# usage: gh.ps1 <root> <Script.java> [args...]   <root> holds ghidra\ghidra_<ver>_PUBLIC, gh_proj and the .java scripts; it must be a path
# without spaces (analyzeHeadless.bat breaks on spaces), e.g. a junction made with New-Item -ItemType Junction.   -> prints the script's own output lines only
param([Parameter(Mandatory)][string]$W, [Parameter(Mandatory)][string]$Script, [Parameter(ValueFromRemainingArguments)]$Rest)
Set-Location $W
if (-not $env:JAVA_HOME) { throw "set JAVA_HOME to a JDK 21" }
& "$W\ghidra\ghidra_12.1.4_PUBLIC\support\analyzeHeadless.bat" "$W\gh_proj" olgame -process OLGame_openol.exe -noanalysis -scriptPath "$W" -postScript $Script @Rest 2>&1 |
    ForEach-Object { $_.ToString() } | Where-Object { $_ -notmatch "^(INFO  (HEADLESS|Opening|REPORT: (Processing|Execute|Save))|WARN|INFO  Using|INFO  Loading|INFO  Last)" } |
    ForEach-Object { $_ -replace "^INFO  $([regex]::Escape($Script))> ", "" }
