# Run after: gh auth login
# Creates repo "instagram-insights" and pushes to GitHub

$ErrorActionPreference = "Stop"
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
$gh = "C:\Program Files\GitHub CLI\gh.exe"
$repoRoot = "C:\Users\LENOVO\Downloads\instagram-insights"

Set-Location $repoRoot

& $gh auth status
if ($LASTEXITCODE -ne 0) {
    Write-Host "Run: gh auth login"
    exit 1
}

# Change ORG below if repo should live under an organization (e.g. ahl-org-name)
# Leave empty to create under your personal account
$ORG = "ahl-official"

$repoName = "instagram-insights"
$fullName = if ($ORG) { "$ORG/$repoName" } else { $repoName }

& $gh repo create $fullName --public --source=. --remote=origin --description "Instagram DM and comment insights for Alchemane and AHL brands" --push

if ($LASTEXITCODE -eq 0) {
    Write-Host "Pushed to https://github.com/$fullName"
} else {
    Write-Host "If repo already exists, try:"
    Write-Host "  git remote add origin https://github.com/$fullName.git"
    Write-Host "  git push -u origin main"
}
