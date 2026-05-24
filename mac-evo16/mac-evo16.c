/**
 * mac-evo16 v2 — Extended macOS IOKit USB helper for Audient EVO 16.
 *
 * Adds:
 *  - Generic USB control transfers (custom bmRequestType)
 *  - Interrupt endpoint reads (endpoint 0x82 on the Audio Control interface)
 *  - Configuration descriptor dump
 *
 * Protocol: JSON over stdin/stdout
 *
 * Build:
 *   cc -o mac-evo16 mac-evo16.c -framework IOKit -framework CoreFoundation
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <unistd.h>
#include <pthread.h>
#include <mach/mach.h>

#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/usb/IOUSBLib.h>
#include <IOKit/IOCFPlugIn.h>

#if defined(MAC_OS_X_VERSION_10_15) && MAC_OS_X_VERSION_MIN_REQUIRED >= MAC_OS_X_VERSION_12_0
#define IOKIT_MASTER_PORT kIOMainPortDefault
#else
#define IOKIT_MASTER_PORT kIOMasterPortDefault
#endif

/* ------------------------------------------------------------------ */
/*  USB device handles                                                */
/* ------------------------------------------------------------------ */

static IOUSBDeviceInterface **dev_iface = NULL;
static IOUSBInterfaceInterface **intf_iface = NULL; /* for interrupt reads */
static io_service_t usb_service = 0;
static io_service_t intf_service = 0;
static int interrupt_running = 0;

static int open_device(uint16_t vid, uint16_t pid) {
    CFMutableDictionaryRef matching;
    io_iterator_t iter;
    kern_return_t kr;

    matching = IOServiceMatching(kIOUSBDeviceClassName);
    if (!matching) return -1;

    CFNumberRef num;
    uint16_t v = vid;
    num = CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt16Type, &v);
    CFDictionarySetValue(matching, CFSTR(kUSBVendorID), num);
    CFRelease(num);
    v = pid;
    num = CFNumberCreate(kCFAllocatorDefault, kCFNumberSInt16Type, &v);
    CFDictionarySetValue(matching, CFSTR(kUSBProductID), num);
    CFRelease(num);

    kr = IOServiceGetMatchingServices(IOKIT_MASTER_PORT, matching, &iter);
    if (kr != KERN_SUCCESS) return -1;

    usb_service = IOIteratorNext(iter);
    IOObjectRelease(iter);
    if (!usb_service) return -1;

    IOCFPlugInInterface **plugIn = NULL;
    SInt32 score;
    kr = IOCreatePlugInInterfaceForService(usb_service,
        kIOUSBDeviceUserClientTypeID, kIOCFPlugInInterfaceID, &plugIn, &score);
    if (kr != KERN_SUCCESS) { IOObjectRelease(usb_service); return -1; }

    HRESULT res = (*plugIn)->QueryInterface(plugIn,
        CFUUIDGetUUIDBytes(kIOUSBDeviceInterfaceID), (LPVOID *)&dev_iface);
    (*plugIn)->Release(plugIn);
    if (res != S_OK || !dev_iface) { IOObjectRelease(usb_service); return -1; }

    kr = (*dev_iface)->USBDeviceOpen(dev_iface);
    if (kr != KERN_SUCCESS) {
        (*dev_iface)->Release(dev_iface);
        dev_iface = NULL;
        IOObjectRelease(usb_service);
        return -1;
    }
    return 0;
}

static void close_device(void) {
    interrupt_running = 0;
    if (intf_iface) {
        (*intf_iface)->USBInterfaceClose(intf_iface);
        (*intf_iface)->Release(intf_iface);
        intf_iface = NULL;
    }
    if (intf_service) { IOObjectRelease(intf_service); intf_service = 0; }
    if (dev_iface) {
        (*dev_iface)->USBDeviceClose(dev_iface);
        (*dev_iface)->Release(dev_iface);
        dev_iface = NULL;
    }
    if (usb_service) { IOObjectRelease(usb_service); usb_service = 0; }
}

/* ------------------------------------------------------------------ */
/*  Generic USB Control Transfer                                       */
/* ------------------------------------------------------------------ */

static int do_ctrl_xfer(uint8_t bmReqType, uint8_t bReq,
                         uint16_t wValue, uint16_t wIndex,
                         uint8_t *data, uint16_t wLength) {
    if (!dev_iface) return -1;
    IOUSBDevRequest req;
    req.bmRequestType = bmReqType;
    req.bRequest = bReq;
    req.wValue = wValue;
    req.wIndex = wIndex;
    req.wLength = wLength;
    req.pData = data;
    kern_return_t kr = (*dev_iface)->DeviceRequest(dev_iface, &req);
    if (kr != KERN_SUCCESS) return -1;
    return 0;
}

/* ------------------------------------------------------------------ */
/*  Interrupt endpoint read                                            */
/* ------------------------------------------------------------------ */

