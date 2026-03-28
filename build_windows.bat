@echo off
echo ========================================
echo Build Script
echo ========================================
echo.

echo [1/3] Installing PyInstaller...
pip install pyinstaller

echo.
echo [2/3] Building executable...
pyinstaller build.spec

echo.
echo [3/3] Organizing release files...
if exist release rmdir /s /q release
mkdir release
xcopy "dist\*.exe" release\ /Y
xcopy frontend release\frontend\ /E /I /Y
copy *.txt release\ /Y

echo.
echo ========================================
echo Build completed!
echo Release files in: release\
echo ========================================
pause
