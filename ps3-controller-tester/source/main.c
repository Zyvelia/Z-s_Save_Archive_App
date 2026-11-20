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

#include "dashboard.h"

SYS_PROCESS_PARAM(1001, 0x100000);

static gcmContextData *context;
static videoResolution resolution;
static u32 *buffers[2];
static bool running = true;
static unsigned stride;
static const char *log_path = "/dev_hdd0/game/ZPADT0001/USRDIR/startup.log";

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

static void sysutil_event(u64 status, u64 param, void *user)
{
    (void)param;
    (void)user;
    if (status == SYSUTIL_EXIT_GAME)
        running = false;
}

static unsigned byte_value(unsigned value)
{
    return value <= 255 ? value : 255;
}

static void update_input(Dashboard *data, const padData *report, bool pressure_enabled)
{
    static const unsigned axes[] = {
        PAD_BUTTON_OFFSET_ANALOG_LEFT_X, PAD_BUTTON_OFFSET_ANALOG_LEFT_Y,
        PAD_BUTTON_OFFSET_ANALOG_RIGHT_X, PAD_BUTTON_OFFSET_ANALOG_RIGHT_Y
    };
    static const unsigned masks[BUTTON_COUNT] = {
        PAD_CTRL_UP, PAD_CTRL_DOWN, PAD_CTRL_LEFT, PAD_CTRL_RIGHT,
        PAD_CTRL_TRIANGLE, PAD_CTRL_CIRCLE, PAD_CTRL_CROSS, PAD_CTRL_SQUARE,
        PAD_CTRL_L1, PAD_CTRL_L2, PAD_CTRL_L3, PAD_CTRL_R1, PAD_CTRL_R2, PAD_CTRL_R3,
        PAD_CTRL_SELECT, PAD_CTRL_START
    };
    static const bool second_word[BUTTON_COUNT] = {
        [TRIANGLE]=true, [CIRCLE]=true, [CROSS]=true, [SQUARE]=true,
        [L1]=true, [L2]=true, [R1]=true, [R2]=true
    };
    for (unsigned i = 0; i < BUTTON_COUNT; ++i) {
        const unsigned offset = second_word[i] ? PAD_BUTTON_OFFSET_DIGITAL2 : PAD_BUTTON_OFFSET_DIGITAL1;
        data->buttons[i] = (report->button[offset] & masks[i]) != 0;
    }
    for (unsigned i = 0; i < 4; ++i)
        data->axes[i] = byte_value(report->button[axes[i]]);
    data->pressure = pressure_enabled && report->len > PAD_BUTTON_OFFSET_PRESS_R2;
    data->triggers[0] = data->pressure ? byte_value(report->button[PAD_BUTTON_OFFSET_PRESS_L2])
                                       : (data->buttons[L2] ? 255 : 0);
    data->triggers[1] = data->pressure ? byte_value(report->button[PAD_BUTTON_OFFSET_PRESS_R2])
                                       : (data->buttons[R2] ? 255 : 0);
    data->sampled = true;
}

static int active_port(void)
{
    padInfo2 info = {0};
    if (ioPadGetInfo2(&info) != 0 || (info.info & 1))
        return -1;
    for (unsigned port = 0; port < MAX_PORT_NUM; ++port)
        if ((info.port_status[port] & 1) && info.device_type[port] == PAD_TYPE_STANDARD)
            return (int)port;
    return -1;
}

static void update_drift(Dashboard *data, s64 deadline, s64 now)
{
    for (unsigned stick = 0; stick < 2; ++stick) {
        for (unsigned axis = 0; axis < 2; ++axis) {
            const unsigned value = data->axes[2 * stick + axis];
            const unsigned offset = value >= 128 ? value - 128 : 128 - value;
            if (offset > data->drift_peak[stick])
                data->drift_peak[stick] = offset;
        }
    }
    data->drift_seconds = now < deadline ? (unsigned)((deadline - now + 999999) / 1000000) : 0;
    data->drift_done = now >= deadline;
}

static bool present(unsigned back, const Dashboard *data)
{
    Canvas canvas = {buffers[back], stride, 0, 0, resolution.width, resolution.height};
    const unsigned width = resolution.width;
    const unsigned height = resolution.height;
    if (width * 360 > height * 640)
        canvas.width = height * 640 / 360;
    else
        canvas.height = width * 360 / 640;
    canvas.x = (width - canvas.width) / 2;
    canvas.y = (height - canvas.height) / 2;
    Canvas screen = {buffers[back], stride, 0, 0, width, height};
    if (canvas.y || canvas.x)
        box(screen, 0, 0, 640, 360, background);
    draw_dashboard(canvas, data);
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
    startup_log("Controller Tester 1.1 starting", true);
    if (!init_video() || ioPadInit(MAX_PORT_NUM) != 0)
        return 1;
    if (sysUtilRegisterCallback(SYSUTIL_EVENT_SLOT0, sysutil_event, NULL) != 0) {
        ioPadEnd();
        return 1;
    }

    Dashboard data = {0}, displayed = {0};
    int port = -1;
    s64 drift_deadline = 0, start_pressed = 0, submitted = 0;
    unsigned back = 0;
    bool first = true, pending = false, select_down = false, pressure_enabled = false;
    while (running) {
        sysUtilCheckCallback();
        if (!running)
            break;
        const s64 now = sysGetSystemTime();
        const int connected_port = active_port();
        if (connected_port != port) {
            port = connected_port;
            memset(&data, 0, sizeof(data));
            drift_deadline = start_pressed = 0;
            select_down = false;
            pressure_enabled = false;
            if (port >= 0) {
                data.connected = true;
                data.port = port;
                if (ioPadInfoPressMode(port) > 0)
                    pressure_enabled = ioPadSetPressMode(port, PAD_PRESS_MODE_ON) == 0;
            }
        }

        if (port >= 0) {
            padData report = {0};
            if (ioPadGetData(port, &report) == 0 && report.len > PAD_BUTTON_OFFSET_ANALOG_LEFT_Y)
                update_input(&data, &report, pressure_enabled);

            if (data.sampled) {
                if (data.buttons[START]) {
                    if (!start_pressed)
                        start_pressed = now;
                    if (now - start_pressed >= 1000000)
                        break;
                } else {
                    start_pressed = 0;
                }

                if (data.buttons[SELECT] && !select_down) {
                    data.drift_peak[0] = data.drift_peak[1] = 0;
                    data.drift_done = false;
                    drift_deadline = now + 3000000;
                }
                select_down = data.buttons[SELECT];
                if (drift_deadline && !data.drift_done)
                    update_drift(&data, drift_deadline, now);
            }
        }
        if (pending) {
            if (gcmGetFlipStatus() == 0)
                pending = false;
            else if (now - submitted > 2000000) {
                startup_log("Display flip timed out", false);
                break;
            }
        }
        if (!pending && (first || memcmp(&data, &displayed, sizeof(data)) != 0) &&
            (first || now - submitted >= 30000)) {
            if (!present(back, &data)) {
                startup_log("Could not submit display flip", false);
                break;
            }
            memcpy(&displayed, &data, sizeof(data));
            first = false;
            pending = true;
            back ^= 1;
            submitted = sysGetSystemTime();
        }
        usleep(8000);
    }
    sysUtilUnregisterCallback(SYSUTIL_EVENT_SLOT0);
    ioPadEnd();
    return 0;
}