/* Open the Audio Control interface (Interface 0) for interrupt reads */
static int open_interrupt_interface(void) {
    if (!dev_iface) return -1;

    IOUSBFindInterfaceRequest intfReq;
    intfReq.bInterfaceClass = kIOUSBFindInterfaceDontCare;
    intfReq.bInterfaceSubClass = kIOUSBFindInterfaceDontCare;
    intfReq.bInterfaceProtocol = kIOUSBFindInterfaceDontCare;
    intfReq.bAlternateSetting = kIOUSBFindInterfaceDontCare;

    io_iterator_t iter;
    kern_return_t kr = (*dev_iface)->CreateInterfaceIterator(dev_iface, &intfReq, &iter);
    if (kr != KERN_SUCCESS) return -1;

    int found = 0;
    io_service_t iface_service;
    while ((iface_service = IOIteratorNext(iter)) != 0) {
        IOCFPlugInInterface **plugIn = NULL;
        SInt32 score;
        kr = IOCreatePlugInInterfaceForService(iface_service,
            kIOUSBInterfaceUserClientTypeID, kIOCFPlugInInterfaceID,
            &plugIn, &score);
        if (kr != KERN_SUCCESS) { IOObjectRelease(iface_service); continue; }

        IOUSBInterfaceInterface **iface = NULL;
        HRESULT res = (*plugIn)->QueryInterface(plugIn,
            CFUUIDGetUUIDBytes(kIOUSBInterfaceInterfaceID),
            (LPVOID *)&iface);
        (*plugIn)->Release(plugIn);

        if (res != S_OK || !iface) { IOObjectRelease(iface_service); continue; }

        UInt8 ifNum;
        (*iface)->GetInterfaceNumber(iface, &ifNum);
        if (ifNum == 0) {  /* Audio Control interface */
            intf_iface = iface;
            intf_service = iface_service;
            kr = (*intf_iface)->USBInterfaceOpen(intf_iface);
            if (kr == KERN_SUCCESS) { found = 1; break; }
            (*intf_iface)->Release(intf_iface);
            intf_iface = NULL;
        }
        (*iface)->Release(iface);
        IOObjectRelease(iface_service);
    }
    IOObjectRelease(iter);
    return found ? 0 : -1;
}

/* Try to read interrupt data (returns raw hex string) */
static int do_interrupt_read(uint8_t *buf, uint16_t *len, int timeout_ms) {
    if (!intf_iface) return -1;
    /* Read from endpoint 0x82 (Interrupt IN, endpoint 2) */
    kern_return_t kr = (*intf_iface)->ReadPipeTO(intf_iface, 0x82, buf, len,
                                                   timeout_ms, timeout_ms);
    if (kr != KERN_SUCCESS) return -1;
    return 0;
}

/* ------------------------------------------------------------------ */
/*  Config descriptor dump                                             */
/* ------------------------------------------------------------------ */

static int get_config_descriptor(uint8_t *buf, uint16_t *len) {
    /* GET_DESCRIPTOR: bmReqType=0x80, bReq=0x06, wValue=(0x02<<8)|0 */
    return do_ctrl_xfer(0x80, 0x06, 0x0200, 0, buf, *len);
}

/* ------------------------------------------------------------------ */
/*  JSON protocol                                                      */
/* ------------------------------------------------------------------ */

static void send_json_data(const uint8_t *data, uint16_t length) {
    printf("{\"data\":[");
    for (int i = 0; i < length; i++) {
        if (i > 0) printf(",");
        printf("%d", data[i]);
    }
    printf("]}\n");
    fflush(stdout);
}

static void send_json_ok(void) {
    printf("{\"status\":\"ok\"}\n");
    fflush(stdout);
}

static void send_json_error(const char *msg) {
    printf("{\"error\":\"%s\"}\n", msg);
    fflush(stdout);
}

static int read_line(char *buf, int maxlen) {
    int pos = 0;
    int c;
    while (pos < maxlen - 1) {
        c = getchar();
        if (c == EOF) return -1;
        if (c == '\n') break;
        buf[pos++] = (char)c;
    }
    buf[pos] = '\0';
    return pos;
}

/* Simple JSON field extraction */
static int json_get_int(const char *json, const char *key, int *val) {
    char search[64];
    snprintf(search, sizeof(search), "\"%s\"", key);
    const char *p = strstr(json, search);
    if (!p) return -1;
    p = strchr(p, ':');
    if (!p) return -1;
    while (*p == ':' || *p == ' ' || *p == '\t') p++;
    *val = (int)strtol(p, NULL, 0);
    return 0;
}

static int json_get_bytes(const char *json, const char *key,
                           uint8_t *buf, uint16_t *len, uint16_t max) {
    char search[64];
    snprintf(search, sizeof(search), "\"%s\"", key);
    const char *p = strstr(json, search);
    if (!p) return -1;
    p = strchr(p, '[');
    if (!p) return -1;
    p++;
    int cnt = 0;
    while (*p && *p != ']' && cnt < max) {
        while (*p == ' ' || *p == ',' || *p == '\t') p++;
        if (*p == ']' || *p == '\0') break;
        buf[cnt++] = (uint8_t)strtol(p, (char**)&p, 0);
    }
    *len = cnt;
    return 0;
}

