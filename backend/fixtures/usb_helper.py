#!/usr/bin/env python3
"""Explicit test fixture, never selected in production. Does not open USB."""
import os
import json
import sys

if os.environ.get("EVO16_FIXTURE_OFFLINE") == "1":
    print("ERROR DEVICE_NOT_FOUND", flush=True)
    sys.exit(1)

registers = {}
print('READY', flush=True)
for line in sys.stdin:
    if line.strip() == 'quit': break
    command = json.loads(line)
    key = (command.get('wIndex'), command.get('wValue'))
    if command['type'] == 'set_cur':
        registers[key] = command['data']
        result = {'status': 'ok'}
    else:
        length = command.get('length', 4)
        value = registers.get(key)
        if value is None:
            if key == (0x3600, 18 << 8): value = [0, 236]  # -20 dB Q8.8
            elif key == (0x2800, 1 << 8): value = [1]
            elif key[0] == 0x3A00 and key[1] >> 8 == 1: value = [0, 8, 0, 0]  # 0 dB
            else: value = [0] * length
        result = {'data': value}
    print(json.dumps(result), flush=True)
