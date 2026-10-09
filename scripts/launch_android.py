"""Boot the installed plugin using its user-owned dependency environment."""
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
state = Path(os.environ.get('ANDROID_USE_STATE_DIR', str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AndroidUse')))
config_path = state / 'config.json'
config = json.loads(config_path.read_text(encoding='utf-8-sig')) if config_path.exists() else {}
python = config.get('python', sys.executable)
for key in ('adb', 'scrcpy', 'scrcpy_server', 'scrcpy_version'):
    if config.get(key): os.environ['ANDROID_USE_' + key.upper()] = config[key]
argv = [python, '-u', str(root / 'server/android_use.py')]
if config.get('serial'): argv += ['--serial', config['serial']]
os.execv(python, argv)
