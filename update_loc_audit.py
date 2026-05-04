import json
import re

with open("modules/localization.py", "r", encoding="utf-8") as f:
    text = f.read()

audit_strings = {
    "en": {
        "usage_set_balance": "⚠️ <b>Usage:</b> <code>/set_balance &lt;amount&gt;</code>\nExample: <code>/set_balance 5000</code>",
        "balance_updated": "✅ <b>Balance updated:</b> {amount}",
        "error_positive_number": "❌ Please provide a valid positive number.",
        "usage_set_risk": "⚠️ <b>Usage:</b> <code>/set_risk &lt;percentage&gt;</code>\nExample: <code>/set_risk 2.5</code>",
        "risk_updated": "✅ <b>Risk updated:</b> {percent}%",
        "error_percentage": "❌ Please provide a valid percentage (e.g. 1.5, 2).",
        "settings_text": "⚙️ <b>Your Configuration</b>\n\n💼 Balance: <b>${balance:,.2f}</b>\n🎯 Risk: <b>{risk_percent}%</b> per trade\n\n<i>Use /set_balance or /set_risk to modify.</i>",
        "fetching_price": "⏳ Fetching BTC/USDT from Binance…",
        "usage_risk": "⚠️ <b>Usage:</b> <code>/risk &lt;balance&gt; &lt;risk%&gt; &lt;entry&gt; &lt;stop_loss&gt;</code>\n\nExample: <code>/risk 10000 1 65000 63500</code>",
        "error_numbers": "❌ All arguments must be numbers.",
        "invalid_input": "❌ Invalid input: {error}",
        "usage_analyze": "⚠️ <b>Usage:</b> <code>/analyze &lt;COIN&gt; [balance] [risk%]</code>\nExample: <code>/analyze BTC 10000 1</code>",
        "analyzing_status": "⏳ <b>Analyzing {symbol}...</b>\n\n"
    },
    "uk": {
        "usage_set_balance": "⚠️ <b>Використання:</b> <code>/set_balance &lt;amount&gt;</code>\nПриклад: <code>/set_balance 5000</code>",
        "balance_updated": "✅ <b>Баланс оновлено:</b> {amount}",
        "error_positive_number": "❌ Введіть дійсне додатне число.",
        "usage_set_risk": "⚠️ <b>Використання:</b> <code>/set_risk &lt;percentage&gt;</code>\nПриклад: <code>/set_risk 2.5</code>",
        "risk_updated": "✅ <b>Ризик оновлено:</b> {percent}%",
        "error_percentage": "❌ Введіть дійсний відсоток (наприклад, 1.5, 2).",
        "settings_text": "⚙️ <b>Ваші налаштування</b>\n\n💼 Баланс: <b>${balance:,.2f}</b>\n🎯 Ризик: <b>{risk_percent}%</b> на угоду\n\n<i>Використовуйте /set_balance або /set_risk для зміни.</i>",
        "fetching_price": "⏳ Отримання ціни BTC/USDT з Binance…",
        "usage_risk": "⚠️ <b>Використання:</b> <code>/risk &lt;balance&gt; &lt;risk%&gt; &lt;entry&gt; &lt;stop_loss&gt;</code>\n\nПриклад: <code>/risk 10000 1 65000 63500</code>",
        "error_numbers": "❌ Усі аргументи мають бути числами.",
        "invalid_input": "❌ Невірний ввід: {error}",
        "usage_analyze": "⚠️ <b>Використання:</b> <code>/analyze &lt;COIN&gt; [balance] [risk%]</code>\nПриклад: <code>/analyze BTC 10000 1</code>",
        "analyzing_status": "⏳ <b>Автоматичний аналіз {symbol}...</b>\n\n"
    },
    "es": {
        "usage_set_balance": "⚠️ <b>Uso:</b> <code>/set_balance &lt;amount&gt;</code>\nEjemplo: <code>/set_balance 5000</code>",
        "balance_updated": "✅ <b>Balance actualizado:</b> {amount}",
        "error_positive_number": "❌ Ingresa un número positivo válido.",
        "usage_set_risk": "⚠️ <b>Uso:</b> <code>/set_risk &lt;percentage&gt;</code>\nEjemplo: <code>/set_risk 2.5</code>",
        "risk_updated": "✅ <b>Riesgo actualizado:</b> {percent}%",
        "error_percentage": "❌ Ingresa un porcentaje válido (ej. 1.5, 2).",
        "settings_text": "⚙️ <b>Tu Configuración</b>\n\n💼 Balance: <b>${balance:,.2f}</b>\n🎯 Riesgo: <b>{risk_percent}%</b> por operación\n\n<i>Usa /set_balance o /set_risk para modificar.</i>",
        "fetching_price": "⏳ Obteniendo precio de BTC/USDT de Binance…",
        "usage_risk": "⚠️ <b>Uso:</b> <code>/risk &lt;balance&gt; &lt;risk%&gt; &lt;entry&gt; &lt;stop_loss&gt;</code>\n\nEjemplo: <code>/risk 10000 1 65000 63500</code>",
        "error_numbers": "❌ Todos los argumentos deben ser números.",
        "invalid_input": "❌ Entrada inválida: {error}",
        "usage_analyze": "⚠️ <b>Uso:</b> <code>/analyze &lt;COIN&gt; [balance] [risk%]</code>\nEjemplo: <code>/analyze BTC 10000 1</code>",
        "analyzing_status": "⏳ <b>Analizando {symbol}...</b>\n\n"
    },
    "de": {
        "usage_set_balance": "⚠️ <b>Verwendung:</b> <code>/set_balance &lt;amount&gt;</code>\nBeispiel: <code>/set_balance 5000</code>",
        "balance_updated": "✅ <b>Guthaben aktualisiert:</b> {amount}",
        "error_positive_number": "❌ Bitte gib eine gültige positive Zahl an.",
        "usage_set_risk": "⚠️ <b>Verwendung:</b> <code>/set_risk &lt;percentage&gt;</code>\nBeispiel: <code>/set_risk 2.5</code>",
        "risk_updated": "✅ <b>Risiko aktualisiert:</b> {percent}%",
        "error_percentage": "❌ Bitte gib einen gültigen Prozentsatz an (z.B. 1.5, 2).",
        "settings_text": "⚙️ <b>Deine Konfiguration</b>\n\n💼 Guthaben: <b>${balance:,.2f}</b>\n🎯 Risiko: <b>{risk_percent}%</b> pro Trade\n\n<i>Nutze /set_balance oder /set_risk zum Ändern.</i>",
        "fetching_price": "⏳ Hole BTC/USDT Preis von Binance…",
        "usage_risk": "⚠️ <b>Verwendung:</b> <code>/risk &lt;balance&gt; &lt;risk%&gt; &lt;entry&gt; &lt;stop_loss&gt;</code>\n\nBeispiel: <code>/risk 10000 1 65000 63500</code>",
        "error_numbers": "❌ Alle Argumente müssen Zahlen sein.",
        "invalid_input": "❌ Ungültige Eingabe: {error}",
        "usage_analyze": "⚠️ <b>Verwendung:</b> <code>/analyze &lt;COIN&gt; [balance] [risk%]</code>\nBeispiel: <code>/analyze BTC 10000 1</code>",
        "analyzing_status": "⏳ <b>Analysiere {symbol}...</b>\n\n"
    },
    "ru": {
        "usage_set_balance": "⚠️ <b>Использование:</b> <code>/set_balance &lt;amount&gt;</code>\nПример: <code>/set_balance 5000</code>",
        "balance_updated": "✅ <b>Баланс обновлен:</b> {amount}",
        "error_positive_number": "❌ Введите действительное положительное число.",
        "usage_set_risk": "⚠️ <b>Использование:</b> <code>/set_risk &lt;percentage&gt;</code>\nПример: <code>/set_risk 2.5</code>",
        "risk_updated": "✅ <b>Риск обновлен:</b> {percent}%",
        "error_percentage": "❌ Введите действительный процент (например, 1.5, 2).",
        "settings_text": "⚙️ <b>Ваши настройки</b>\n\n💼 Баланс: <b>${balance:,.2f}</b>\n🎯 Риск: <b>{risk_percent}%</b> на сделку\n\n<i>Используйте /set_balance или /set_risk для изменения.</i>",
        "fetching_price": "⏳ Получение цены BTC/USDT с Binance…",
        "usage_risk": "⚠️ <b>Использование:</b> <code>/risk &lt;balance&gt; &lt;risk%&gt; &lt;entry&gt; &lt;stop_loss&gt;</code>\n\nПример: <code>/risk 10000 1 65000 63500</code>",
        "error_numbers": "❌ Все аргументы должны быть числами.",
        "invalid_input": "❌ Неверный ввод: {error}",
        "usage_analyze": "⚠️ <b>Использование:</b> <code>/analyze &lt;COIN&gt; [balance] [risk%]</code>\nПример: <code>/analyze BTC 10000 1</code>",
        "analyzing_status": "⏳ <b>Анализ {symbol}...</b>\n\n"
    },
    "fr": {
        "usage_set_balance": "⚠️ <b>Utilisation :</b> <code>/set_balance &lt;amount&gt;</code>\nExemple : <code>/set_balance 5000</code>",
        "balance_updated": "✅ <b>Solde mis à jour :</b> {amount}",
        "error_positive_number": "❌ Veuillez fournir un nombre positif valide.",
        "usage_set_risk": "⚠️ <b>Utilisation :</b> <code>/set_risk &lt;percentage&gt;</code>\nExemple : <code>/set_risk 2.5</code>",
        "risk_updated": "✅ <b>Risque mis à jour :</b> {percent}%",
        "error_percentage": "❌ Veuillez fournir un pourcentage valide (ex: 1.5, 2).",
        "settings_text": "⚙️ <b>Votre Configuration</b>\n\n💼 Solde: <b>${balance:,.2f}</b>\n🎯 Risque: <b>{risk_percent}%</b> par trade\n\n<i>Utilisez /set_balance ou /set_risk pour modifier.</i>",
        "fetching_price": "⏳ Récupération du prix BTC/USDT depuis Binance…",
        "usage_risk": "⚠️ <b>Utilisation :</b> <code>/risk &lt;balance&gt; &lt;risk%&gt; &lt;entry&gt; &lt;stop_loss&gt;</code>\n\nExemple : <code>/risk 10000 1 65000 63500</code>",
        "error_numbers": "❌ Tous les arguments doivent être des nombres.",
        "invalid_input": "❌ Entrée invalide : {error}",
        "usage_analyze": "⚠️ <b>Utilisation :</b> <code>/analyze &lt;COIN&gt; [balance] [risk%]</code>\nExemple : <code>/analyze BTC 10000 1</code>",
        "analyzing_status": "⏳ <b>Analyse de {symbol}...</b>\n\n"
    },
    "pl": {
        "usage_set_balance": "⚠️ <b>Użycie:</b> <code>/set_balance &lt;amount&gt;</code>\nPrzykład: <code>/set_balance 5000</code>",
        "balance_updated": "✅ <b>Saldo zaktualizowane:</b> {amount}",
        "error_positive_number": "❌ Proszę podać prawidłową liczbę dodatnią.",
        "usage_set_risk": "⚠️ <b>Użycie:</b> <code>/set_risk &lt;percentage&gt;</code>\nPrzykład: <code>/set_risk 2.5</code>",
        "risk_updated": "✅ <b>Ryzyko zaktualizowane:</b> {percent}%",
        "error_percentage": "❌ Proszę podać prawidłowy procent (np. 1.5, 2).",
        "settings_text": "⚙️ <b>Twoja Konfiguracja</b>\n\n💼 Saldo: <b>${balance:,.2f}</b>\n🎯 Ryzyko: <b>{risk_percent}%</b> na transakcję\n\n<i>Użyj /set_balance lub /set_risk aby zmienić.</i>",
        "fetching_price": "⏳ Pobieranie ceny BTC/USDT z Binance…",
        "usage_risk": "⚠️ <b>Użycie:</b> <code>/risk &lt;balance&gt; &lt;risk%&gt; &lt;entry&gt; &lt;stop_loss&gt;</code>\n\nPrzykład: <code>/risk 10000 1 65000 63500</code>",
        "error_numbers": "❌ Wszystkie argumenty muszą być liczbami.",
        "invalid_input": "❌ Nieprawidłowe dane: {error}",
        "usage_analyze": "⚠️ <b>Użycie:</b> <code>/analyze &lt;COIN&gt; [balance] [risk%]</code>\nPrzykład: <code>/analyze BTC 10000 1</code>",
        "analyzing_status": "⏳ <b>Analizowanie {symbol}...</b>\n\n"
    }
}

for lang, payload in audit_strings.items():
    block = ""
    for k, v in payload.items():
        block += f'        "{k}": {json.dumps(v, ensure_ascii=False)},\n'
    
    target = f'"{lang}": {{\n'
    if target in text:
        text = text.replace(target, target + block)

with open("modules/localization.py", "w", encoding="utf-8") as f:
    f.write(text)
