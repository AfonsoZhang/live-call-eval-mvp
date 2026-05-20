# Upload this repo to GitHub (run after: gh auth login)
$ErrorActionPreference = "Stop"

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

$repoName = if ($args.Count -gt 0) { $args[0] } else { "live-call-eval-mvp" }

gh auth status | Out-Null

Write-Host "Creating public repo '$repoName' and pushing..."
gh repo create $repoName --public --source=. --remote=origin --push

Write-Host "Done. Open:"
gh repo view --web
