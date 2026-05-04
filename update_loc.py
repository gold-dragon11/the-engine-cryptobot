import re

with open("modules/localization.py", "r") as f:
    content = f.read()

additions = {
    "en": '"margin_type": "Margin Type", "isolated": "ISOLATED", "cross": "CROSS",',
    "uk": '"margin_type": "Тип маржі", "isolated": "ІЗОЛЬОВАНА", "cross": "КРОСС",',
    "es": '"margin_type": "Tipo de Margen", "isolated": "AISLADO", "cross": "CRUZADO",',
    "de": '"margin_type": "Margentyp", "isolated": "ISOLIERT", "cross": "KREUZEN",',
    "ru": '"margin_type": "Тип маржи", "isolated": "ИЗОЛИРОВАННАЯ", "cross": "КРОСС",',
    "fr": '"margin_type": "Type de Marge", "isolated": "ISOLÉE", "cross": "CROISÉE",',
    "pl": '"margin_type": "Typ Depozytu", "isolated": "IZOLOWANY", "cross": "KRZYŻOWY",',
}

for lang, vals in additions.items():
    pattern = rf'("{lang}": {{\n)'
    content = re.sub(pattern, rf'\1        {vals}\n', content)

with open("modules/localization.py", "w") as f:
    f.write(content)
