"""
config_manager.py
Handles loading/saving the desktop pet's settings so it remembers
position, size, opacity, speed, and the media library between runs.
"""
import json
import os
import sys


def get_app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(get_app_dir(), "config.json")

DEFAULT_CONFIG = {
    "pos_x": 200,
    "pos_y": 200,
    "size": 200,            # sprite height in px (width scales to match aspect ratio)
    "opacity": 1.0,         # 0.0 - 1.0
    "speed": 1.0,           # playback speed multiplier
    "current_media": None,  # path to the currently active sprite/video
    "media_library": [],    # list of paths the user has added
    "chroma_lower": [35, 40, 40],
    "chroma_upper": [90, 255, 255],
    "auto_hide_on_fullscreen": True,
    "click_through": False,
    "roam_enabled": True,
    "roam_speed": 1.5,
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            # fill in any keys missing from an older config file
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError as e:
        print(f"[config_manager] Failed to save config: {e}")
