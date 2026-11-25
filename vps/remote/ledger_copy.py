"""A consistent copy of her cron ledger, read-only on the original. Runs as agent:
python3 -I - <executions.db> <copy> (Hermes cron/executions.py's ledger)."""
import os
import sqlite3
import sys

src = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
dst = sqlite3.connect(sys.argv[2])
os.chmod(sys.argv[2], 0o600)  # the other user on the host has no business reading it
src.backup(dst)
dst.close()
print(src.execute("SELECT COUNT(*) FROM executions WHERE status IN ('claimed', 'running')").fetchone()[0])
