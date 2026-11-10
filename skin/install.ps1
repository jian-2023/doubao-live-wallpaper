# 安装：备份并重定向豆包快捷方式到启动器
$Here     = Split-Path -Parent $MyInvocation.MyCommand.Path
$Bak      = Join-Path $Here 'backup'
$DOUBAO   = 'C:\Users\86195\AppData\Local\Doubao\Application\Doubao.exe'
$Launcher = Join-Path $Here 'launcher.py'
$PyDir    = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python38'
$PyW      = Join-Path $PyDir 'pythonw.exe'
if (-not (Test-Path -LiteralPath $PyW)) {
    $PyDir = Split-Path -Parent (Get-Command python.exe).Source
    $PyW   = Join-Path $PyDir 'pythonw.exe'
    if (-not (Test-Path -LiteralPath $PyW)) { $PyW = Join-Path $PyDir 'python.exe' }
}

New-Item -ItemType Directory -Force -Path $Bak | Out-Null

$Targets = @(
    @{ Path = Join-Path $env:USERPROFILE 'Desktop\豆包.lnk';              Bak = 'doubao-desktop.lnk' },
    @{ Path = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\豆包.lnk'; Bak = 'doubao-startmenu.lnk' }
)

$sh = New-Object -ComObject WScript.Shell
foreach ($t in $Targets) {
    if (-not (Test-Path -LiteralPath $t.Path)) { Write-Output "skip (not found): $($t.Path)"; continue }
    $bakFile = Join-Path $Bak $t.Bak
    if (-not (Test-Path -LiteralPath $bakFile)) {
        Copy-Item -LiteralPath $t.Path -Destination $bakFile -Force
        Write-Output "backup -> $bakFile"
    }
    $lnk = $sh.CreateShortcut($t.Path)
    $lnk.TargetPath       = $PyW
    $lnk.Arguments        = '"' + $Launcher + '"'
    $lnk.WorkingDirectory = $Here
    $lnk.IconLocation     = $DOUBAO + ',0'
    $lnk.Description      = '豆包（真人壁纸版）'
    $lnk.Save()
    Write-Output "retargeted: $($t.Path)"
}
Write-Output 'install done'
