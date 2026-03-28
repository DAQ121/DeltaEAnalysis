@echo off
echo ========================================
echo Test Strip Color Detection System - Build Script
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
copy "dist\试纸色差检测系统.exe" release\
xcopy frontend release\frontend\ /E /I /Y
copy 使用说明.txt release\

echo.
echo ========================================
echo Build completed!
echo Release files in: release\
echo ========================================
pause
