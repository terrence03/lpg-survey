<#
  在 Windows Server 上安裝問卷後端為 Windows 服務（開機自動啟動、當掉自動重啟）。
  需求：Python 3.13（安裝時選「Install for all users」，含 py 啟動器）、NSSM（https://nssm.cc/download）

  隔離方式：
  - 套件裝在專案內的 .venv，不動到系統的 Python。
  - 服務用專屬的低權限虛擬帳戶「NT SERVICE\lpg-survey」執行，不用 LocalSystem。
    這個帳戶只能讀取程式資料夾、寫入 output\，secrets 只有它和系統管理員讀得到。
  - 只監聽 127.0.0.1，外部無法直接連線，只能經過 IIS。
  用法（以系統管理員身分開 PowerShell，在專案根目錄執行）：
    .\deploy\windows\install-service.ps1 -Nssm C:\tools\nssm\nssm.exe
  更新程式後只要重啟服務：nssm restart lpg-survey
#>
param(
  [string]$Nssm = "nssm.exe",
  [int]$Port = 8538,
  [string]$ServiceName = "lpg-survey"
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path "$PSScriptRoot\..\..").Path
Set-Location $root

if (-not (Test-Path ".venv")) { py -3.13 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
New-Item -ItemType Directory -Force output | Out-Null

& $Nssm install $ServiceName "$root\.venv\Scripts\python.exe" "-m uvicorn server.main:app --host 127.0.0.1 --port $Port"
& $Nssm set $ServiceName AppDirectory $root
& $Nssm set $ServiceName AppEnvironmentExtra "TZ=Asia/Taipei"
& $Nssm set $ServiceName AppStdout "$root\output\service.log"
& $Nssm set $ServiceName AppStderr "$root\output\service.log"
& $Nssm set $ServiceName AppRotateFiles 1
& $Nssm set $ServiceName AppRotateBytes 10485760
& $Nssm set $ServiceName Start SERVICE_AUTO_START

# Run as a dedicated low-privilege virtual account instead of LocalSystem.
$account = "NT SERVICE\$ServiceName"
sc.exe config $ServiceName obj= $account | Out-Null
icacls $root /grant "${account}:(OI)(CI)RX" | Out-Null
icacls "$root\output" /grant "${account}:(OI)(CI)M" | Out-Null
if (Test-Path "$root\.streamlit") {
  # Secrets: only administrators, SYSTEM and the service account may read them.
  icacls "$root\.streamlit" /inheritance:r /grant:r "Administrators:(OI)(CI)F" "SYSTEM:(OI)(CI)F" "${account}:(OI)(CI)R" | Out-Null
}

& $Nssm start $ServiceName

Start-Sleep -Seconds 3
Invoke-RestMethod "http://127.0.0.1:$Port/api/health"
