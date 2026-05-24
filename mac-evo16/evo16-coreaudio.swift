// evo16-coreaudio — Set EVO 16 preamp gain via CoreAudio API on macOS
// Build: swiftc -o evo16-coreaudio evo16-coreaudio.swift -framework CoreAudio -framework AudioToolbox
// Run:   ./evo16-coreaudio

import Foundation
import CoreAudio
import AudioToolbox

// MARK: - Helper functions

func fourCC(_ string: String) -> UInt32 {
    let data = string.data(using: .ascii)!
    return UInt32(bigEndian: data.withUnsafeBytes { $0.load(as: UInt32.self) })
}

func getAudioDevices() -> [AudioDeviceID] {
    var propSize: UInt32 = 0
    var propAddr = AudioObjectPropertyAddress(
        mSelector: kAudioHardwarePropertyDevices,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    
    AudioObjectGetPropertyDataSize(
        AudioObjectID(kAudioObjectSystemObject),
        &propAddr, 0, nil, &propSize
    )
    
    let deviceCount = Int(propSize) / MemoryLayout<AudioDeviceID>.size
    var devices = [AudioDeviceID](repeating: 0, count: deviceCount)
    
    AudioObjectGetPropertyData(
        AudioObjectID(kAudioObjectSystemObject),
        &propAddr, 0, nil, &propSize, &devices
    )
    
    return devices
}

func getDeviceName(_ deviceID: AudioDeviceID) -> String {
    var propAddr = AudioObjectPropertyAddress(
        mSelector: kAudioDevicePropertyDeviceName,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    var name: [CChar] = [CChar](repeating: 0, count: 256)
    var propSize = UInt32(name.count)
    
    AudioObjectGetPropertyData(
        deviceID, &propAddr, 0, nil, &propSize, &name
    )
    return String(cString: name)
}

func hasVolumeControl(_ deviceID: AudioDeviceID, scope: AudioObjectPropertyScope, channel: UInt32) -> Bool {
    var propAddr = AudioObjectPropertyAddress(
        mSelector: kAudioDevicePropertyVolumeScalar,
        mScope: scope,
        mElement: channel
    )
    var propSize: UInt32 = 0
    let result = AudioObjectGetPropertyDataSize(deviceID, &propAddr, 0, nil, &propSize)
    return result == noErr
}

func getVolume(_ deviceID: AudioDeviceID, scope: AudioObjectPropertyScope, channel: UInt32) -> Float32? {
    var propAddr = AudioObjectPropertyAddress(
        mSelector: kAudioDevicePropertyVolumeScalar,
        mScope: scope,
        mElement: channel
    )
    var volume: Float32 = 0
    var propSize = UInt32(MemoryLayout<Float32>.size)
    
    let result = AudioObjectGetPropertyData(deviceID, &propAddr, 0, nil, &propSize, &volume)
    guard result == noErr else { return nil }
    return volume
}

func setVolume(_ deviceID: AudioDeviceID, scope: AudioObjectPropertyScope, channel: UInt32, volume: Float32) -> Bool {
    var propAddr = AudioObjectPropertyAddress(
        mSelector: kAudioDevicePropertyVolumeScalar,
        mScope: scope,
        mElement: channel
    )
    var vol = volume
    let result = AudioObjectSetPropertyData(deviceID, &propAddr, 0, nil, UInt32(MemoryLayout<Float32>.size), &vol)
    return result == noErr
}

func hasMuteControl(_ deviceID: AudioDeviceID, scope: AudioObjectPropertyScope, channel: UInt32) -> Bool {
    var propAddr = AudioObjectPropertyAddress(
        mSelector: kAudioDevicePropertyMute,
        mScope: scope,
        mElement: channel
    )
    var propSize: UInt32 = 0
    let result = AudioObjectGetPropertyDataSize(deviceID, &propAddr, 0, nil, &propSize)
    return result == noErr
}

// MARK: - Main

print("=== CoreAudio: EVO 16 Probe ===")
let devices = getAudioDevices()

var evoID: AudioDeviceID = 0

for devID in devices {
    let name = getDeviceName(devID)
    if name.lowercased().contains("evo") || name.lowercased().contains("audient") {
        print("\n🔊 Found: \"\(name)\" (ID: \(devID))")
        evoID = devID
    }
}

guard evoID != 0 else {
    print("❌ EVO 16 not found in CoreAudio devices")
    exit(1)
}

// Probe input volume controls
print("\n--- Input Volume Controls ---")
for ch in 1...10 {
    if hasVolumeControl(evoID, scope: kAudioObjectPropertyScopeInput, channel: UInt32(ch)) {
        if let vol = getVolume(evoID, scope: kAudioObjectPropertyScopeInput, channel: UInt32(ch)) {
            print("  IN\(ch): volume scalar = \(vol) (0.0=silence, 1.0=max)")
        }
    } else {
        print("  IN\(ch): no volume control")
    }
}

// Probe mute controls
print("\n--- Input Mute Controls ---")
for ch in 1...10 {
    if hasMuteControl(evoID, scope: kAudioObjectPropertyScopeInput, channel: UInt32(ch)) {
        print("  IN\(ch): has mute control")
    } else {
        print("  IN\(ch): no mute control")
    }
}

// Output volume controls
print("\n--- Output Volume Controls ---")
for ch in 1...10 {
    if hasVolumeControl(evoID, scope: kAudioObjectPropertyScopeOutput, channel: UInt32(ch)) {
        if let vol = getVolume(evoID, scope: kAudioObjectPropertyScopeOutput, channel: UInt32(ch)) {
            print("  OUT\(ch): volume scalar = \(vol)")
        }
    } else {
        print("  OUT\(ch): no volume control")
    }
}

// Try setting IN1 gain to 13 dB via CoreAudio
// Note: CoreAudio uses scalar 0.0-1.0, but for UAC2 devices it maps to the full range
// We need to convert 13 dB to the scalar range.
// EVO 16 input gain range: 0 dB to 58 dB
// Scalar 0.0 = 0 dB, 1.0 = 58 dB
let targetDB: Float32 = 13.0
let maxDB: Float32 = 58.0
let scalar = targetDB / maxDB

print("\n--- Setting IN1 via CoreAudio ---")
if hasVolumeControl(evoID, scope: kAudioObjectPropertyScopeInput, channel: 1) {
    print("Setting IN1 gain to \(targetDB) dB (scalar: \(scalar))...")
    if setVolume(evoID, scope: kAudioObjectPropertyScopeInput, channel: 1, volume: scalar) {
        print("✅ CoreAudio SET succeeded!")
        // Read back
        if let vol = getVolume(evoID, scope: kAudioObjectPropertyScopeInput, channel: 1) {
            let db = vol * maxDB
            print("   Readback: scalar=\(vol), dB=\(db)")
        }
    } else {
        print("❌ CoreAudio SET failed")
    }
}
