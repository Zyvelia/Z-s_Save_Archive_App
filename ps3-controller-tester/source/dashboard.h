#ifndef CONTROLLER_DASHBOARD_H
#define CONTROLLER_DASHBOARD_H

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../../ps3-stats/source/font.h"

enum button_id {
    UP, DOWN, LEFT, RIGHT, TRIANGLE, CIRCLE, CROSS, SQUARE,
    L1, L2, L3, R1, R2, R3, SELECT, START, BUTTON_COUNT
};

typedef struct {
    uint32_t *pixels;
    unsigned stride;
    unsigned x, y, width, height;
} Canvas;

typedef struct {
    bool connected, sampled, pressure;
    unsigned port;
    unsigned axes[4], triggers[2];
    bool buttons[BUTTON_COUNT];
    unsigned drift_peak[2], drift_seconds;
    bool drift_done;
} Dashboard;

static const uint32_t background = 0xff101723;
static const uint32_t panel = 0xff1b2636;
static const uint32_t subtle = 0xff344458;
static const uint32_t ink = 0xffedf3fb;
static const uint32_t muted = 0xffb1c3d8;
static const uint32_t mint = 0xff8ce9c7;
static const uint32_t amber = 0xffffca85;

static void box(Canvas c, unsigned x, unsigned y, unsigned w, unsigned h, uint32_t color)
{
    unsigned left = c.x + x * c.width / 640;
    unsigned right = c.x + (x + w) * c.width / 640;
    unsigned top = c.y + y * c.height / 360;
    unsigned bottom = c.y + (y + h) * c.height / 360;
    for (unsigned row = top; row < bottom; ++row) {
        uint32_t *line = c.pixels + row * c.stride;
        for (unsigned col = left; col < right; ++col)
            line[col] = color;
    }
}

static void print(Canvas c, unsigned x, unsigned y, unsigned scale, uint32_t color, const char *text)
{
    for (; *text; ++text, x += 6 * scale) {
        unsigned ch = (unsigned char)*text;
        if (ch < 32 || ch > 'Z')
            continue;
        for (unsigned row = 0; row < 7; ++row)
            for (unsigned col = 0; col < 5; ++col)
                if (font[ch - 32][row] & (16u >> col))
                    box(c, x + col * scale, y + row * scale, scale, scale, color);
    }
}

static void disc(Canvas c, int x, int y, int radius, uint32_t color)
{
    for (int row = -radius; row <= radius; ++row) {
        int edge = radius;
        while (edge * edge + row * row > radius * radius)
            --edge;
        box(c, x - edge, y + row, 2 * edge + 1, 1, color);
    }
}

static void stick(Canvas c, const Dashboard *data, unsigned index, unsigned x)
{
    const unsigned axis_x = data->axes[index * 2];
    const unsigned axis_y = data->axes[index * 2 + 1];
    const uint32_t accent = index ? amber : mint;
    char value[32];

    box(c, x, 80, 274, 122, panel);
    box(c, x, 80, 274, 2, accent);
    print(c, x + 12, 94, 2, ink, index ? "RIGHT STICK" : "LEFT STICK");
    disc(c, x + 52, 151, 34, subtle);
    disc(c, x + 52, 151, 32, background);
    box(c, x + 22, 151, 61, 1, subtle);
    box(c, x + 52, 121, 1, 61, subtle);
    if (data->sampled)
        disc(c, x + 22 + axis_x * 60 / 255, 121 + axis_y * 60 / 255, 4, accent);

    if (data->sampled)
        snprintf(value, sizeof(value), "X %3u   Y %3u", axis_x, axis_y);
    else
        snprintf(value, sizeof(value), "NO INPUT");
    print(c, x + 102, 133, 2, ink, value);
    if (data->drift_done || data->drift_seconds) {
        snprintf(value, sizeof(value), "PEAK OFFSET %u", data->drift_peak[index]);
        print(c, x + 102, 162, 1, accent, value);
    } else {
        print(c, x + 102, 162, 1, muted, "CENTER 128");
    }
}

static void draw_dashboard(Canvas c, const Dashboard *data)
{
    static const char *names[BUTTON_COUNT] = {
        "UP", "DOWN", "LEFT", "RIGHT", "TRIANGLE", "CIRCLE", "CROSS", "SQUARE",
        "L1", "L2", "L3", "SELECT", "R1", "R2", "R3", "START"
    };
    static const enum button_id order[] = {
        UP, DOWN, LEFT, RIGHT, TRIANGLE, CIRCLE, CROSS, SQUARE,
        L1, L2, L3, SELECT, R1, R2, R3, START
    };
    char status[48];
    box(c, 0, 0, 640, 360, background);
    print(c, 40, 26, 3, ink, "CONTROLLER TESTER");
    if (data->connected)
        snprintf(status, sizeof(status), "PORT %u", data->port + 1);
    else
        snprintf(status, sizeof(status), "NO CONTROLLER");
    box(c, 469, 27, 131, 20, panel);
    print(c, 479, 33, 1, data->connected ? mint : amber, status);
    print(c, 40, 58, 1, muted, "LIVE INPUT");
    box(c, 40, 71, 560, 1, subtle);

    stick(c, data, 0, 40);
    stick(c, data, 1, 326);
    box(c, 40, 212, 328, 101, panel);
    box(c, 380, 212, 220, 101, panel);
    print(c, 52, 221, 2, ink, "BUTTONS");
    for (unsigned i = 0; i < BUTTON_COUNT; ++i) {
        unsigned x = 52 + (i % 4) * 77;
        unsigned y = 240 + (i / 4) * 16;
        bool pressed = data->sampled && data->buttons[order[i]];
        box(c, x, y, 69, 13, pressed ? mint : subtle);
        print(c, x + 6, y + 3, 1, pressed ? background : ink, names[i]);
    }

    print(c, 392, 221, 2, ink, "TRIGGERS");
    for (unsigned i = 0; i < 2; ++i) {
        const unsigned y = 243 + 31 * i;
        const unsigned value = data->triggers[i];
        const uint32_t accent = i ? amber : mint;
        print(c, 392, y, 1, ink, i ? "R2" : "L2");
        if (!data->sampled)
            snprintf(status, sizeof(status), "NO INPUT");
        else if (data->pressure)
            snprintf(status, sizeof(status), "%u", value);
        else
            snprintf(status, sizeof(status), "%s", value ? "PRESSED" : "RELEASED");
        print(c, 505, y, 1, muted, status);
        box(c, 392, y + 11, 196, 6, subtle);
        if (data->sampled)
            box(c, 392, y + 11, 196 * value / 255, 6, accent);
    }

    if (data->drift_seconds)
        snprintf(status, sizeof(status), "KEEP STICKS STILL   %u S", data->drift_seconds);
    else if (data->drift_done)
        snprintf(status, sizeof(status), "DRIFT CHECK COMPLETE   SELECT TO REPEAT");
    else
        snprintf(status, sizeof(status), "%s", data->sampled ? "SELECT TO CHECK STICK DRIFT" : "CONNECT A CONTROLLER");
    print(c, 40, 329, 1, mint, status);
    print(c, 467, 329, 1, muted, "HOLD START TO EXIT");
}
#endif
