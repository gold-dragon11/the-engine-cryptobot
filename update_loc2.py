import re

with open("modules/localization.py", "r") as f:
    content = f.read()

additions = {
    "en": '"recommended": "(Recommended)",',
    "uk": '"recommended": "(Рекомендовано)",',
    "es": '"recommended": "(Recomendado)",',
    "de": '"recommended": "(Empfohlen)",',
    "ru": '"recommended": "(Рекомендовано)",',
    "fr": '"recommended": "(Recommandé)",',
    "pl": '"recommended": "(Zalecane)",',
}

for lang, vals in additions.items():
    pattern = rf'("{lang}": {{\n)'
    content = re.sub(pattern, rf'\1        {vals}\n', content)

with open("modules/localization.py", "w") as f:
    f.write(content)
