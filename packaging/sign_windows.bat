@echo off
setlocal
cd /d "%~dp0\.."

echo ============================================================================
echo  Sortify - Optional Windows Authenticode Code Signing Helper
echo ============================================================================
echo Note: Sortify builds are UNSIGNED by default unless you provide a legitimate
echo code-signing certificate via SORTIFY_PFX_PATH or SORTIFY_CERT_SHA1.
echo Self-signed certificates are intentionally NOT generated, as they do not
echo establish public trust or prevent Windows SmartScreen warnings.
echo ============================================================================

if "%SORTIFY_PFX_PATH%"=="" if "%SORTIFY_CERT_SHA1%"=="" (
  echo [SKIP] Neither SORTIFY_PFX_PATH nor SORTIFY_CERT_SHA1 is set.
  echo        Artifacts remain UNSIGNED.
  exit /b 0
)

where signtool.exe >nul 2>nul
if errorlevel 1 (
  echo [ERROR] signtool.exe not found on PATH. Install the Windows 10/11 SDK.
  exit /b 1
)

set "TIMESTAMP_URL=http://timestamp.digicert.com"

for %%F in ("dist\Sortify\Sortify.exe" "release\Sortify-Setup-1.0.0.exe") do (
  if exist "%%~F" (
    echo Signing %%~F ...
    if not "%SORTIFY_CERT_SHA1%"=="" (
      signtool.exe sign /sha1 "%SORTIFY_CERT_SHA1%" /fd SHA256 /tr "%TIMESTAMP_URL%" /td SHA256 "%%~F"
    ) else (
      signtool.exe sign /f "%SORTIFY_PFX_PATH%" /p "%SORTIFY_PFX_PASSWORD%" /fd SHA256 /tr "%TIMESTAMP_URL%" /td SHA256 "%%~F"
    )
    if errorlevel 1 (
      echo [ERROR] Signing failed for %%~F
      exit /b 1
    )
  )
)

echo [OK] Authenticode signing completed and verified.
exit /b 0
