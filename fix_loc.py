import re

with open("modules/localization.py", "r", encoding="utf-8") as f:
    text = f.read()

def repl(match):
    content = match.group(0)
    # Re-normalize any botched escaping back into literal multiline format with triple quotes
    # actually let's just make it triple quotes.
    return content.replace('"about_text": "', '"about_text": """').replace('",\n        "report_title"', '""",\n        "report_title"')

text = re.sub(r'"about_text": ".*?",(?=\n        "report_title")', repl, text, flags=re.DOTALL)

with open("modules/localization.py", "w", encoding="utf-8") as f:
    f.write(text)
