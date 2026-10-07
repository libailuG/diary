param([string]$DataDir = '')
Set-Location -LiteralPath $PSScriptRoot
$diaryLaunchArgs = @('bootstrap.py')
if ($DataDir) { $diaryLaunchArgs += @('--data-dir', $DataDir) }
foreach ($diaryCandidate in @('py', 'python')) {
    if (-not (Get-Command $diaryCandidate -ErrorAction SilentlyContinue)) { continue }
    $diaryPrefix = @()
    if ($diaryCandidate -eq 'py') { $diaryPrefix = @('-3') }
    & $diaryCandidate @diaryPrefix -c 'import sys; assert sys.version_info >= (3, 10)' 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $diaryCandidate @diaryPrefix @diaryLaunchArgs
        exit $LASTEXITCODE
    }
}
Write-Error 'Python 3.10+ was not found. Install Python or use the portable Windows package; Conda is not required.'
exit 1
