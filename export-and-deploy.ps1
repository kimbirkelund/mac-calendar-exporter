[CmdletBinding()]
param()

$PSCmdlet.MyInvocation.BoundParameters.Keys | ForEach-Object { Write-Verbose "$($PSCmdlet.MyInvocation.MyCommand)-$($_): $($PSCmdlet.MyInvocation.BoundParameters[$_])" }

$ErrorActionPreference = 'Stop';
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version 1;

Push-Location $PSScriptRoot;
try
{
    Remove-Item -Path 'page' -Recurse -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Path 'page' -ErrorAction SilentlyContinue | Out-Null

    ./setup-and-run.sh --no-interactive

    Push-Location 'page'
    try
    {
        npx --yes vercel@latest --yes --prod
    }
    finally
    {
        Pop-Location;
    }
}
finally
{
    Pop-Location;
}

