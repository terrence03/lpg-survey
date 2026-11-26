<#
  在 Windows Server 的 IIS 上安裝問卷網站，網址為 https://<網域>/lpg-survey/
  需求：
    - IIS
    - HttpPlatformHandler v1.2（https://www.iis.net/downloads/microsoft/httpplatformhandler）
    - Python 3.13（安裝時選「Install for all users」）
  用法（以系統管理員身分開 PowerShell，在專案根目錄執行）：
    Set-ExecutionPolicy -Scope Process Bypass
    .\deploy\windows\setup.ps1 -Site "lpg.org.tw"
  -Site 是 IIS 管理員左側看到的網站名稱。更新程式後重跑一次即可，不會重複建立。

  隔離方式：
    - 套件裝在專案內的 .venv，不動到系統 Python。
    - 程式以 IIS 專屬的低權限帳戶「IIS AppPool\lpg-survey」執行：
      只能讀取專案資料夾、寫入 output\，config\credentials.toml 只有它與系統管理員讀得到。
    - uvicorn 只聽 127.0.0.1，外部只能經過 IIS 連進來。
#>
param(
  [Parameter(Mandatory = $true)][string]$Site,
  [string]$AppName = "lpg-survey"
)
$ErrorActionPreference = "Stop"
Import-Module WebAdministration
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $root

if (-not (Get-WebGlobalModule -Name httpPlatformHandler)) {
  throw "找不到 HttpPlatformHandler，請先安裝：https://www.iis.net/downloads/microsoft/httpplatformhandler"
}
if (-not (Test-Path "IIS:\Sites\$Site")) {
  throw "IIS 裡找不到名為「$Site」的網站。目前的網站有：$((Get-Website).Name -join '、')"
}

Write-Host "1/5 安裝 Python 套件到 .venv" -ForegroundColor Cyan
if (-not (Test-Path ".venv")) { py -3.13 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
New-Item -ItemType Directory -Force "output\logs" | Out-Null
& .\.venv\Scripts\python.exe -c "import server.main"
if ($LASTEXITCODE -ne 0) {
  throw "程式無法載入（見上方錯誤）。若是 DLL 或存取被拒，請確認防毒或應用程式控管沒有擋住 $root。"
}

Write-Host "2/5 產生 iis\web.config" -ForegroundColor Cyan
if ((Test-Path "IIS:\AppPools\$AppName") -and (Get-WebAppPoolState -Name $AppName).Value -ne "Stopped") {
  try { Stop-WebAppPool -Name $AppName } catch { }
}
$appDir = Join-Path $root "iis"
New-Item -ItemType Directory -Force $appDir | Out-Null
$config = Get-Content "$PSScriptRoot\web.config.template" -Raw -Encoding UTF8
$config = $config.Replace("{{ROOT}}", $root).Replace("{{BASE_PATH}}", "/$AppName")
$target = "$appDir\web.config"
$current = if (Test-Path $target) { Get-Content $target -Raw -Encoding UTF8 } else { "" }
if ($current -ne $config) {
  # IIS or antivirus may hold the file for a moment; retry a few times.
  for ($i = 1; $i -le 10; $i++) {
    try { [IO.File]::WriteAllText($target, $config, (New-Object Text.UTF8Encoding $true)); break }
    catch { if ($i -eq 10) { throw "web.config 一直被佔用，請稍等一分鐘再重跑：$_" }; Start-Sleep -Seconds 2 }
  }
}

Write-Host "3/5 建立應用程式集區 $AppName" -ForegroundColor Cyan
$poolPath = "IIS:\AppPools\$AppName"
if (-not (Test-Path $poolPath)) { New-WebAppPool -Name $AppName | Out-Null }
Set-ItemProperty $poolPath -Name managedRuntimeVersion -Value ""
Set-ItemProperty $poolPath -Name startMode -Value "AlwaysRunning"
Set-ItemProperty $poolPath -Name processModel.identityType -Value "ApplicationPoolIdentity"
Set-ItemProperty $poolPath -Name processModel.idleTimeout -Value ([TimeSpan]::Zero)

Write-Host "4/5 設定資料夾權限" -ForegroundColor Cyan
$account = "IIS AppPool\$AppName"
icacls $root /grant "${account}:(OI)(CI)RX" | Out-Null
icacls "$root\output" /grant "${account}:(OI)(CI)M" | Out-Null
if (Test-Path "$root\config\credentials.toml") {
  icacls "$root\config" /inheritance:r /grant:r "Administrators:(OI)(CI)F" "SYSTEM:(OI)(CI)F" "${account}:(OI)(CI)R" | Out-Null
} else {
  Write-Warning "找不到 config\credentials.toml，資料會只寫到 output\*.csv。放好後請重跑此腳本。"
}

Write-Host "5/5 在網站「$Site」下建立 /$AppName" -ForegroundColor Cyan
if (Get-WebApplication -Site $Site -Name $AppName) {
  Set-ItemProperty "IIS:\Sites\$Site\$AppName" -Name physicalPath -Value $appDir
  Set-ItemProperty "IIS:\Sites\$Site\$AppName" -Name applicationPool -Value $AppName
} else {
  New-WebApplication -Site $Site -Name $AppName -PhysicalPath $appDir -ApplicationPool $AppName | Out-Null
}
if ((Get-WebAppPoolState -Name $AppName).Value -eq "Started") { Restart-WebAppPool -Name $AppName } else { Start-WebAppPool -Name $AppName }

Write-Host "`n完成。請開啟 https://<網域>/$AppName/ 測試。" -ForegroundColor Green
Write-Host "程式記錄檔在 $root\output\logs\，寫入 Sheets 失敗時的備援 CSV 在 $root\output\"
