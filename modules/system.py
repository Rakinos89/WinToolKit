"""Windows privilege checks and system repair commands."""
import ctypes
import subprocess
import sys
from pathlib import Path


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def relaunch_as_admin():
    """Ask Windows UAC to relaunch the app. Returns True if accepted."""
    script = str(Path(__file__).resolve().parent.parent / "main.py")
    args = subprocess.list2cmdline([script])
    result = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, args, str(Path(script).parent), 1
    )
    if result <= 32:
        raise OSError(f"Windows did not launch elevated process (code {result}).")
    return True


REPAIR_COMMANDS = {
    "DISM RestoreHealth": ["DISM.exe", "/Online", "/Cleanup-Image", "/RestoreHealth"],
    "SFC Scan": ["sfc.exe", "/scannow"],
}
