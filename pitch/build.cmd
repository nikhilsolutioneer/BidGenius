@echo off
rem Rebuild the pitch deck from the running app.
rem Usage: pitch\build.cmd [baseUrl] [projectId]
rem   e.g. pitch\build.cmd http://127.0.0.1:8001 project_f1acfeec34bc4fa4
setlocal
cd /d "%~dp0\.."
set BASE=%~1
if "%BASE%"=="" set BASE=http://127.0.0.1:8000
node pitch\capture.cjs %BASE% %2 pitch\shots || exit /b 1
node pitch\build_deck.mjs %BASE% %2 || exit /b 1
"C:\Program Files\LibreOffice\program\soffice.exe" --headless --norestore --convert-to pdf --outdir pitch pitch\BidGenius_AI_Pitch.pptx
echo Deck: pitch\BidGenius_AI_Pitch.pptx and pitch\BidGenius_AI_Pitch.pdf
