import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'bjt_history.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS test_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            device_type TEXT,
            beta_avg REAL,
            beta_max REAL,
            beta_min REAL,
            beta_linearity REAL,
            vce_sat REAL,
            raw_data TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_test_record(device_type, beta_avg, beta_max, beta_min, beta_linearity, vce_sat, raw_data):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO test_records (device_type, beta_avg, beta_max, beta_min, beta_linearity, vce_sat, raw_data)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (device_type, beta_avg, beta_max, beta_min, beta_linearity, vce_sat, json.dumps(raw_data)))
    conn.commit()
    conn.close()

init_db()
