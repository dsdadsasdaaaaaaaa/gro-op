"""Run by the Supervisor right before it backs up /data: fold SQLite's write-ahead log into the main file,
so the backup holds a clean, complete database even though Grow Brain keeps running."""
import sqlite3
import sys

try:
    c = sqlite3.connect("/data/grow_brain.sqlite", timeout=10)
    c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    c.close()
except Exception as e:  # never block a backup
    print(f"checkpoint skipped: {e}", file=sys.stderr)
