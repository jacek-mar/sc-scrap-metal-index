"""CC0-1.0. Find a Star Conflict install in the local Steam libraries (read-only)."""
import os
import re
from pathlib import Path

GAME_FOLDER = 'star conflict'


def steam_roots():
    roots = []
    try:
        import winreg
        for hive, key, value in [(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
                                 (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
                                 (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Valve\Steam', 'InstallPath')]:
            try:
                with winreg.OpenKey(hive, key) as handle:
                    roots.append(Path(winreg.QueryValueEx(handle, value)[0]))
            except OSError:
                pass
    except ImportError:
        pass
    for env in ('ProgramFiles(x86)', 'ProgramFiles'):
        if os.environ.get(env):
            roots.append(Path(os.environ[env]) / 'Steam')
    home = Path.home()
    roots += [home / '.steam/steam', home / '.local/share/Steam']
    unique = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique


def libraries(vdf_text):
    """Library folders from libraryfolders.vdf ("path" entries; old format: numbered keys)."""
    found = re.findall(r'"path"\s+"([^"]+)"', vdf_text)
    found += re.findall(r'^\s*"\d+"\s+"([^"]+)"', vdf_text, re.M)
    return [Path(p.replace('\\\\', '\\')) for p in found]


def find_install():
    candidates = []
    for root in steam_roots():
        candidates.append(root)
        vdf = root / 'steamapps' / 'libraryfolders.vdf'
        if vdf.is_file():
            try:
                candidates += libraries(vdf.read_text(encoding='utf-8', errors='replace'))
            except OSError:
                pass
    for library in candidates:
        game = library / 'steamapps' / 'common' / GAME_FOLDER
        if (game / 'data' / 'strings.pak').is_file():
            return game
    return None
