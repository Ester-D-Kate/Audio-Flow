import json
import sys
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG: Dict[str, Any] = {
    "hotkeys": {
        "start": "ctrl+shift+l",
        "stop": "ctrl+alt+s",
        "pause": "ctrl+shift+space",
        "cancel": "ctrl+shift+esc",
        "prompt": "ctrl+shift+alt+p",
    },
}


def load_config() -> Dict[str, Any]:
    # Determine where to look for config.json
    if getattr(sys, 'frozen', False):
        # If running as compiled exe, look in the same folder as the exe
        base_path = Path(sys.executable).parent
    else:
        # If running as script, look in project root
        base_path = Path(__file__).resolve().parent.parent

    cfg_path = base_path / "config.json"
    
    if not cfg_path.exists():
        # Fallback to bundled config if external one is missing (for frozen app)
        if getattr(sys, 'frozen', False):
             # In PyInstaller, bundled files are in sys._MEIPASS
             bundled_path = Path(sys._MEIPASS) / "config.json"
             if bundled_path.exists():
                 cfg_path = bundled_path
             else:
                 return DEFAULT_CONFIG
        else:
             return DEFAULT_CONFIG

    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            user_cfg = json.load(fh)
    except Exception:
        return DEFAULT_CONFIG
    cfg = DEFAULT_CONFIG.copy()
    cfg.update(user_cfg)
    # Merge nested hotkeys dict if provided
    if "hotkeys" in user_cfg and isinstance(user_cfg["hotkeys"], dict):
        merged = DEFAULT_CONFIG.get("hotkeys", {}).copy()
        merged.update(user_cfg["hotkeys"])
        cfg["hotkeys"] = merged
    return cfg
