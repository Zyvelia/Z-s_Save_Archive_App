#include <malloc.h>
#include <stdbool.h>
#include <stdio.h>
#include <sys/process.h>
#include <unistd.h>

#include <io/pad.h>
#include <lv2/systime.h>
#include <rsx/rsx.h>
#include <sysutil/sysutil.h>
#include <sysutil/video.h>

#include "font.h"

SYS_PROCESS_PARAM(1001, 0x100000);

static gcmContextData *context;
static videoResolution resolution;
static u32 *buffers[2];
static bool running = true;
static unsigned stride;
static const char *log_path = "/dev_hdd0/game/ZSTATS001/USRDIR/startup.log";

static void startup_log(const char *message, bool reset)
{
    FILE *log = fopen(log_path, reset ? "w" : "a");
    if (log) {
        fprintf(log, "%s\n", message);
        fclose(log);
    }
}

static bool wait_rsx_ready(void)
{
    const unsigned label_index = 255;
    volatile u32 *label = gcmGetLabelAddress(label_index);
    if (!label)
        return false;
    *label = 0;
    rsxSetWriteBackendLabel(context, label_index, 1);
    rsxFlushBuffer(context);
    for (unsigned poll = 0; poll < 200; ++poll) {
        if (*label == 1)
            return true;
        usleep(5000);
    }
    return false;
}

static s32 read_temperature_word(u32 sensor, u32 *word)
{
    /* CFW LV2 get_temperature. The high byte is degrees Celsius. */
    lv2syscall2(383, sensor, (u32)(u64)word);
    return_to_user_prog(s32);
}

static void temperature(u32 sensor, char *value, size_t capacity)
{
    u32 word = 0;
    s32 result = read_temperature_word(sensor, &word);
    u32 degrees = word >> 24;
    if (result == 0 && degrees > 0 && degrees <= 125)
        snprintf(value, capacity, "%u C", (unsigned)degrees);
    else
        snprintf(value, capacity, "UNAVAILABLE");
}

static bool init_video(void)
{
    const u32 alignment = 1024 * 1024;
    const u32 io_size = 32 * alignment;
    void *io = memalign(alignment, io_size);
    videoState state = {0};
    if (!io || rsxInit(&context, alignment, io_size, io) != 0 || !context) {
        startup_log("RSX initialization failed", false);
        return false;
    }
    if (videoGetState(0, 0, &state) != 0 ||
        videoGetResolution(state.displayMode.resolution, &resolution) != 0 ||
        !resolution.width || !resolution.height) {
        startup_log("Could not read the display mode", false);
        return false;
    }
    if (!wait_rsx_ready()) {
        startup_log("RSX initialization fence timed out", false);
        return false;
    }

    const u32 pitch = (resolution.width * sizeof(u32) + 63) & ~63u;
    stride = pitch / sizeof(u32);
    videoConfiguration config = {0};
    config.resolution = state.displayMode.resolution;
    config.aspect = state.displayMode.aspect;
    config.format = VIDEO_BUFFER_FORMAT_XRGB;
    config.pitch = pitch;
    if (videoConfigure(0, &config, NULL, 0) != 0) {
        startup_log("Video configuration failed", false);
        return false;
    }
    gcmSetFlipMode(GCM_FLIP_VSYNC);

    for (unsigned i = 0; i < 2; ++i) {
        u32 offset;
        buffers[i] = rsxMemalign(64, pitch * resolution.height);
        if (!buffers[i] || rsxAddressToOffset(buffers[i], &offset) != 0 ||
            gcmSetDisplayBuffer(i, offset, pitch, resolution.width, resolution.height) != 0) {
            startup_log("Display buffer registration failed", false);
            return false;
        }
    }
    return true;
}

static void rectangle(u32 *buffer, unsigned x, unsigned y, unsigned width,
                      unsigned height, u32 color)
{
    for (unsigned row = y; row < y + height && row < resolution.height; ++row)
        for (unsigned col = x; col < x + width && col < resolution.width; ++col)
            buffer[row * stride + col] = color;
}

static void text(u32 *buffer, unsigned x, unsigned y, unsigned scale,
                 u32 color, const char *label)
{
    for (; *label; ++label, x += 6 * scale) {
        unsigned ch = (unsigned char)*label;
        if (ch < 32 || ch > 'Z')
            continue;
        for (unsigned row = 0; row < 7; ++row)
            for (unsigned col = 0; col < 5; ++col)
                if (font[ch - 32][row] & (16u >> col))
                    rectangle(buffer, x + col * scale, y + row * scale, scale, scale, color);
    }
}

