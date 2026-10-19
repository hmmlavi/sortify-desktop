@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0\.."

echo ============================================================================
echo  Sortify v1.0.0 - Reproducible Windows Build ^& Release Pipeline
echo ============================================================================

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Virtual environment .venv\Scripts\python.exe not found.
  echo Create a clean virtual environment first:
  echo   py -3.12 -m venv .venv
  echo   .\.venv\Scripts\python.exe -m pip install --upgrade pip
  echo   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  exit /b 1
)

echo [1/5] Running automated test suite...
.venv\Scripts\python.exe -m unittest discover -s tests -v
if errorlevel 1 (
  echo [ERROR] Automated tests failed. Aborting build.
  exit /b 1
)

echo [2/5] Running PyInstaller with Sortify.spec...
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean Sortify.spec
if errorlevel 1 (
  echo [ERROR] PyInstaller build failed.
  exit /b 1
)

if not exist "dist\Sortify\Sortify.exe" (
  echo [ERROR] Expected dist\Sortify\Sortify.exe was not generated.
  exit /b 1
)

echo [3/5] Running standalone smoke test (--diagnose) outside source tree...
set "SMOKE_DIR=%TEMP%\Sortify Clean Smoke Test"
if exist "!SMOKE_DIR!" rmdir /s /q "!SMOKE_DIR!"
mkdir "!SMOKE_DIR!\App Copy"
mkdir "!SMOKE_DIR!\User Data"
xcopy /E /I /Q "dist\Sortify" "!SMOKE_DIR!\App Copy" >nul
set "SORTIFY_DATA_DIR=!SMOKE_DIR!\User Data"
"!SMOKE_DIR!\App Copy\Sortify.exe" --diagnose
if errorlevel 1 (
  echo [ERROR] Standalone smoke test failed!
  rmdir /s /q "!SMOKE_DIR!"
  exit /b 1
)
set "SORTIFY_DATA_DIR="
rmdir /s /q "!SMOKE_DIR!"

if not exist "release" mkdir "release"

echo [4/5] Checking for Inno Setup Compiler...
set "PF86=%ProgramFiles(x86)%"
set "ISCC_CMD="
echo       Searching for ISCC.exe
where iscc.exe >nul 2>nul && set "ISCC_CMD=iscc.exe"
if exist "%PF86%\Inno Setup 6\ISCC.exe" set "ISCC_CMD=%PF86%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_CMD=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%PROGRAMFILES%\Inno Setup 6\ISCC.exe" set "ISCC_CMD=%PROGRAMFILES%\Inno Setup 6\ISCC.exe"
if not defined ISCC_CMD goto iscc_missing
echo       Compiling the installer
"!ISCC_CMD!" "packaging\installer.iss"
if errorlevel 1 goto iscc_failed
goto iscc_done

:iscc_missing
echo [WARN] Inno Setup 6 ISCC.exe not found; skipping the installer build.
echo        Install Inno Setup 6 from https://jrsoftware.org/isinfo.php and re-run.
goto iscc_done

:iscc_failed
echo [ERROR] Inno Setup compilation failed.
exit /b 1

:iscc_done

echo [5/5] Generating release\SHA256SUMS.txt...
.venv\Scripts\python.exe packaging\build_release.py --checksums-only
if errorlevel 1 exit /b 1

echo ============================================================================
echo  Build Complete!
echo  Standalone App : dist\Sortify\Sortify.exe
if exist "release\Sortify-Setup-1.0.0.exe" (
  echo  Installer      : release\Sortify-Setup-1.0.0.exe
)
echo  Checksums      : release\SHA256SUMS.txt
echo ============================================================================
exit /b 0
