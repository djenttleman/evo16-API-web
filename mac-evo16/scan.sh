#!/bin/bash
# Quick scan of all EVO16 UAC2 entities that respond
# Usage: ./scan.sh > result.json

BIN="./mac-evo16"
VID="0x2708"
PID="0x000a"

{
  # FU10 - Output Volume (entity 10 = 0x0A00)
  for cs in 256 512; do  # CS=1 (mute), CS=2 (volume)
    for ch in 1 2 3 4 5 6 7 8; do
      echo "{\"type\":\"get_cur\",\"wValue\":$((cs | (ch-1))),\"wIndex\":2560,\"length\":2}"
      sleep 0.05
    done
  done
  
  # FU11 - Input Gain (entity 11 = 0x0B00)
  for cs in 256 512; do
    for ch in 1 2 3 4 5 6 7 8; do
      echo "{\"type\":\"get_cur\",\"wValue\":$((cs | (ch-1))),\"wIndex\":2816,\"length\":2}"
      sleep 0.05
    done
  done
  
  # FU12 - entity 12 = 0x0C00
  for cs in 256 512; do
    for ch in 1 2; do
      echo "{\"type\":\"get_cur\",\"wValue\":$((cs | (ch-1))),\"wIndex\":3072,\"length\":2}"
      sleep 0.05
    done
  done

  # FU13 - entity 13 = 0x0D00
  for cs in 256 512; do
    for ch in 1 2; do
      echo "{\"type\":\"get_cur\",\"wValue\":$((cs | (ch-1))),\"wIndex\":3328,\"length\":2}"
      sleep 0.05
    done
  done

  # EU58 - Phantom/Mute (entity 58 = 0x3A00)
  for cs in 256 512; do
    for ch in 1 2 3 4 5 6 7 8; do
      echo "{\"type\":\"get_cur\",\"wValue\":$((cs | (ch-1))),\"wIndex\":14848,\"length\":2}"
      sleep 0.05
    done
  done

  # EU59 - Output Mute (entity 59 = 0x3B00)
  for cs in 256 512; do
    for ch in 1 2 3 4; do
      echo "{\"type\":\"get_cur\",\"wValue\":$((cs | (ch-1))),\"wIndex\":15104,\"length\":2}"
      sleep 0.05
    done
  done

  echo '{"type":"quit"}'
  sleep 0.3
} | $BIN $VID $PID 2>/dev/null
