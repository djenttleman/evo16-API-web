#!/bin/bash
# Test: read phantom on CH1, CH9, CH17, then try writing to CH17
HELPER="/Users/djenttleman/dev/evo16-web/mac-evo16/mac-evo16"

echo "=== READ tests (phantom, CS=0) ==="
for ch in 1 9 17; do
  wValue=$(( (0 << 8) | (ch - 1) ))
  payload=$(printf '{"type":"get_cur","wValue":%d,"wIndex":14848,"length":4}' "$wValue")
  echo "CH$ch (wValue=$wValue):"
  echo "$payload" | "$HELPER" 0x2708 0x000a 2>/dev/null
  echo ""
done

echo "=== GAIN reads (CS=1) ==="
for ch in 1 9 17; do
  wValue=$(( (1 << 8) | (ch - 1) ))
  payload=$(printf '{"type":"get_cur","wValue":%d,"wIndex":14848,"length":4}' "$wValue")
  echo "CH$ch (wValue=$wValue):"
  echo "$payload" | "$HELPER" 0x2708 0x000a 2>/dev/null
  echo ""
done

echo "=== WRITE test — set CH17 gain to 25dB ==="
ch=17
wValue=$(( (1 << 8) | (ch - 1) ))
payload=$(printf '{"type":"set_cur","wValue":%d,"wIndex":14848,"data":[0,25,0,0]}' "$wValue")
echo "SET_CH17_GAIN_25:"
echo "$payload" | "$HELPER" 0x2708 0x000a 2>/dev/null
echo ""

echo "=== VERIFY: re-read CH17 gain ==="
wValue=$(( (1 << 8) | 16 ))
payload=$(printf '{"type":"get_cur","wValue":%d,"wIndex":14848,"length":4}' "$wValue")
echo "GET_CH17_GAIN:"
echo "$payload" | "$HELPER" 0x2708 0x000a 2>/dev/null
echo ""
