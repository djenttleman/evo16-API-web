/**
 * evo16-coreaudio — Probe and control EVO 16 via CoreAudio.
 *
 * Build:
 *   cc -o evo16-coreaudio evo16-coreaudio.c -framework CoreAudio -framework AudioToolbox
 */
#include <stdio.h>
#include <string.h>
#include <CoreAudio/CoreAudio.h>

#define EVO_MAX_INPUTS 10

static void print_err(const char *msg, OSStatus err) {
    fprintf(stderr, "%s: %d\n", msg, err);
}

int main(int argc, char **argv) {
    AudioObjectPropertyAddress propAddr;
    UInt32 propSize;
    OSStatus err;

    // 1. Find EVO 16 device
    propAddr.mSelector = kAudioHardwarePropertyDevices;
    propAddr.mScope = kAudioObjectPropertyScopeGlobal;
    propAddr.mElement = kAudioObjectPropertyElementMain;

    err = AudioObjectGetPropertyDataSize(kAudioObjectSystemObject, &propAddr, 0, NULL, &propSize);
    if (err) { print_err("Failed to get device count", err); return 1; }

    int count = propSize / sizeof(AudioDeviceID);
    AudioDeviceID *devices = malloc(propSize);
    err = AudioObjectGetPropertyData(kAudioObjectSystemObject, &propAddr, 0, NULL, &propSize, devices);
    if (err) { print_err("Failed to get device list", err); free(devices); return 1; }

    AudioDeviceID evoID = 0;
    char evoName[256];

    for (int i = 0; i < count; i++) {
        propAddr.mSelector = kAudioDevicePropertyDeviceName;
        propAddr.mScope = kAudioObjectPropertyScopeGlobal;
        propAddr.mElement = kAudioObjectPropertyElementMain;
        char name[256] = {0};
        propSize = sizeof(name);
        err = AudioObjectGetPropertyData(devices[i], &propAddr, 0, NULL, &propSize, name);
        if (err) continue;

        if (strstr(name, "EVO") || strstr(name, "evo") || strstr(name, "Audient")) {
            evoID = devices[i];
            strncpy(evoName, name, 255);
            printf("🔊 Found: \"%s\" (ID=%u)\n", evoName, (unsigned)evoID);
        }
    }

    if (!evoID) {
        printf("❌ EVO 16 not found in CoreAudio\n");
        free(devices);
        return 1;
    }

    // 2. Probe input volume controls
    printf("\n--- Input Volume Controls ---\n");
    for (int ch = 1; ch <= EVO_MAX_INPUTS; ch++) {
        propAddr.mSelector = kAudioDevicePropertyVolumeScalar;
        propAddr.mScope = kAudioObjectPropertyScopeInput;
        propAddr.mElement = ch;

        propSize = 0;
        err = AudioObjectGetPropertyDataSize(evoID, &propAddr, 0, NULL, &propSize);
        if (err || propSize == 0) {
            printf("  IN%d: no volume control\n", ch);
            continue;
        }

        Float32 vol = 0;
        propSize = sizeof(vol);
        err = AudioObjectGetPropertyData(evoID, &propAddr, 0, NULL, &propSize, &vol);
        if (err) {
            printf("  IN%d: can't read volume\n", ch);
            continue;
        }
        // CoreAudio scalar 0.0-1.0 maps to 0-58 dB range
        float db = vol * 58.0f;
        printf("  IN%d: scalar=%.3f (%.1f dB)\n", ch, vol, db);
    }

    // 3. Probe mute controls
    printf("\n--- Input Mute Controls ---\n");
    for (int ch = 1; ch <= EVO_MAX_INPUTS; ch++) {
        propAddr.mSelector = kAudioDevicePropertyMute;
        propAddr.mScope = kAudioObjectPropertyScopeInput;
        propAddr.mElement = ch;

        propSize = 0;
        err = AudioObjectGetPropertyDataSize(evoID, &propAddr, 0, NULL, &propSize);
        if (err || propSize == 0) {
            printf("  IN%d: no mute control\n", ch);
            continue;
        }

        UInt32 muted = 0;
        propSize = sizeof(muted);
        err = AudioObjectGetPropertyData(evoID, &propAddr, 0, NULL, &propSize, &muted);
        if (!err) {
            printf("  IN%d: muted=%d\n", ch, muted);
        }
    }

    // 4. If argument given, set gain
    if (argc > 2 && strcmp(argv[1], "set") == 0) {
        int channel = atoi(argv[2]);
        float db = (float)atof(argv[3]);
        float scalar = db / 58.0f;
        if (scalar < 0) scalar = 0;
        if (scalar > 1) scalar = 1;

        propAddr.mSelector = kAudioDevicePropertyVolumeScalar;
        propAddr.mScope = kAudioObjectPropertyScopeInput;
        propAddr.mElement = channel;

        Float32 vol = scalar;
        propSize = sizeof(vol);
        err = AudioObjectSetPropertyData(evoID, &propAddr, 0, NULL, propSize, &vol);
        if (err) {
            printf("\n❌ CoreAudio SET IN%d to %.1f dB FAILED: %d\n", channel, db, err);
        } else {
            printf("\n✅ CoreAudio SET IN%d to %.1f dB (scalar=%.3f)\n", channel, db, scalar);
            // Readback
            propSize = sizeof(vol);
            err = AudioObjectGetPropertyData(evoID, &propAddr, 0, NULL, &propSize, &vol);
            if (!err) {
                printf("   Readback: scalar=%.3f (%.1f dB)\n", vol, vol * 58.0f);
            }
        }
    }

    // 5. Probe output volume
    printf("\n--- Output Volume ---\n");
    for (int ch = 1; ch <= 10; ch++) {
        propAddr.mSelector = kAudioDevicePropertyVolumeScalar;
        propAddr.mScope = kAudioObjectPropertyScopeOutput;
        propAddr.mElement = ch;
        propSize = 0;
        err = AudioObjectGetPropertyDataSize(evoID, &propAddr, 0, NULL, &propSize);
        if (err || propSize == 0) {
            printf("  OUT%d: no volume control\n", ch);
            continue;
        }
        Float32 vol = 0;
        propSize = sizeof(vol);
        err = AudioObjectGetPropertyData(evoID, &propAddr, 0, NULL, &propSize, &vol);
        if (!err) {
            printf("  OUT%d: scalar=%.3f\n", ch, vol);
        }
    }

    free(devices);
    return 0;
}
