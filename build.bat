@echo off
echo ========================================
echo BioManager Build Script
echo ========================================

REM Check if PyInstaller is installed
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    python -m pip install pyinstaller
)

REM Create resources directory if not exists
if not exist "resources\icons" mkdir "resources\icons"

REM Check if icon exists
if not exist "resources\icons\app.ico" (
    echo WARNING: Icon file not found at resources/icons/app.ico
    echo Building without icon...
)

REM Build the executable
echo Building BioManager...
python -m PyInstaller build.spec --clean

if errorlevel 1 (
    echo.
    echo ========================================
    echo Build FAILED! Check errors above.
    echo ========================================
) else (
    echo.
    echo ========================================
    echo Build complete!
    echo Executable: dist\BioManager.exe
    echo ========================================
)
pause
