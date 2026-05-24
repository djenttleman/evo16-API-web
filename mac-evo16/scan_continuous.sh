#!/bin/bash
# Continuous EU58 read during knob sweep
# Reads EU58 CS=1 for all 8 channels, 5 times per second

BIN="./mac-evo16"
VID="0x2708"
PID="0x000a"

{
  echo "READY_SIGNAL"
  for i in $(seq 1 80); do
    # Read EU58 CS1 (wValue=256) for all 8 channels
    # EU58 = 0x3A00 = 14848 decimal
    for ch in 0 1 2 3 4 5 6 7; do
      wval=$((256 | ch))
      echo "{\"type\":\"get_cur\",\"wValue\":$wval,\"wIndex\":14848,\"length\":2}"
      sleep 0.02
    done
    echo "---SNAPSHOT $i---"
    sleep 0.15
  done
  echo '{"type":"quit"}'
  sleep 0.1
} | $BIN $VID $PID 2>/dev/null
