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

static const uint32_t background = 0xff21152f;
static const uint32_t panel = 0xff342345;
static const uint32_t subtle = 0xff554369;
static const uint32_t ink = 0xffedf3fb;
static const uint32_t muted = 0xffccbddc;
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

static void rounded_box(Canvas c, unsigned x, unsigned y, unsigned w, unsigned h,
                        unsigned radius, uint32_t color)
{
    box(c, x, y + radius, w, h - 2 * radius, color);
    for (unsigned row = 0; row < radius; ++row) {
        unsigned edge = radius;
        unsigned dy = radius - row - 1;
        while (edge * edge + dy * dy > radius * radius)
            --edge;
        unsigned inset = radius - edge;
        box(c, x + inset, y + row, w - 2 * inset, 1, color);
        box(c, x + inset, y + h - 1 - row, w - 2 * inset, 1, color);
    }
}

static void button(Canvas c, const Dashboard *data, enum button_id id,
                   unsigned x, unsigned y, unsigned width, const char *label, uint32_t color)
{
    bool down = data->sampled && data->buttons[id];
    rounded_box(c, x, y, width, 18, 5, down ? color : 0xff20182e);
    unsigned label_width = (unsigned)strlen(label) * 6 - 1;
    print(c, x + (width - label_width) / 2, y + 6, 1, down ? background : ink, label);
}

static void live_stick(Canvas c, const Dashboard *data, unsigned index, int x, int y)
{
    const uint32_t accent = index ? amber : mint;
    int dx = 0, dy = 0;
    if (data->sampled) {
        dx = ((int)data->axes[2 * index] - 128) * 12 / 128;
        dy = ((int)data->axes[2 * index + 1] - 128) * 12 / 128;
    }
    disc(c, x, y, 27, 0xff6b5a81);
    disc(c, x, y, 24, 0xff1b1428);
    if (dx || dy)
        disc(c, x + dx / 2, y + dy / 2, 13, subtle);
    bool down = data->sampled && data->buttons[index ? R3 : L3];
    disc(c, x + dx, y + dy, 12, accent);
    disc(c, x + dx, y + dy, 9, down ? accent : 0xff403151);
    print(c, x + dx - 5, y + dy - 3, 1, down ? background : ink, index ? "R3" : "L3");
}

static void controller(Canvas c, const Dashboard *data)
{
    /* Shoulder buttons sit behind the two-tone shell and grips. */
    button(c, data, L2, 91, 93, 50, "L2", mint);
    button(c, data, R2, 307, 93, 50, "R2", amber);
    button(c, data, L1, 100, 110, 41, "L1", mint);
    button(c, data, R1, 307, 110, 41, "R1", amber);
    rounded_box(c, 57, 132, 111, 159, 48, 0xff24192f);
    rounded_box(c, 280, 132, 111, 159, 48, 0xff24192f);
    rounded_box(c, 60, 127, 103, 152, 46, 0xff685781);
    rounded_box(c, 285, 127, 103, 152, 46, 0xff685781);
    rounded_box(c, 71, 151, 80, 121, 36, 0xff534568);
    rounded_box(c, 297, 151, 80, 121, 36, 0xff534568);
    rounded_box(c, 86, 126, 276, 109, 38, 0xff77668d);
    rounded_box(c, 94, 136, 260, 93, 31, 0xff635376);
    rounded_box(c, 200, 134, 48, 4, 2, data->sampled ? mint : subtle);

    button(c, data, UP, 121, 147, 24, "UP", mint);
    button(c, data, LEFT, 97, 167, 34, "LEFT", mint);
    button(c, data, RIGHT, 135, 167, 36, "RIGHT", mint);
    button(c, data, DOWN, 116, 187, 34, "DOWN", mint);
    button(c, data, TRIANGLE, 301, 145, 26, "TRI", mint);
    button(c, data, SQUARE, 273, 165, 27, "SQ", 0xffdfa6ed);
    button(c, data, CIRCLE, 329, 165, 27, "O", 0xfff5a4ab);
    button(c, data, CROSS, 301, 186, 26, "X", 0xffb3bdff);
    button(c, data, SELECT, 182, 158, 40, "SELECT", mint);
    button(c, data, START, 227, 158, 38, "START", amber);

    live_stick(c, data, 0, 183, 218);
    live_stick(c, data, 1, 265, 218);
}

static void draw_dashboard(Canvas c, const Dashboard *data)
{
    char line[48];
    for (unsigned y = 0; y < 360; ++y) {
        uint32_t red = 48u - y * 17u / 359u;
        uint32_t green = 28u - y * 11u / 359u;
        uint32_t blue = 75u - y * 23u / 359u;
        box(c, 0, y, 640, 1, 0xff000000u | (red << 16) | (green << 8) | blue);
    }
    print(c, 36, 26, 3, ink, "CONTROLLER TESTER");
    if (data->connected)
        snprintf(line, sizeof(line), "PORT %u", data->port + 1);
    else
        snprintf(line, sizeof(line), "NO CONTROLLER");
    rounded_box(c, 468, 27, 136, 22, 6, panel);
    print(c, 480, 34, 1, data->connected ? mint : amber, line);
    box(c, 36, 64, 568, 1, subtle);

    controller(c, data);
    rounded_box(c, 410, 81, 194, 215, 14, panel);
    for (unsigned i = 0; i < 2; ++i) {
        const unsigned y = 93 + i * 49;
        const uint32_t accent = i ? amber : mint;
        print(c, 424, y, 2, accent, i ? "RIGHT STICK" : "LEFT STICK");
        if (data->sampled)
            snprintf(line, sizeof(line), "X %3u     Y %3u", data->axes[2 * i], data->axes[2 * i + 1]);
        else
            snprintf(line, sizeof(line), "NO INPUT");
        print(c, 424, y + 19, 1, ink, line);
        if (data->drift_done || data->drift_seconds)
            snprintf(line, sizeof(line), "PEAK OFFSET %u", data->drift_peak[i]);
        else
            snprintf(line, sizeof(line), "CENTER 128");
        print(c, 424, y + 31, 1, muted, line);
    }

    box(c, 424, 193, 166, 1, subtle);
    print(c, 424, 205, 2, ink, "TRIGGERS");
    for (unsigned i = 0; i < 2; ++i) {
        const unsigned y = 227 + 28 * i;
        unsigned value = data->triggers[i];
        print(c, 424, y, 1, ink, i ? "R2" : "L2");
        if (!data->sampled)
            snprintf(line, sizeof(line), "NO INPUT");
        else if (data->pressure)
            snprintf(line, sizeof(line), "%u", value);
        else
            snprintf(line, sizeof(line), "%s", value ? "PRESSED" : "RELEASED");
        print(c, 532, y, 1, muted, line);
        box(c, 424, y + 12, 166, 5, subtle);
        if (data->sampled)
            box(c, 424, y + 12, 166 * value / 255, 5, i ? amber : mint);
    }

    box(c, 36, 313, 568, 1, subtle);
    if (data->drift_seconds)
        snprintf(line, sizeof(line), "KEEP STICKS STILL   %u S", data->drift_seconds);
    else if (data->drift_done)
        snprintf(line, sizeof(line), "DRIFT CHECK COMPLETE   SELECT TO REPEAT");
    else
        snprintf(line, sizeof(line), "%s", data->sampled ? "SELECT TO CHECK STICK DRIFT" : "CONNECT A CONTROLLER");
    print(c, 36, 328, 1, mint, line);
    print(c, 471, 328, 1, muted, "HOLD START TO EXIT");
}
#endif
