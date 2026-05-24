#!/bin/bash
# Brute-force vendor OUT requests to find the preamp control command
# Tries all bRequest 0-255 with bmReqType=0x41 through DFU interface

BIN="./mac-evo16"

{
  for bReq in $(seq 0 255); do
    # Vendor OUT: bmReqType=0x41 (host→dev, vendor, interface)
    # Try with no data, just the command
    echo "{\"type\":\"ctrl\",\"bmReqType\":65,\"bReq\":$bReq,\"wValue\":256,\"wIndex\":0,\"length\":0}"
    sleep 0.02
  done
  
  # Read EU58 ch1 after all attempts
  echo '{"type":"get_cur","wValue":256,"wIndex":14848,"length":2}'
  sleep 0.3
  echo '{"type":"quit"}'
} | $BIN 0x2708 0x000a 2>/dev/null | grep -v READY | grep -v 'unknown type'
