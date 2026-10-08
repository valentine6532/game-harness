#!/bin/bash
# Rebuild the plaza (optional: pass --build) and capture shots from Scripts/shot_config.json.
UE="/c/Program Files/Epic Games/UE_5.8/Engine/Binaries/Win64"
P="D:/HarnessPrograming/diablo/unreal/Nyablo"
LOG="D:/HarnessPrograming/diablo/unreal/logs"
# no console / editor windows on the user's desktop (4-23): nowin.py = CREATE_NO_WINDOW + SW_HIDE, -RenderOffScreen
NOWIN="pythonw D:/HarnessPrograming/diablo/workspace/plaza_v2/tools/nowin.py"
if [ "$1" = "--build" ] || [ "$1" = "--layout" ]; then
  [ "$1" = "--layout" ] && export NYABLO_SKIP_IMPORT=1   # rebuild level only, reuse imported assets
  $NOWIN "$UE/UnrealEditor-Cmd.exe" "$P/Nyablo.uproject" -run=pythonscript -script="$P/Scripts/ue_build_plaza.py" -unattended -nop4 -nosplash -stdout -FullStdOutLogOutput > "$LOG/build.log" 2>&1
  grep -E "PLAZA_BUILD_DONE|LogPython: Error" "$LOG/build.log" | head -5
fi
timeout 900 $NOWIN "$UE/UnrealEditor.exe" "$P/Nyablo.uproject" -ExecCmds="py $P/Scripts/ue_shot.py" \
  "-ini:EditorSettings:[/Script/UnrealEd.EditorPerformanceSettings]:bThrottleCPUWhenNotForeground=False" \
  -RenderOffScreen -nosplash -nop4 -log -abslog="$LOG/shot.log" > /dev/null 2>&1
grep -E "NYABLO_SHOT|LogPython: Error" "$LOG/shot.log" | cut -c1-200
