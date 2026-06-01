#!/usr/bin/env python3
"""USB register sniffer — detect changes when INSTR button is pressed on EVO 16.

Captures full entity state, waits for user to press physical INSTR button,
then diffs to find which registers changed.
"""
import subprocess, json, sys, time

HELPER = "/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

def make_helper():
    p = subprocess.Popen([HELPER, "0x2708", "0x000a"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    p.stdout.readline()  # READY
    return p

def cmd(p, js):
    p.stdin.write(json.dumps(js, separators=(',',':')) + "\n")
    p.stdin.flush()
    return json.loads(p.stdout.readline())

def read_entity(p, entity, cs, cn, length=8):
    wValue = (cs << 8) | cn
    r = cmd(p, {"type": "get_cur", "wValue": wValue, "wIndex": entity, "length": length})
    if "data" in r:
        return bytes(r["data"])[:length]
    return None

def snapshot(p, channels=range(1, 25)):
    """Full snapshot of all known entities for all channels."""
    snap = {}
    
    # Entities to scan
    entities = [
        (0x3A00, "EU58"),
        (0x0B00, "FU11"),
        (0x3C00, "MU60"),
        (0x3E00, "EU62"),
        (0x3D00, "EU61"),
        (0x3B00, "EU59"),
    ]
    
    # CS values to scan per entity
    cs_map = {
        0x3A00: [0, 1, 2, 5, 7],    # phantom, gain mirror, mute, instr?, caps
        0x0B00: [2],                  # gain
        0x3C00: [0, 1, 6],           # mixer config
        0x3E00: [0, 1, 3, 6],        # status/heartbeat
        0x3D00: [0, 5],              # alternate
        0x3B00: [0, 1],              # output config  
    }
    
    for ent, name in entities:
        ent_key = f"{name}(0x{ent:04x})"
        snap[ent_key] = {}
        css = cs_map.get(ent, [0, 1, 2, 5])
        for cs in css:
            cs_key = f"CS={cs}"
            snap[ent_key][cs_key] = {}
            for ch in channels:
                cn = ch - 1
                try:
                    val = read_entity(p, ent, cs, cn, 8)
                    if val:
                        snap[ent_key][cs_key][f"CH{ch}"] = val.hex(" ")
                except:
                    pass
    
    return snap

def diff_snaps(before, after):
    changes = []
    for ent in before:
        if ent not in after:
            continue
        for cs in before[ent]:
            if cs not in after[ent]:
                continue
            for ch in before[ent][cs]:
                v1 = before[ent][cs].get(ch)
                v2 = after[ent][cs].get(ch)
                if v1 != v2:
                    changes.append(f"  {ent} {cs} {ch}: {v1} → {v2}")
    return changes

def main():
    print("🔌 Connecting to EVO 16...")
    p = make_helper()
    
    print("📸 Taking BEFORE snapshot...")
    before = snapshot(p)
    print(f"   Captured {sum(len(css) for ent in before.values() for css in ent.values())} register values")
    
    print("\n" + "=" * 60)
    print("🎸  PRESS THE PHYSICAL INSTR BUTTON ON EVO 16 NOW")
    print("    (or type ENTER when done)")
    print("=" * 60)
    input()
    
    print("\n📸 Taking AFTER snapshot...")
    after = snapshot(p)
    
    changes = diff_snaps(before, after)
    
    if changes:
        print(f"\n🔥 DETECTED {len(changes)} CHANGES:")
        for c in changes:
            print(c)
    else:
        print("\n❌ NO CHANGES DETECTED")
        print("\nTrying again with faster loop detection...")
        print("\nPress Ctrl+C when you've toggled INSTR a few times")
        
        # Continuous fast loop monitoring just EU58 CS=0,5,7 for CH1-2
        try:
            last_states = {}
            iteration = 0
            while True:
                iteration += 1
                states = {}
                for ch in [1, 2]:
                    for cs in [0, 5, 7]:
                        cn = ch - 1
                        val = read_entity(p, 0x3A00, cs, cn, 8)
                        key = f"EU58 CS={cs} CH{ch}"
                        states[key] = val.hex(" ") if val else "N/A"
                
                for key, val in states.items():
                    if key in last_states and last_states[key] != val:
                        print(f"\n🔥 CHANGE: {key}: {last_states[key]} → {val}")
                    last_states[key] = val
                
                if iteration % 10 == 0:
                    print(f"  [{iteration}] EU58 CS=5 CH1={states.get('EU58 CS=5 CH1','?')} CH2={states.get('EU58 CS=5 CH2','?')}  CS=7 CH1={states.get('EU58 CS=7 CH1','?')}", end="\r")
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped.")
    
    cmd(p, {"type": "quit"})
    p.stdin.close()
    p.wait()

if __name__ == "__main__":
    main()
