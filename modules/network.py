"""Windows network maintenance commands."""
import subprocess


def flush_dns():
    """Clear the Windows DNS resolver cache and return the command output."""
    result = subprocess.run(
        ["ipconfig", "/flushdns"],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    output = result.stdout.strip()
    error = result.stderr.strip()
    if result.returncode != 0:
        raise RuntimeError(error or output or "DNS flush failed")
    return output or "DNS cache flushed successfully."
