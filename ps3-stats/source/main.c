#include <malloc.h>
#include <stdbool.h>
#include <stdio.h>
#include <sys/process.h>
#include <unistd.h>

#include <io/pad.h>
#include <lv2/sysfs.h>
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

static void free_storage(char *value, size_t capacity)
{
    u32 block_size = 0;
    u64 blocks = 0;
    if (sysFsGetFreeSize("/dev_hdd0", &block_size, &blocks) != 0 || block_size == 0) {
        snprintf(value, capacity, "UNAVAILABLE");
        return;
    }
    const u64 mib = ((u64)block_size * blocks) / (1024 * 1024);
    snprintf(value, capacity, "%llu.%u GIB",
             (unsigned long long)(mib / 1024), (unsigned)((mib % 1024) * 10 / 1024));
}

static bool init_video(void)
{
    const u32 io_size = 1024 * 1024;
    void *io = memalign(io_size, io_size);
    videoState state = {0};
    if (!io || rsxInit(&context, 0x10000, io_size, io) != 0 ||
        videoGetState(0, 0, &state) != 0 ||
        videoGetResolution(state.displayMode.resolution, &resolution) != 0)
        return false;

    const u32 pitch = resolution.width * sizeof(u32);
    videoConfiguration config = {0};
    config.resolution = state.displayMode.resolution;
    config.format = VIDEO_BUFFER_FORMAT_XRGB;
    config.pitch = pitch;
    if (videoConfigure(0, &config, NULL, 0) != 0)
        return false;
    gcmSetFlipMode(GCM_FLIP_VSYNC);

    for (unsigned i = 0; i < 2; ++i) {
        u32 offset;
        buffers[i] = rsxMemalign(64, pitch * resolution.height);
        if (!buffers[i] || rsxAddressToOffset(buffers[i], &offset) != 0 ||
            gcmSetDisplayBuffer(i, offset, pitch, resolution.width, resolution.height) != 0)
            return false;
    }
    return true;
}

static void rectangle(u32 *buffer, unsigned x, unsigned y, unsigned width,
                      unsigned height, u32 color)
{
    for (unsigned row = y; row < y + height && row < resolution.height; ++row)
        for (unsigned col = x; col < x + width && col < resolution.width; ++col)
            buffer[row * resolution.width + col] = color;
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

static void draw_stats(u32 *buffer)
{
    char values[3][32];
    temperature(0, values[0], sizeof(values[0]));
    temperature(1, values[1], sizeof(values[1]));
    free_storage(values[2], sizeof(values[2]));

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
    text(buffer, x, h * 84 / 100, scale, 0xffc4cfe0, "CIRCLE TO EXIT");
}

static void sysutil_event(u64 status, u64 param, void *user)
{
    (void)param;
    (void)user;
    if (status == SYSUTIL_EXIT_GAME)
        running = false;
}

static bool exit_pressed(void)
{
    padInfo info = {0};
    if (ioPadGetInfo(&info) != 0)
        return false;
    for (unsigned i = 0; i < MAX_PADS; ++i) {
        padData data = {0};
        if (info.status[i] && ioPadGetData(i, &data) == 0 && data.len && data.BTN_CIRCLE)
            return true;
    }
    return false;
}

int main(void)
{
    if (!init_video() || ioPadInit(MAX_PADS) != 0)
        return 1;
    if (sysUtilRegisterCallback(SYSUTIL_EVENT_SLOT0, sysutil_event, NULL) != 0) {
        ioPadEnd();
        return 1;
    }

    unsigned back = 0;
    s64 last_update = 0;
    bool first_flip = true;
    while (running) {
        sysUtilCheckCallback();
        if (!running || exit_pressed())
            break;
        s64 now = sysGetSystemTime();
        if (first_flip || now - last_update >= 1000000) {
            if (first_flip || gcmGetFlipStatus() == 0) {
                draw_stats(buffers[back]);
                __asm__ volatile ("sync" ::: "memory");
                gcmResetFlipStatus();
                if (gcmSetFlip(context, back) != 0)
                    break;
                rsxFlushBuffer(context);
                back ^= 1;
                first_flip = false;
                last_update = now;
            }
        }
        usleep(20000);
    }

    sysUtilUnregisterCallback(SYSUTIL_EVENT_SLOT0);
    ioPadEnd();
    return 0;
}
