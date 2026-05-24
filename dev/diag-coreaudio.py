#!/usr/bin/env python3
"""Diagnostic: probe EVO 16 via CoreAudio AudioObject API."""
import subprocess, plistlib, json

# First, list all audio devices
script = """
tell application "System Preferences"
    -- Use Audio MIDI Setup via terminal
end tell

-- List audio devices via system_profiler
do shell script "system_profiler SPAudioDataType"
"""

# Use Python's CoreAudio bindings via ctypes
import ctypes
import ctypes.util

# Load CoreAudio framework
ca_path = ctypes.util.find_library("CoreAudio")
ca = ctypes.CDLL(ca_path)

# AudioObjectID type
AudioObjectID = ctypes.c_uint32
AudioObjectPropertyAddress = ctypes.c_uint32 * 3

# kAudioObjectSystemObject
kAudioObjectSystemObject = AudioObjectID(1)

# Property selectors
kAudioHardwarePropertyDevices = b'dev#'[0:4]  # 'dev#' as UInt32
kAudioDevicePropertyVolumeScalar = b'vol#'[0:4]  # approximate
kAudioObjectPropertyScopeOutput = b'outp'[0:4]   # 'outp'
kAudioObjectPropertyScopeInput = b'inpt'[0:4]    # 'inpt'
kAudioObjectPropertyElementMain = 0
kAudioObjectPropertyElementWildcard = 0xFFFFFFFF

def fourcc(s):
    """Convert 4-char string to UInt32 fourcc."""
    return int.from_bytes(s.encode('ascii'), 'big')

print("=== CoreAudio: List Audio Devices ===")

# Get number of audio devices
prop_size = ctypes.c_size_t(0)
addr = (AudioObjectPropertyAddress * 1)()
addr[0] = (fourcc('dev#'), 0, 0)  # kAudioHardwarePropertyDevices, kAudioObjectPropertyScopeGlobal, kAudioObjectPropertyElementMain

# First get size
ca.AudioObjectGetPropertyDataSize(
    kAudioObjectSystemObject,
    addr,
    0, None,
    ctypes.byref(prop_size)
)

num_devices = prop_size.value // ctypes.sizeof(AudioObjectID)
print(f"System has {num_devices} audio devices")

# Get device list
devices = (AudioObjectID * num_devices)()
ca.AudioObjectGetPropertyData(
    kAudioObjectSystemObject,
    addr,
    0, None,
    ctypes.byref(prop_size),
    devices
)

for i in range(num_devices):
    dev_id = devices[i]
    
    # Get device name
    name_addr = (AudioObjectPropertyAddress * 1)()
    name_addr[0] = (fourcc('lnam'), 0, 0)  # kAudioDevicePropertyDeviceName
    name_size = ctypes.c_size_t(256)
    name_buf = ctypes.create_string_buffer(256)
    
    try:
        ca.AudioObjectGetPropertyData(
            AudioObjectID(dev_id),
            name_addr,
            0, None,
            ctypes.byref(name_size),
            name_buf
        )
        name = name_buf.value.decode('utf-8').strip('\x00')
        
        if 'EVO' in name or 'audient' in name.lower():
            print(f"\n🔊 FOUND: Device ID={dev_id}, Name='{name}'")
            
            # Check available input channels
            ch_addr = (AudioObjectPropertyAddress * 1)()
            ch_addr[0] = (fourcc('ch#i'), fourcc('inpt'), 0)  # kAudioDevicePropertyStreamConfiguration, Input
            ch_size = ctypes.c_size_t(0)
            ca.AudioObjectGetPropertyDataSize(AudioObjectID(dev_id), ch_addr, 0, None, ctypes.byref(ch_size))
            print(f"  Input channels config size: {ch_size.value}")
            
            # Check volume controls
            vol_addr = (AudioObjectPropertyAddress * 1)()
            vol_addr[0] = (fourcc('mvol'), fourcc('inpt'), 1)  # kAudioDevicePropertyVolumeScalar, Input, ch 1
            vol_size = ctypes.c_size_t(0)
            result = ca.AudioObjectGetPropertyDataSize(AudioObjectID(dev_id), vol_addr, 0, None, ctypes.byref(vol_size))
            print(f"  Volume control exists: {result == 0}, size={vol_size.value}")
            
            # Check mute control
            mute_addr = (AudioObjectPropertyAddress * 1)()
            mute_addr[0] = (fourcc('mute'), fourcc('inpt'), 1)
            mute_size = ctypes.c_size_t(0)
            result = ca.AudioObjectGetPropertyDataSize(AudioObjectID(dev_id), mute_addr, 0, None, ctypes.byref(mute_size))
            print(f"  Mute control exists: {result == 0}")

    except Exception as e:
        print(f"  Device {dev_id}: error getting name: {e}")
