import re

with open("modules/localization.py", "r", encoding="utf-8") as f:
    text = f.read()

# I will find '"btn_about_project": "...",' and EVERYTHING up to '"report_title"' and replace it.
text = re.sub(r'"btn_about_project": ".*?",.*?"report_title"', '"report_title"', text, flags=re.DOTALL)

with open("modules/localization.py", "w", encoding="utf-8") as f:
    f.write(text)
