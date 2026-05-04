import os
from modules.db_manager import DatabaseManager

def main():
    print("Testing db_manager.py functionality...")
    db = DatabaseManager()
    
    print(f"Expected DB Path: {db.db_path}")
    
    print("\n--- Initializing DB ---")
    db.init_db()
    
    print("\n--- Initializing Market State ---")
    db.initialize_market_state()
    
    if os.path.exists(db.db_path):
        print("SUCCESS: engine.db was created successfully.")
    else:
        print("ERROR: engine.db was NOT created.")
    
    print("\n--- Testing Signal Insertion ---")
    db.add_signal('BTCUSDT', 'LONG', 64000.5, 68000.0, 62000.0)
    db.add_signal('SOLUSDT', 'SHORT', 145.0, 130.0, 160.0)
    
    active_count = db.get_active_signals_count()
    print(f"Active Signals Count: {active_count}")
    
    print("\n--- Testing Market Data Update ---")
    db.update_market_data('BTCUSDT', 65500.0, 'UPTREND')
    db.update_market_data('SOLUSDT', 147.5, 'DOWNTREND')
    print("Market data updated successfully.")

if __name__ == '__main__':
    main()
