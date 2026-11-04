"""Read-only gaming diagnostics and explicit Windows power-plan changes."""
import json
import re
import shutil
import socket
import subprocess
import time

import psutil

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
GAME_EXECUTABLES = {
    'wow.exe', 'wowclassic.exe', 'wowclassicera.exe', 'wowt.exe',
    'ragnarok.exe', 'ragexe.exe', 'ragexe_re.exe', 'ragzero.exe',
    'steam.exe', 'steamwebhelper.exe', 'ffxiv_dx11.exe', 'ffxiv.exe',
    'eldenring.exe', 'cs2.exe', 'valorant-win64-shipping.exe',
    'league of legends.exe', 'overwatch.exe', 'diablo iv.exe',
    'cyberpunk2077.exe', 'bg3.exe', 'game.exe',
}
# Launcher processes are deliberately excluded from the detected games list.
GAME_EXECUTABLES -= {'steam.exe', 'steamwebhelper.exe', 'game.exe'}


def gpu_info():
    """GPU adapter name from Windows; NVIDIA metrics when nvidia-smi exists."""
    info = {'name': 'Unavailable', 'utilization': 'Unavailable',
            'vram': 'Unavailable (vendor monitoring required)'}
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
             'Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name | ConvertTo-Json -Compress'],
            capture_output=True, text=True, errors='replace', timeout=12,
            creationflags=NO_WINDOW)
        if result.returncode == 0 and result.stdout.strip():
            names = json.loads(result.stdout.strip())
            if isinstance(names, str):
                names = [names]
            info['name'] = ', '.join(str(n) for n in names if n) or 'Unavailable'
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    if shutil.which('nvidia-smi'):
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total',
                 '--format=csv,noheader,nounits'], capture_output=True, text=True,
                errors='replace', timeout=5, creationflags=NO_WINDOW)
            if result.returncode == 0 and result.stdout.strip():
                fields = [x.strip() for x in result.stdout.splitlines()[0].split(',')]
                if len(fields) == 3:
                    info['utilization'] = f'{fields[0]}%'
                    info['vram'] = f'{fields[1]} / {fields[2]} MiB'
        except (OSError, subprocess.TimeoutExpired):
            pass
    return info


def game_processes():
    """Known game executables; not a comprehensive game detector."""
    found = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            name = proc.info['name'] or ''
            if name.casefold() in GAME_EXECUTABLES:
                memory = proc.info['memory_info']
                mib = memory.rss / (1024 ** 2) if memory else 0
                found.append((name, proc.info['pid'], round(mib)))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return sorted(found, key=lambda p: p[0].casefold())


def power_plans():
    """Return (guid, display name, active) from powercfg, locale independent."""
    result = subprocess.run(['powercfg', '/list'], capture_output=True,
                            text=True, errors='replace', timeout=10,
                            creationflags=NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or 'Unable to list power plans.')
    plans = []
    guid_pattern = re.compile(r'\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b')
    for line in result.stdout.splitlines():
        match = guid_pattern.search(line)
        if match:
            tail = line[match.end():].strip()
            name_match = re.search(r'\(([^()]*)\)', tail)
            plans.append((match.group(0), name_match.group(1) if name_match else match.group(0), '*' in tail))
    return plans


def activate_power_plan(guid):
    if not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', guid):
        raise ValueError('Invalid power-plan identifier.')
    result = subprocess.run(['powercfg', '/setactive', guid], capture_output=True,
                            text=True, errors='replace', timeout=12,
                            creationflags=NO_WINDOW)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Power plan change failed.')


def tcp_latency(host='1.1.1.1', port=443, timeout=2.0):
    """TCP connection latency, not ICMP ping or in-game latency."""
    start = time.perf_counter()
    with socket.create_connection((host, port), timeout=timeout):
        pass
    return round((time.perf_counter() - start) * 1000)
