"""Prints the job ids her cron ledger has claimed or running, as a JSON list on the last line.
Runs as agent, read-only: python3 -I - <executions.db> (Hermes cron/executions.py's ledger)."""
import json
import sqlite3
import sys

db = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
rows = db.execute("SELECT job_id FROM executions WHERE status IN ('claimed', 'running')")
print(json.dumps([job_id for (job_id,) in rows]))