static void draw_stats(u32 *buffer, char values[3][32], bool sensors_enabled)
{
    const char *labels[] = {"CELL TEMPERATURE", "RSX TEMPERATURE", "FREE INTERNAL STORAGE"};
    const unsigned w = resolution.width;
    const unsigned h = resolution.height;
    const unsigned x = w / 10;
    const unsigned scale = h / 160 ? h / 160 : 1;
    rectangle(buffer, 0, 0, w, h, 0xff101621);
    text(buffer, x, h / 9, scale + 2, 0xffa8e8cf, "PS3 STATS");
    for (unsigned i = 0; i < 3; ++i) {
        unsigned y = h * (25 + 17 * i) / 100;
        rectangle(buffer, x, y, w - 2 * x, h * 14 / 100, 0xff202c3c);
        text(buffer, x + w / 40, y + h / 50, scale, 0xffc4cfe0, labels[i]);
        text(buffer, x + w / 40, y + h * 8 / 100, scale + 1, 0xffffffff, values[i]);
    }
    if (!sensors_enabled)
        text(buffer, x, h * 81 / 100, scale, 0xffa8e8cf, "CROSS TO ENABLE TEMPERATURES");
    text(buffer, x, h * 88 / 100, scale, 0xffc4cfe0, "CIRCLE TO EXIT");
}

static void sysutil_event(u64 status, u64 param, void *user)
{
    (void)param;
    (void)user;
    if (status == SYSUTIL_EXIT_GAME)
        running = false;
}

static bool read_buttons(bool screen_ready, bool *enable_temperatures)
{
    static bool cross_released[MAX_PADS];
    padInfo info = {0};
    if (ioPadGetInfo(&info) != 0)
        return false;
    for (unsigned i = 0; i < MAX_PADS; ++i) {
        padData data = {0};
        if (info.status[i] && ioPadGetData(i, &data) == 0 && data.len) {
            if (data.BTN_CIRCLE)
                return true;
            if (screen_ready && !data.BTN_CROSS)
                cross_released[i] = true;
            else if (screen_ready && cross_released[i])
                *enable_temperatures = true;
        }
    }
    return false;
}

static bool present(unsigned back, char values[3][32], bool sensors_enabled)
{
    draw_stats(buffers[back], values, sensors_enabled);
    __asm__ volatile ("sync" ::: "memory");
    gcmResetFlipStatus();
    if (gcmSetFlip(context, back) != 0)
        return false;
    gcmSetWaitFlip(context);
    rsxFlushBuffer(context);
    return true;
}

int main(void)
{
    startup_log("PS3 Stats 1.2 starting", true);
    if (!init_video() || ioPadInit(MAX_PADS) != 0)
        return 1;
    if (sysUtilRegisterCallback(SYSUTIL_EVENT_SLOT0, sysutil_event, NULL) != 0) {
        startup_log("Could not register XMB exit callback", false);
        ioPadEnd();
        return 1;
    }

    char values[3][32] = {"PAUSED", "PAUSED", "UNAVAILABLE"};
    unsigned front = 0;
    bool sensors_enabled = false;
    bool first_temperature = true;
    bool pending = present(front, values, sensors_enabled);
    s64 submitted = sysGetSystemTime();
    s64 last_update = 0;
    bool first_read = true;
    if (!pending) {
        startup_log("First display flip could not be submitted", false);
        running = false;
    }
    while (running) {
        sysUtilCheckCallback();
        if (!running || read_buttons(!first_read, &sensors_enabled))
            break;

        s64 now = sysGetSystemTime();
        if (pending) {
            if (gcmGetFlipStatus() == 0)
                pending = false;
            else if (now - submitted > 2000000) {
                startup_log("Display flip timed out", false);
                break;
            }
        }
        if (!pending && (first_read || (sensors_enabled && first_temperature) ||
                         now - last_update >= 1000000)) {
            if (sensors_enabled) {
                if (first_temperature)
                    startup_log("Reading CELL temperature", false);
                temperature(0, values[0], sizeof(values[0]));
                if (first_temperature)
                    startup_log("Reading RSX temperature", false);
                temperature(1, values[1], sizeof(values[1]));
                if (first_temperature)
                    startup_log("Initial temperature readings finished", false);
                first_temperature = false;
            }
            if (first_read)
                startup_log("First display flip completed", false);
            first_read = false;
            front ^= 1;
            if (!present(front, values, sensors_enabled)) {
                startup_log("Display flip could not be submitted", false);
                break;
            }
            pending = true;
            submitted = sysGetSystemTime();
            last_update = submitted;
        }
        usleep(20000);
    }

    sysUtilUnregisterCallback(SYSUTIL_EVENT_SLOT0);
    ioPadEnd();
    return 0;
}
