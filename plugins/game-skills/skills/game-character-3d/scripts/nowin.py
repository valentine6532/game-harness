"""Run a command without popping a console window on the user's desktop (Windows).

pythonw nowin.py <exe> [args...]

Claude Code's shell has no console of its own, so every console program it starts (blender.exe, python.exe,
UnrealEditor-Cmd.exe) gets a fresh visible console window that steals focus. Start this with pythonw (no window
itself); the child gets CREATE_NO_WINDOW (a hidden console that its own children inherit, e.g. process_character's
fix_textures.py call) and SW_HIDE for GUI programs. Output is passed through, exit code returned.
"""
import shutil
import subprocess
import sys

sys.argv[1] = shutil.which(sys.argv[1]) or sys.argv[1]     # 'codex' -> ...\codex.cmd (PATHEXT), as a shell would
si = subprocess.STARTUPINFO()
si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
si.wShowWindow = 0                                   # SW_HIDE
p = subprocess.Popen(sys.argv[1:], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=si)
out = sys.stdout.buffer if sys.stdout else None
for line in p.stdout:
    if out:
        out.write(line)
        out.flush()
sys.exit(p.wait())