/* ------------------------------------------------------------------ */
/*  Main loop                                                          */
/* ------------------------------------------------------------------ */

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "Usage: %s VID PID\n", argv[0]);
        return 1;
    }

    uint16_t vid = (uint16_t)strtoul(argv[1], NULL, 0);
    uint16_t pid = (uint16_t)strtoul(argv[2], NULL, 0);

    if (open_device(vid, pid) != 0) { return 1; }
    printf("READY\n");
    fflush(stdout);

    char line[8192];
    uint8_t buf[4096];

    while (1) {
        int n = read_line(line, sizeof(line));
        if (n < 0) break;
        if (strcmp(line, "QUIT") == 0 || strcmp(line, "quit") == 0) break;

        char cmd_type[32] = {0};
        json_get_int(line, "wValue", &(int){0});
        json_get_int(line, "wIndex", &(int){0});
        json_get_int(line, "length", &(int){0});

        if (strstr(line, "\"type\":\"ctrl\"")) {
            /* Generic control transfer */
            int bmReqType = 0, bReq = 0, wValue = 0, wIndex = 0, wLength = 0;
            json_get_int(line, "bmReqType", &bmReqType);
            json_get_int(line, "bReq", &bReq);
            json_get_int(line, "wValue", &wValue);
            json_get_int(line, "wIndex", &wIndex);
            json_get_int(line, "length", &wLength);

            uint8_t *data_buf = buf;
            uint16_t data_len = wLength;
            memset(buf, 0, sizeof(buf));

            if (bmReqType & 0x80) { /* IN */
                if (do_ctrl_xfer(bmReqType, bReq, wValue, wIndex, data_buf, data_len) == 0) {
                    send_json_data(data_buf, data_len);
                } else {
                    send_json_error("ctrl_xfer failed");
                }
            } else { /* OUT */
                uint16_t out_len = 0;
                json_get_bytes(line, "data", buf, &out_len, 4096);
                if (do_ctrl_xfer(bmReqType, bReq, wValue, wIndex, buf, out_len) == 0) {
                    send_json_ok();
                } else {
                    send_json_error("ctrl_xfer failed");
                }
            }
        }
        else if (strstr(line, "\"type\":\"get_cur\"")) {
            /* Standard GET_CUR (UAC2): bmReqType=0xA1, bReq=0x01 */
            int wValue = 0, wIndex = 0, wLength = 0;
            json_get_int(line, "wValue", &wValue);
            json_get_int(line, "wIndex", &wIndex);
            json_get_int(line, "length", &wLength);
            memset(buf, 0, sizeof(buf));
            if (do_ctrl_xfer(0xA1, 0x01, wValue, wIndex, buf, wLength) == 0) {
                send_json_data(buf, wLength);
            } else {
                send_json_error("GET_CUR failed");
            }
        }
        else if (strstr(line, "\"type\":\"set_cur\"")) {
            /* Standard SET_CUR (UAC2): bmReqType=0x21, bReq=0x01 */
            int wValue = 0, wIndex = 0;
            uint16_t data_len = 0;
            json_get_int(line, "wValue", &wValue);
            json_get_int(line, "wIndex", &wIndex);
            json_get_bytes(line, "data", buf, &data_len, 4096);
            if (do_ctrl_xfer(0x21, 0x01, wValue, wIndex, buf, data_len) == 0) {
                send_json_ok();
            } else {
                send_json_error("SET_CUR failed");
            }
        }
        else if (strstr(line, "\"type\":\"set_min\"")) {
            /* Standard SET_MIN (UAC2): bmReqType=0x21, bReq=0x02 */
            int wValue = 0, wIndex = 0;
            uint16_t data_len = 0;
            json_get_int(line, "wValue", &wValue);
            json_get_int(line, "wIndex", &wIndex);
            json_get_bytes(line, "data", buf, &data_len, 4096);
            if (do_ctrl_xfer(0x21, 0x02, wValue, wIndex, buf, data_len) == 0) {
                send_json_ok();
            } else {
                send_json_error("SET_MIN failed");
            }
        }
        else if (strstr(line, "\"type\":\"interrupt\"")) {
            /* Read interrupt endpoint */
            uint8_t ibuf[64];
            uint16_t ilen = sizeof(ibuf);
            if (!intf_iface && open_interrupt_interface() != 0) {
                send_json_error("no interrupt interface");
                continue;
            }
            if (do_interrupt_read(ibuf, &ilen, 2000) == 0) {
                send_json_data(ibuf, ilen);
            } else {
                send_json_error("interrupt timeout");
            }
        }
        else if (strstr(line, "\"type\":\"config_desc\"")) {
            /* Dump configuration descriptor */
            memset(buf, 0, sizeof(buf));
            uint16_t desc_len = 4096;
            if (get_config_descriptor(buf, &desc_len) == 0) {
                send_json_data(buf, desc_len);
            } else {
                send_json_error("config_desc failed");
            }
        }
        else {
            send_json_error("unknown type");
        }
    }

    close_device();
    return 0;
}
