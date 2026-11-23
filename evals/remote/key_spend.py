"""Prints what OpenRouter has billed the eval's key so far (USD), or null; never the key. Runs on
the VPS: python3 - <profile .env> <settle reads>. OpenRouter's count can lag: with settle reads,
it reads until two reads 5 s apart agree (at most that many more reads)."""
import json
import re
import sys
import time
import urllib.request

try:
    env, settle = sys.argv[1], int(sys.argv[2])
    key = re.search(r"""^(?:export\s+)?OPENROUTER_API_KEY=["']?([^"'\s]+)""", open(env).read(), re.M).group(1)
    req = urllib.request.Request("https://openrouter.ai/api/v1/key", headers={"Authorization": "Bearer " + key})
    read = lambda: json.load(urllib.request.urlopen(req, timeout=10))["data"]["usage"]  # noqa: E731
    usage = read()
    for _ in range(settle):
        time.sleep(5)
        last, usage = usage, read()
        if last == usage:
            break
    print(json.dumps(usage))
except Exception:
    print("null")
