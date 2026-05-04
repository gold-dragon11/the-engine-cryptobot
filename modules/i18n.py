import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

LANGUAGE_NAMES = {
    "en": "🇬🇧 English",
    "uk": "🇺🇦 Українська",
    "es": "🇪🇸 Español",
    "de": "🇩🇪 Deutsch",
    "ru": "🇷🇺 Русский",
    "fr": "🇫🇷 Français",
    "pl": "🇵🇱 Polski",
}

class LocalizationManager:
    def __init__(self, locales_dir: str = "locales", default_lang: str = "en"):
        self.locales_dir = locales_dir
        self.default_lang = default_lang
        # In current_lang we keep the ENV one as a secondary fallback or default if no lang provided
        self.env_lang = os.getenv("UI_LANGUAGE", self.default_lang).lower()
        self.translations = {}
        
        self._load_all_languages()

    def _load_all_languages(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        locales_path = os.path.join(base_dir, self.locales_dir)
        
        if not os.path.exists(locales_path):
            logger.error(f"Locales directory not found: {locales_path}")
            return

        for filename in os.listdir(locales_path):
            if filename.endswith(".json"):
                lang = filename.replace(".json", "")
                filepath = os.path.join(locales_path, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        self.translations[lang] = json.load(f)
                    logger.debug(f"Loaded i18n dictionary for '{lang}'")
                except Exception as e:
                    logger.error(f"Failed to load i18n dictionary {filename}: {e}")

    def get(self, key_path: str, lang: str = None, **kwargs) -> str:
        """
        Retrieves a string via dot notation.
        Priority:
        1. Requested lang
        2. ENV lang (UI_LANGUAGE)
        3. Default lang (en)
        """
        keys = key_path.split('.')
        
        target_lang = (lang or self.env_lang).lower()
        
        # 1. Try requested/env language
        result = self._navigate_dict(self.translations.get(target_lang, {}), keys)
        
        # 2. Try ENV lang if not already tried
        if result is None and target_lang != self.env_lang:
            result = self._navigate_dict(self.translations.get(self.env_lang, {}), keys)
        
        # 3. Fallback to default
        if result is None and target_lang != self.default_lang and self.env_lang != self.default_lang:
            result = self._navigate_dict(self.translations.get(self.default_lang, {}), keys)
            
        # Return key if literally nowhere to be found
        if result is None:
            return key_path

        # Format if string
        if isinstance(result, str) and kwargs:
            try:
                return result.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Missing format key {e} for i18n string '{key_path}'")
                return result
        return str(result)

    def _navigate_dict(self, d: dict, keys: list):
        current = d
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        return current

# Global singleton
i18n = LocalizationManager()
