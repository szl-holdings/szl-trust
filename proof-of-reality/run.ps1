# Run the SZL Proof-of-Reality verifier. Normal (non-admin) PowerShell.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m pip install --quiet cryptography
python verify_all.py @args
Write-Host "`nReport: $(Resolve-Path report\proof_of_reality.md)" -ForegroundColor Green
Get-Content report\proof_of_reality.md
