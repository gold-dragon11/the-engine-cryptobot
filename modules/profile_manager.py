import json
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# File path relative to main execution dir
PROFILES_FILE = "data/user_profiles.json"

# In-memory caching for faster reads
_profiles_cache: Dict[str, Dict[str, float]] = {}

def load_profiles() -> None:
    """Load profiles from disk to memory cache."""
    global _profiles_cache
    if not os.path.exists("data"):
        os.makedirs("data")
    
    if os.path.exists(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, "r", encoding="utf-8") as f:
                _profiles_cache = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing {PROFILES_FILE}: {e}")
            _profiles_cache = {}
    else:
        _profiles_cache = {}

def save_profiles() -> None:
    """Flush memory cache to disk."""
    if not os.path.exists("data"):
        os.makedirs("data")
    try:
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(_profiles_cache, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving {PROFILES_FILE}: {e}")

def get_user_profile(user_id: int) -> Dict[str, Any]:
    """Retrieve user's balance, risk_percent, and language. Initialize if not found."""
    uid_str = str(user_id)
    if uid_str not in _profiles_cache:
        # Default starting stats
        _profiles_cache[uid_str] = {
            "balance": 1000.0,
            "risk_percent": 2.0,
            "language": "en"
        }
        save_profiles()
    
    # Backward compatibility: Ensure old profiles have 'language' key
    if "language" not in _profiles_cache[uid_str]:
        _profiles_cache[uid_str]["language"] = "en"
        save_profiles()
        
    return _profiles_cache[uid_str]

def update_user_profile(user_id: int, updates: Dict[str, Any]) -> None:
    """Update profile attributes and sync to disk."""
    uid_str = str(user_id)
    # Ensure initialized
    if uid_str not in _profiles_cache:
        _profiles_cache[uid_str] = {
            "balance": 1000.0,
            "risk_percent": 2.0,
            "language": "en"
        }
    
    for k, v in updates.items():
        _profiles_cache[uid_str][k] = v
        
    save_profiles()

# Preload successfully on module import to prep memory map
load_profiles()
