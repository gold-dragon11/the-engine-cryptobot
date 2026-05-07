import re

with open('main.py', 'r') as f:
    content = f.read()

# 1. Update imports
content = re.sub(r'from modules\.risk_manager import.*', 'from modules.risk_manager import calculate_trade_risk', content)
content = re.sub(r'from modules\.profile_manager import.*?\n', '', content)

# 2. Update _lang
content = re.sub(r'def _lang\(user_id: int\) -> str:.*?return prof\.get\("language", "en"\)', 'def _lang(user_id: int) -> str:\n    return db.get_user_language(user_id)', content, flags=re.DOTALL)

# 3. Update /start
new_start = """async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    from modules.i18n import LANGUAGE_NAMES
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(LANGUAGE_NAMES["en"], callback_data="setlang_en"),
            InlineKeyboardButton(LANGUAGE_NAMES["uk"], callback_data="setlang_uk"),
        ],
        [
            InlineKeyboardButton(LANGUAGE_NAMES["es"], callback_data="setlang_es"),
            InlineKeyboardButton(LANGUAGE_NAMES["de"], callback_data="setlang_de"),
        ],
        [
            InlineKeyboardButton(LANGUAGE_NAMES["ru"], callback_data="setlang_ru"),
            InlineKeyboardButton(LANGUAGE_NAMES["fr"], callback_data="setlang_fr"),
        ],
        [
            InlineKeyboardButton(LANGUAGE_NAMES["pl"], callback_data="setlang_pl"),
        ],
    ])
    
    await update.message.reply_text(
        "Please select your language / Будь ласка, оберіть мову:",
        reply_markup=keyboard,
    )"""
content = re.sub(r'async def start.*?await update\.message\.reply_html\(welcome_text, reply_markup=keyboard\)', new_start, content, flags=re.DOTALL)

# 4. Update language_callback
new_lang_cb = """async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    lang_code = query.data.replace("setlang_", "")
    from modules.i18n import LANGUAGE_NAMES
    if lang_code not in LANGUAGE_NAMES:
        return

    uid = query.from_user.id
    db.set_user_language(uid, lang_code)
    logger.info("User %d set language to '%s'", uid, lang_code)

    await query.edit_message_text(
        "🐉 Систему активовано. Фонове сканування ринку розпочато..."
    )"""
content = re.sub(r'async def language_callback.*?i18n\.get\("language_set", lang=lang_code, language=LANGUAGE_NAMES\[lang_code\]\)\n    \)', new_lang_cb, content, flags=re.DOTALL)

# 5. Remove Profile Management commands, stats, guide, price, risk, analyze
# They span from `# ── Profile Management ──` to `# ── Background Streams ──`
content = re.sub(r'# ── Profile Management ───────────────────────────────────────.*?# ── Background Streams ─────────────────────────────────────────', '# ── Background Streams ─────────────────────────────────────────', content, flags=re.DOTALL)

# 6. Update Watcher loop
# Look for dynamic risk calculation and replace with calculate_trade_risk
watcher_risk_old = r'''                        if mkt_structure\.atr_14:.*?except Exception as e:.*?logger\.warning\(f"Watcher dynamic risk calc error for \{coin\}: \{e\}"\)'''
watcher_risk_new = r'''                        if mkt_structure.atr_14:
                            try:
                                dyn_result = calculate_trade_risk(
                                    entry_price=current_price,
                                    support=mkt_structure.support,
                                    resistance=mkt_structure.resistance,
                                    atr_14=mkt_structure.atr_14,
                                    ai_direction=sentiment.direction
                                )
                            except Exception as e:
                                logger.warning(f"Watcher dynamic risk calc error for {coin}: {e}")'''
content = re.sub(watcher_risk_old, watcher_risk_new, content, flags=re.DOTALL)

# 7. Update Watcher message building (signal output template)
watcher_msg_old = r'''                        msg \+= f"\{i18n\.get\('watcher\.triggered', coin=coin\)\}\\n".*?logger\.warning\(f"No ADMIN_CHAT_ID found in config\. Cannot send alert for \{coin\}\."\)'''
watcher_msg_new = r'''                        
                        if dyn_result:
                            signal_data = {
                                "ticker": coin,
                                "type": sentiment.direction,
                                "entry_price": dyn_result.entry_price,
                                "sl": dyn_result.stop_loss,
                                "tp": dyn_result.take_profit,
                                "rr_ratio": dyn_result.rr_ratio,
                                "comment": sentiment.reasoning
                            }
                            
                            from modules.notifier import send_signal_alert
                            if config.ADMIN_CHAT_ID:
                                send_signal_alert(signal_data)
                            else:
                                logger.warning(f"No ADMIN_CHAT_ID found in config. Cannot send alert for {coin}.")'''
content = re.sub(watcher_msg_old, watcher_msg_new, content, flags=re.DOTALL)

# Also remove msg generation before `if dyn_result:`
content = re.sub(r'''                        from modules\.i18n import i18n\s+msg = f"\{i18n\.get\('watcher\.signal_header'\)\}\\n\\n"\s+''', '', content)

# 8. Remove removed commands from add_handler
content = re.sub(r'    app\.add_handler\(CommandHandler\("price",    price_command\)\)\n', '', content)
content = re.sub(r'    app\.add_handler\(CommandHandler\("risk",     risk_command\)\)\n', '', content)
content = re.sub(r'    app\.add_handler\(CommandHandler\("analyze",  analyze_command\)\)\n', '', content)
content = re.sub(r'    app\.add_handler\(CommandHandler\("set_balance", set_balance_command\)\)\n', '', content)
content = re.sub(r'    app\.add_handler\(CommandHandler\("set_risk", set_risk_command\)\)\n', '', content)
content = re.sub(r'    app\.add_handler\(CommandHandler\("settings", settings_command\)\)\n', '', content)
content = re.sub(r'    app\.add_handler\(CommandHandler\("stats",    stats_command\)\)\n', '', content)
content = re.sub(r'    app\.add_handler\(CommandHandler\("guide",    guide_command\)\)\n', '', content)
content = re.sub(r'    app\.add_handler\(CommandHandler\("academy",  guide_command\)\)\n', '', content)

with open('main.py', 'w') as f:
    f.write(content)
