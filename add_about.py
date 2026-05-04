import re, json

with open("modules/localization.py", "r", encoding="utf-8") as f:
    text = f.read()

data = {
    "en": {
        "btn_about_project": "ℹ️ About the Project",
        "about_text": "🐉 <b>Shadow of the Dragon Ecosystem</b>\n\nWelcome to the ultimate Quantitative Crypto Oracle. Our platform bridges the gap between institutional risk management and cutting-edge artificial intelligence.\n\n🧠 <b>AI Analysis</b>\nPowered by Gemini 3.1 Pro, the bot analyzes market structure, Fear & Greed indices, and live global news feeds to yield intelligent, context-aware directional biases.\n\n👁️ <b>The Watcher</b>\nA 24/7 autonomous monitoring system that perpetually scans tier-1 cryptocurrencies, delivering high-confidence trigger signals.\n\n🛡️ <b>Personal Risk Management</b>\nA dynamic ecosystem tailored to your portfolio. Customize your parameters to enforce calculated Stop Losses (ATR-derived) ensuring absolute capital preservation.\n\n📈 <b>Dragon Academy</b>\nBuilt-in educational pillars designed to enhance your understanding of risk thresholds, reward ratios, and margin safety.\n\n🌍 <b>Professional Support</b>\nSeamlessly process complex quantitative data structures across 7 natively supported languages."
    },
    "uk": {
        "btn_about_project": "ℹ️ Про проєкт",
        "about_text": "🐉 <b>Екосистема Shadow of the Dragon</b>\n\nЛаскаво просимо до потужного Крипто Оракула. Наша платформа поєднує інституційний ризик-менеджмент із передовим штучним інтелектом.\n\n🧠 <b>ШІ Аналіз</b>\nПрацюючи на базі Gemini 3.1 Pro, бот аналізує структуру ринку, індекс Страху та Жадібності і світові новини для точних прогнозів.\n\n👁️ <b>The Watcher (Спостерігач)</b>\nАвтономна система моніторингу 24/7, яка постійно перевіряє топові криптовалюти та надсилає сигнали з найвищою впевненістю.\n\n🛡️ <b>Персональний ризик-менеджмент</b>\nЕкосистема, налаштована під ваш портфель. Використовуйте свої параметри для розрахунку безпечних Stop Loss (на базі ATR), що гарантує збереження капіталу.\n\n📈 <b>Академія Дракона</b>\nВбудовані освітні матеріали для кращого розуміння меж ризиків, співвідношення R:R та безпеки забезпечення.\n\n🌍 <b>Професійна підтримка</b>\nБагатомовна обробка складних квантитативних метрик сімома мовами."
    },
    "es": {
        "btn_about_project": "ℹ️ Sobre el Proyecto",
        "about_text": "🐉 <b>Ecosistema Shadow of the Dragon</b>\n\nBienvenido al Oráculo Cuantitativo definitivo. Nuestra plataforma une la gestión de riesgos institucional con la inteligencia artificial.\n\n🧠 <b>Análisis IA</b>\nImpulsado por Gemini 3.1 Pro, el bot escanea la estructura del mercado, el miedo y la codicia y noticias en vivo.\n\n👁️ <b>El Observador</b>\nMonitoreo autónomo 24/7 que analiza criptomonedas top, entregando señales de alta confianza.\n\n🛡️ <b>Gestión de Riesgo Personal</b>\nUn entorno adaptado a tu cartera. Usa tus parámetros para generar Stop Losses seguros basados en ATR, garantizando la preservación del capital.\n\n📈 <b>La Academia del Dragón</b>\nMódulo educativo para comprender umbrales de riesgo, ratios R:R y márgenes seguros.\n\n🌍 <b>Soporte Profesional</b>\nProcesa métricas cuánticas complejas en 7 idiomas nativos."
    },
    "de": {
        "btn_about_project": "ℹ️ Über das Projekt",
        "about_text": "🐉 <b>Shadow of the Dragon Ökosystem</b>\n\nWillkommen beim definitiven krypto-quantitativen Orakel. Wir verbinden institutionelles Risikomanagement mit KI.\n\n🧠 <b>KI-Analyse</b>\nAngetrieben durch Gemini 3.1 Pro analysiert der Bot Marktstrukturen, Angst & Gier sowie Live-Nachrichten.\n\n👁️ <b>The Watcher</b>\n24/7 autonomes Überwachungssystem für erstklassige Kryptowährungen, das extrem zuverlässige Alarme liefert.\n\n🛡️ <b>Persönliches Risikomanagement</b>\nPassen Sie Ihre Vorgaben an, um sichere (ATR-abgeleitete) Stop-Losses zu erzwingen und ihr Kapital zu maximieren.\n\n📈 <b>Drachen-Akademie</b>\nBildungsmodul zum Verständnis von Risikoschwellen, Gewinnraten und Margensicherheit.\n\n🌍 <b>Professioneller Support</b>\nKomplexe Metriken nahtlos in 7 Sprachen verarbeiten."
    },
    "ru": {
        "btn_about_project": "ℹ️ О проекте",
        "about_text": "🐉 <b>Экосистема Shadow of the Dragon</b>\n\nДобро пожаловать в мощнейший Крипто Оракул. Наша платформа объединяет институциональный риск-менеджмент с ИИ.\n\n🧠 <b>ИИ Анализ</b>\nОсновываясь на Gemini 3.1 Pro, бот анализирует рыночную структуру, индекс Страха и Жадности и мировые новости.\n\n👁️ <b>The Watcher (Наблюдатель)</b>\nАвтономная система 24/7, постоянно сканирующая топ-криптовалюты для поиска уверенных сигналов.\n\n🛡️ <b>Персональный риск-менеджмент</b>\nДинамическая система, подстраивающаяся под ваш портфель. Вычисляет безопасные Stop Loss (на базе ATR) для защиты капитала.\n\n📈 <b>Академия Дракона</b>\nВстроенные обучающие материалы для понимания порогов риска, R:R и безопасности маржи.\n\n🌍 <b>Профессиональная поддержка</b>\nКомплексная работа с квантитативными данными на 7 языках."
    },
    "fr": {
        "btn_about_project": "ℹ️ À propos du Projet",
        "about_text": "🐉 <b>Écosystème Shadow of the Dragon</b>\n\nBienvenue dans l'Oracle Crypto Quantitatif ultime. Nous relions la gestion institutionnelle des risques à l'IA.\n\n🧠 <b>Analyse IA</b>\nPropulsé par Gemini 3.1 Pro, le bot analyse les structures de marché, les indices de Peur et de Cupidité et l'actualité en direct.\n\n👁️ <b>L'Observateur</b>\nSystème de surveillance autonome 24/7 scannant les meilleures cryptomonnaies pour des signaux très fiables.\n\n🛡️ <b>Gestion personnelle des risques</b>\nAdopte vos paramètres pour forcer des Stop Losses calculés (basés sur l'ATR) assurant la préservation du capital.\n\n📈 <b>Académie du Dragon</b>\nModule éducatif conçu pour améliorer votre compréhension des seuils de risque, des ratios R:R et des marges.\n\n🌍 <b>Support Professionnel</b>\nTraite des structures de données complexes en 7 langues."
    },
    "pl": {
        "btn_about_project": "ℹ️ O projekcie",
        "about_text": "🐉 <b>Ekosystem Shadow of the Dragon</b>\n\nWitaj w ostatecznej Wyroczni Krypto. Łączymy instytucjonalne zarządzanie ryzykiem z AI.\n\n🧠 <b>Analiza AI</b>\nZasilany przez Gemini 3.1 Pro bot analizuje strukturę rynkową, Indeks Strachu i Chciwości oraz wiadomości na żywo.\n\n👁️ <b>Obserwator</b>\nAutonomiczny system 24/7, który skanuje topowe kryptowaluty, dostarczając sygnały o wysokiej pewności.\n\n🛡️ <b>Osobiste zarządzanie ryzykiem</b>\nWykorzystaj swoje parametry, by wymuszać bezpieczne Stop Lossy (na bazie ATR), co gwarantuje ochronę kapitału.\n\n📈 <b>Akademia Smoka</b>\nWbudowane filary edukacyjne zaprojektowane w celu zrozumienia progów ryzyka, R:R i bezpieczeństwa depozytów.\n\n🌍 <b>Profesjonalne wsparcie</b>\nPrzetwarza złożone struktury danych w 7 językach."
    }
}

for lang, payload in data.items():
    s_btn = json.dumps(payload["btn_about_project"], ensure_ascii=False)
    s_txt = json.dumps(payload["about_text"], ensure_ascii=False)
    repl = f'        "btn_about_project": {s_btn},\n        "about_text": {s_txt},\n'
    # Use replace
    target = f'"{lang}": {{\n'
    if target in text:
        text = text.replace(target, target + repl)

with open("modules/localization.py", "w", encoding="utf-8") as f:
    f.write(text)
