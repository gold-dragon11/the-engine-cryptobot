import os
import sqlite3
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        # Resolve the path dynamically relative to the root directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(current_dir)
        data_dir = os.path.join(root_dir, 'data')
        
        # Ensure data dir exists
        os.makedirs(data_dir, exist_ok=True)
        
        self.db_path = os.path.join(data_dir, 'engine.db')
        
    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=10)

    def init_db(self):
        """Creates tables if they do not exist and handles migrations."""
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                type TEXT,
                entry_price REAL,
                tp1 REAL,
                tp2 REAL,
                tp3 REAL,
                sl REAL,
                timestamp DATETIME,
                status TEXT,
                tp1_hit INTEGER DEFAULT 0,
                start_time DATETIME,
                close_time DATETIME,
                pnl REAL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS market_state (
                ticker TEXT UNIQUE,
                current_price REAL,
                trend_direction TEXT,
                last_updated DATETIME
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                language TEXT DEFAULT 'en',
                is_active INTEGER DEFAULT 0
            )
        ''')
        
        # Simple migration: Add missing columns if they don't exist
        cursor.execute("PRAGMA table_info(signals)")
        columns = [info[1] for info in cursor.fetchall()]
        
        missing_columns = {
            "tp1": "REAL",
            "tp2": "REAL",
            "tp3": "REAL",
            "tp1_hit": "INTEGER DEFAULT 0",
            "start_time": "DATETIME",
            "close_time": "DATETIME",
            "pnl": "REAL"
        }
        
        for col, col_type in missing_columns.items():
            if col not in columns:
                try:
                    cursor.execute(f"ALTER TABLE signals ADD COLUMN {col} {col_type}")
                    logger.info(f"DB Migration: Added column '{col}' to 'signals' table.")
                except Exception as e:
                    logger.error(f"Migration error column {col}: {e}")

        cursor.execute("PRAGMA table_info(users)")
        user_columns = [info[1] for info in cursor.fetchall()]
        if "is_active" not in user_columns:
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 0")
                logger.info("DB Migration: Added column 'is_active' to 'users' table.")
            except Exception as e:
                logger.error(f"Migration error column is_active: {e}")

        cursor.execute("PRAGMA journal_mode=WAL;")
        conn.commit()
        conn.close()

    def initialize_market_state(self):
        """Pre-populates the market_state table with default tickers."""
        tickers = ['BTCUSDT', 'SOLUSDT', 'TAOUSDT', 'ONDOUSDT', 'RENDERUSDT', 'PEPEUSDT', 'TONUSDT']
        conn = self._connect()
        cursor = conn.cursor()
        
        for ticker in tickers:
            cursor.execute('''
                INSERT OR IGNORE INTO market_state (ticker, current_price, trend_direction, last_updated)
                VALUES (?, ?, ?, ?)
            ''', (ticker, 0.0, 'UNKNOWN', datetime.now()))
            
        conn.commit()
        conn.close()

    def add_signal(self, ticker, type, entry, tp1, tp2, tp3, sl):
        """Inserts a new signal with status 'PENDING'."""
        conn = self._connect()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO signals (ticker, type, entry_price, tp1, tp2, tp3, sl, timestamp, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (ticker, type, entry, tp1, tp2, tp3, sl, datetime.now(), 'PENDING'))
        
        conn.commit()
        conn.close()

    def update_market_price(self, ticker, price):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE market_state SET current_price = ?, last_updated = ? WHERE ticker = ?
        ''', (price, datetime.now(), ticker))
        conn.commit()
        conn.close()

    def update_market_trend(self, ticker, trend):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE market_state SET trend_direction = ?, last_updated = ? WHERE ticker = ?
        ''', (trend, datetime.now(), ticker))
        conn.commit()
        conn.close()

    def get_user_language(self, user_id: int) -> str:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else "en"

    def set_user_language(self, user_id: int, language: str):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, language) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET language = excluded.language
        ''', (user_id, language))
        conn.commit()
        conn.close()

    def is_bot_activated(self) -> bool:
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0

    def activate_user(self, user_id: int):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, language, is_active) VALUES (?, 'en', 1)
            ON CONFLICT(user_id) DO UPDATE SET is_active = 1
        ''', (user_id,))
        conn.commit()
        conn.close()

    def reset_all_activations(self):
        """Reset all users to inactive state. Called on bot startup for clean dormant boot."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 0")
        conn.commit()
        conn.close()
        logger.info("DB: All user activations reset. Bot is now dormant.")

    def get_market_prices(self):
        """Returns a dict of ticker -> price."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT ticker, current_price FROM market_state")
        rows = cursor.fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}

    def get_active_signals_count(self):
        """Count only non-closed signals."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals WHERE status IN ('PENDING', 'ACTIVE')")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_signals_by_status(self, status):
        conn = self._connect()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM signals WHERE status = ?", (status,))
        rows = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def update_signal_status(self, signal_id, status, start_time=None, close_time=None, pnl=None):
        conn = self._connect()
        cursor = conn.cursor()
        if start_time:
            cursor.execute("UPDATE signals SET status = ?, start_time = ? WHERE id = ?", (status, start_time, signal_id))
        elif close_time:
            cursor.execute("UPDATE signals SET status = ?, close_time = ?, pnl = ? WHERE id = ?", (status, close_time, pnl, signal_id))
        else:
            cursor.execute("UPDATE signals SET status = ? WHERE id = ?", (status, signal_id))
        conn.commit()
        conn.close()

    def mark_tp1_hit(self, signal_id, new_sl):
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("UPDATE signals SET tp1_hit = 1, sl = ? WHERE id = ?", (new_sl, signal_id))
        conn.commit()
        conn.close()

    def get_stats(self):
        """Returns overall performance stats."""
        conn = self._connect()
        cursor = conn.cursor()
        
        # Win rate
        cursor.execute("SELECT COUNT(*) FROM signals WHERE status = 'CLOSED'")
        total = cursor.fetchone()[0]
        if total == 0:
            conn.close()
            return {"win_rate": 0, "total_pnl": 0, "best_coin": "N/A"}
            
        cursor.execute("SELECT COUNT(*) FROM signals WHERE status = 'CLOSED' AND pnl > 0")
        wins = cursor.fetchone()[0]
        win_rate = (wins / total) * 100
        
        # Total PnL
        cursor.execute("SELECT SUM(pnl) FROM signals WHERE status = 'CLOSED'")
        total_pnl = cursor.fetchone()[0] or 0.0
        
        # Best coin
        cursor.execute("SELECT ticker, SUM(pnl) as coin_pnl FROM signals WHERE status = 'CLOSED' GROUP BY ticker ORDER BY coin_pnl DESC LIMIT 1")
        best = cursor.fetchone()
        best_coin = best[0] if best else "N/A"
        
        conn.close()
        return {
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "best_coin": best_coin
        }
    def has_active_trade(self, ticker):
        """Перевіряє, чи є активна угода по тикеру (PENDING або ACTIVE)."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM signals WHERE ticker = ? AND status IN ('PENDING', 'ACTIVE')", (ticker,))
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
