import json, re

with open("modules/localization.py", "r", encoding="utf-8") as f:
    text = f.read()

# I will translate these using basic domain vocabulary for the 7 languages
audit_strings = {
    "en": {
        "binance_error": "📡 Could not reach Binance. Check your connection or try again shortly.",
        "price_report": "🟡 <b>BTC / USDT</b>  |  Binance Spot\n\n💵 Price:      <b>${last:,.2f}</b>\n📈 24h Change: {change_sign} {change_pct:.2f}%\n🔺 24h High:   ${high:,.2f}\n🔻 24h Low:    ${low:,.2f}\n📦 Volume:     {volume:,.2f} BTC\n🏷 Bid / Ask:  ${bid:,.2f} / ${ask:,.2f}",
        "manual_risk_report": "⚖️ <b>Risk Management Report (Manual)</b>\n\n🔷 Direction:        {direction}\n💼 Balance:          ${balance:,.2f}\n🎯 Risk:             {risk_percent}%  →  <b>${risk_amount:,.2f}</b>\n📍 Entry:            ${entry:,.4f}\n🛑 Stop-Loss:        ${stop_loss:,.4f}\n🏆 Take Profit:      <b>${take_profit:,.4f}</b>  (1:2 R:R)\n📏 Risk per Unit:    ${risk_per_unit:,.2f}\n\n━━━━━━━━━━━━━━━━━━━━\n📦 Position Size:    <b>{position_size:,.6f} units</b>\n💵 Position Value:   <b>${position_value:,.2f}</b>\n⚡ Leverage:         <b>{leverage}x</b>\n💸 Breakeven Fee:    {breakeven:.3f}%\n\n<i>⚠️ This is not financial advice.</i>"
    },
    "uk": {
        "binance_error": "📡 Не вдалося зв'язатися з Binance. Перевірте з'єднання.",
        "price_report": "🟡 <b>BTC / USDT</b>  |  Binance Spot\n\n💵 Ціна:       <b>${last:,.2f}</b>\n📈 24г Зміна:  {change_sign} {change_pct:.2f}%\n🔺 24г Макс:   ${high:,.2f}\n🔻 24г Мін:    ${low:,.2f}\n📦 Об'єм:      {volume:,.2f} BTC\n🏷 Bid / Ask:  ${bid:,.2f} / ${ask:,.2f}",
        "manual_risk_report": "⚖️ <b>Звіт з Ризик-менеджменту (Ручний)</b>\n\n🔷 Напрямок:         {direction}\n💼 Баланс:           ${balance:,.2f}\n🎯 Ризик:            {risk_percent}%  →  <b>${risk_amount:,.2f}</b>\n📍 Вхід:             ${entry:,.4f}\n🛑 Stop-Loss:        ${stop_loss:,.4f}\n🏆 Take Profit:      <b>${take_profit:,.4f}</b>  (1:2 R:R)\n📏 Ризик на одиницю: ${risk_per_unit:,.2f}\n\n━━━━━━━━━━━━━━━━━━━━\n📦 Розмір позиції:   <b>{position_size:,.6f} units</b>\n💵 Вартість позиції: <b>${position_value:,.2f}</b>\n⚡ Плече:            <b>{leverage}x</b>\n💸 Комісія беззбит.: {breakeven:.3f}%\n\n<i>⚠️ Не є фінансовою порадою.</i>"
    },
    "es": {
        "binance_error": "📡 No se pudo conectar a Binance. Intenta nuevamente.",
        "price_report": "🟡 <b>BTC / USDT</b>  |  Binance Spot\n\n💵 Precio:     <b>${last:,.2f}</b>\n📈 Cambio 24h: {change_sign} {change_pct:.2f}%\n🔺 Máx 24h:    ${high:,.2f}\n🔻 Mín 24h:    ${low:,.2f}\n📦 Volumen:    {volume:,.2f} BTC\n🏷 Bid / Ask:  ${bid:,.2f} / ${ask:,.2f}",
        "manual_risk_report": "⚖️ <b>Reporte de Riesgo (Manual)</b>\n\n🔷 Dirección:        {direction}\n💼 Balance:          ${balance:,.2f}\n🎯 Riesgo:           {risk_percent}%  →  <b>${risk_amount:,.2f}</b>\n📍 Entrada:          ${entry:,.4f}\n🛑 Stop-Loss:        ${stop_loss:,.4f}\n🏆 Take Profit:      <b>${take_profit:,.4f}</b>  (1:2 R:R)\n📏 Riesgo por Uni:   ${risk_per_unit:,.2f}\n\n━━━━━━━━━━━━━━━━━━━━\n📦 Tamaño Posición:  <b>{position_size:,.6f} units</b>\n💵 Valor Posición:   <b>${position_value:,.2f}</b>\n⚡ Apalancamiento:   <b>{leverage}x</b>\n💸 Tarifa Breakeven: {breakeven:.3f}%\n\n<i>⚠️ Sin asesoría financiera.</i>"
    },
    "de": {
        "binance_error": "📡 Binance nicht erreichbar. Überprüfe die Verbindung.",
        "price_report": "🟡 <b>BTC / USDT</b>  |  Binance Spot\n\n💵 Preis:      <b>${last:,.2f}</b>\n📈 24h Update: {change_sign} {change_pct:.2f}%\n🔺 24h Hoch:   ${high:,.2f}\n🔻 24h Tief:   ${low:,.2f}\n📦 Volumen:    {volume:,.2f} BTC\n🏷 Bid / Ask:  ${bid:,.2f} / ${ask:,.2f}",
        "manual_risk_report": "⚖️ <b>Risikomanagement-Bericht (Manuell)</b>\n\n🔷 Richtung:         {direction}\n💼 Guthaben:         ${balance:,.2f}\n🎯 Risiko:           {risk_percent}%  →  <b>${risk_amount:,.2f}</b>\n📍 Einstieg:         ${entry:,.4f}\n🛑 Stop-Loss:        ${stop_loss:,.4f}\n🏆 Take Profit:      <b>${take_profit:,.4f}</b>  (1:2 R:R)\n📏 Risiko/Einheit:   ${risk_per_unit:,.2f}\n\n━━━━━━━━━━━━━━━━━━━━\n📦 Positionsgröße:   <b>{position_size:,.6f} units</b>\n💵 Pos.-Wert:        <b>${position_value:,.2f}</b>\n⚡ Hebel:            <b>{leverage}x</b>\n💸 Breakeven-Gebühr: {breakeven:.3f}%\n\n<i>⚠️ Keine Finanzberatung.</i>"
    },
    "ru": {
        "binance_error": "📡 Не удалось подключиться к Binance. Проверьте соединение.",
        "price_report": "🟡 <b>BTC / USDT</b>  |  Binance Spot\n\n💵 Цена:       <b>${last:,.2f}</b>\n📈 Изм. за 24ч:{change_sign} {change_pct:.2f}%\n🔺 Макс. 24ч:  ${high:,.2f}\n🔻 Мин. 24ч:   ${low:,.2f}\n📦 Объём:      {volume:,.2f} BTC\n🏷 Bid / Ask:  ${bid:,.2f} / ${ask:,.2f}",
        "manual_risk_report": "⚖️ <b>Отчет по Риск-менеджменту (Ручной)</b>\n\n🔷 Направление:      {direction}\n💼 Баланс:           ${balance:,.2f}\n🎯 Риск:             {risk_percent}%  →  <b>${risk_amount:,.2f}</b>\n📍 Вход:             ${entry:,.4f}\n🛑 Stop-Loss:        ${stop_loss:,.4f}\n🏆 Take Profit:      <b>${take_profit:,.4f}</b>  (1:2 R:R)\n📏 Риск на ед.:      ${risk_per_unit:,.2f}\n\n━━━━━━━━━━━━━━━━━━━━\n📦 Размер позиции:   <b>{position_size:,.6f} units</b>\n💵 Стоимость поз.:   <b>${position_value:,.2f}</b>\n⚡ Плечо:            <b>{leverage}x</b>\n💸 Комис. безубыт.:  {breakeven:.3f}%\n\n<i>⚠️ Не является финансовым советом.</i>"
    },
    "fr": {
        "binance_error": "📡 Impossible d'atteindre Binance. Vérifiez votre connexion.",
        "price_report": "🟡 <b>BTC / USDT</b>  |  Binance Spot\n\n💵 Prix :      <b>${last:,.2f}</b>\n📈 24h Chang : {change_sign} {change_pct:.2f}%\n🔺 24h Haut :  ${high:,.2f}\n🔻 24h Bas :   ${low:,.2f}\n📦 Volume :    {volume:,.2f} BTC\n🏷 Bid / Ask:  ${bid:,.2f} / ${ask:,.2f}",
        "manual_risk_report": "⚖️ <b>Rapport de Risque (Manuel)</b>\n\n🔷 Direction :       {direction}\n💼 Solde :           ${balance:,.2f}\n🎯 Risque :          {risk_percent}%  →  <b>${risk_amount:,.2f}</b>\n📍 Entrée :          ${entry:,.4f}\n🛑 Stop-Loss :       ${stop_loss:,.4f}\n🏆 Take Profit :     <b>${take_profit:,.4f}</b>  (1:2 R:R)\n📏 Risque / Unit :   ${risk_per_unit:,.2f}\n\n━━━━━━━━━━━━━━━━━━━━\n📦 Taille Position : <b>{position_size:,.6f} units</b>\n💵 Valeur Position : <b>${position_value:,.2f}</b>\n⚡ Levier :          <b>{leverage}x</b>\n💸 Frais Breakeven : {breakeven:.3f}%\n\n<i>⚠️ Pas un conseil financier.</i>"
    },
    "pl": {
        "binance_error": "📡 Nie można połączyć z Binance. Sprawdź połączenie.",
        "price_report": "🟡 <b>BTC / USDT</b>  |  Binance Spot\n\n💵 Cena:       <b>${last:,.2f}</b>\n📈 Zmiana 24h: {change_sign} {change_pct:.2f}%\n🔺 24h High:   ${high:,.2f}\n🔻 24h Low:    ${low:,.2f}\n📦 Wolumen:    {volume:,.2f} BTC\n🏷 Bid / Ask:  ${bid:,.2f} / ${ask:,.2f}",
        "manual_risk_report": "⚖️ <b>Raport Zarządzania Ryzykiem (Ręczny)</b>\n\n🔷 Kierunek:         {direction}\n💼 Saldo:            ${balance:,.2f}\n🎯 Ryzyko:           {risk_percent}%  →  <b>${risk_amount:,.2f}</b>\n📍 Wejście:          ${entry:,.4f}\n🛑 Stop-Loss:        ${stop_loss:,.4f}\n🏆 Take Profit:      <b>${take_profit:,.4f}</b>  (1:2 R:R)\n📏 Ryzyko/Jedn.:     ${risk_per_unit:,.2f}\n\n━━━━━━━━━━━━━━━━━━━━\n📦 Rozm. Pozycji:    <b>{position_size:,.6f} units</b>\n💵 Wartość Pozycji:  <b>${position_value:,.2f}</b>\n⚡ Dźwignia:         <b>{leverage}x</b>\n💸 Opłata Breakeven: {breakeven:.3f}%\n\n<i>⚠️ To nie jest porada finansowa.</i>"
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
