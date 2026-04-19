[CmdletBinding()]
param(
    [switch]$Force
)

$PSCmdlet.MyInvocation.BoundParameters.Keys | ForEach-Object { Write-Verbose "$($PSCmdlet.MyInvocation.MyCommand)-$($_): $($PSCmdlet.MyInvocation.BoundParameters[$_])" }

$ErrorActionPreference = 'Stop';
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version 1;

Push-Location $PSScriptRoot;
try
{
    if ($Force -and (launchctl list | grep kimbir.update-machine))
    {
        launchctl unload ~/Library/LaunchAgents/kimbir.export-and-deploy-kbi-work-calendar.plist
    }

    Copy-Item ./kimbir.export-and-deploy-kbi-work-calendar.plist ~/Library/LaunchAgents -Force

    launchctl load ~/Library/LaunchAgents/kimbir.export-and-deploy-kbi-work-calendar.plist
}
finally
{
    Pop-Location;
}

