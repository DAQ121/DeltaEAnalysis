@echo off
echo ========================================
echo 试纸色差检测系统 - Windows打包脚本
echo ========================================
echo.

echo [1/3] 安装PyInstaller...
pip install pyinstaller

echo.
echo [2/3] 开始打包...
pyinstaller build.spec

echo.
echo [3/3] 整理发布文件...
if exist release rmdir /s /q release
mkdir release
copy "dist\试纸色差检测系统.exe" release\
xcopy frontend release\frontend\ /E /I /Y
copy 使用说明.txt release\

echo.
echo ========================================
echo 打包完成！
echo 发布文件位于: release\
echo ========================================
pause
