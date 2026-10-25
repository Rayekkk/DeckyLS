# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026 Rayekkk

"""The FPS counter's window: a transparent X11 window that gamescope draws over games.

It is marked GAMESCOPE_EXTERNAL_OVERLAY and GAMESCOPE_NO_FOCUS, as Steam's own performance overlay (mangoapp) is,
so gamescope shows it on top of the game and never gives it focus or input; its input shape is empty too.
Reads one label per line on stdin and draws it in the top-left corner; an empty line hides the window. Ends when
stdin closes. Runs as its own process with the system python3 (libX11, libXfixes and libcairo through ctypes), so
nothing in it can take the plugin's backend down.
"""

import ctypes
import os
import select
import sys

X = ctypes.CDLL("libX11.so.6")
XF = ctypes.CDLL("libXfixes.so.3")
CAIRO = ctypes.CDLL("libcairo.so.2")
P, UL, D = ctypes.c_void_p, ctypes.c_ulong, ctypes.c_double


class VisualInfo(ctypes.Structure):
    _fields_ = [("visual", P), ("visualid", UL), ("screen", ctypes.c_int), ("depth", ctypes.c_int),
                ("cls", ctypes.c_int), ("red_mask", UL), ("green_mask", UL), ("blue_mask", UL),
                ("colormap_size", ctypes.c_int), ("bits_per_rgb", ctypes.c_int)]


class WindowAttributes(ctypes.Structure):
    _fields_ = [("background_pixmap", UL), ("background_pixel", UL), ("border_pixmap", UL), ("border_pixel", UL),
                ("bit_gravity", ctypes.c_int), ("win_gravity", ctypes.c_int), ("backing_store", ctypes.c_int),
                ("backing_planes", UL), ("backing_pixel", UL), ("save_under", ctypes.c_int),
                ("event_mask", ctypes.c_long), ("do_not_propagate_mask", ctypes.c_long),
                ("override_redirect", ctypes.c_int), ("colormap", UL), ("cursor", UL)]


class TextExtents(ctypes.Structure):
    _fields_ = [(name, D) for name in ("x_bearing", "y_bearing", "width", "height", "x_advance", "y_advance")]


for fn, args, res in (
        (X.XOpenDisplay, [ctypes.c_char_p], P), (X.XDefaultScreen, [P], ctypes.c_int),
        (X.XRootWindow, [P, ctypes.c_int], UL), (X.XDisplayWidth, [P, ctypes.c_int], ctypes.c_int),
        (X.XDisplayHeight, [P, ctypes.c_int], ctypes.c_int),
        (X.XMatchVisualInfo, [P, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.POINTER(VisualInfo)], ctypes.c_int),
        (X.XCreateColormap, [P, UL, P, ctypes.c_int], UL),
        (X.XCreateWindow, [P, UL, ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                           ctypes.c_int, ctypes.c_uint, P, UL, ctypes.POINTER(WindowAttributes)], UL),
        (X.XInternAtom, [P, ctypes.c_char_p, ctypes.c_int], UL),
        (X.XChangeProperty, [P, UL, UL, UL, ctypes.c_int, ctypes.c_int, P, ctypes.c_int], ctypes.c_int),
        (X.XStoreName, [P, UL, ctypes.c_char_p], ctypes.c_int), (X.XMapWindow, [P, UL], ctypes.c_int),
        (X.XUnmapWindow, [P, UL], ctypes.c_int), (X.XFlush, [P], ctypes.c_int),
        (XF.XFixesCreateRegion, [P, P, ctypes.c_int], UL),
        (XF.XFixesSetWindowShapeRegion, [P, UL, ctypes.c_int, ctypes.c_int, ctypes.c_int, UL], None),
        (CAIRO.cairo_xlib_surface_create, [P, UL, P, ctypes.c_int, ctypes.c_int], P),
        (CAIRO.cairo_create, [P], P), (CAIRO.cairo_set_operator, [P, ctypes.c_int], None),
        (CAIRO.cairo_set_source_rgba, [P, D, D, D, D], None), (CAIRO.cairo_paint, [P], None),
        (CAIRO.cairo_new_path, [P], None), (CAIRO.cairo_rectangle, [P, D, D, D, D], None),
        (CAIRO.cairo_arc, [P, D, D, D, D, D], None), (CAIRO.cairo_close_path, [P], None),
        (CAIRO.cairo_fill, [P], None), (CAIRO.cairo_move_to, [P, D, D], None),
        (CAIRO.cairo_select_font_face, [P, ctypes.c_char_p, ctypes.c_int, ctypes.c_int], None),
        (CAIRO.cairo_set_font_size, [P, D], None),
        (CAIRO.cairo_text_extents, [P, ctypes.c_char_p, ctypes.POINTER(TextExtents)], None),
        (CAIRO.cairo_show_text, [P, ctypes.c_char_p], None), (CAIRO.cairo_surface_flush, [P], None)):
    fn.argtypes, fn.restype = args, res

OPERATOR_SOURCE, OPERATOR_OVER, SHAPE_INPUT, PI = 1, 2, 2, 3.141592653589793


class Overlay:
    def __init__(self, display):
        self.d = X.XOpenDisplay(display.encode())
        if not self.d:
            sys.exit(f"cannot open X display {display}")
        screen = X.XDefaultScreen(self.d)
        root = X.XRootWindow(self.d, screen)
        self.w, self.h = X.XDisplayWidth(self.d, screen), X.XDisplayHeight(self.d, screen)
        info = VisualInfo()
        if not X.XMatchVisualInfo(self.d, screen, 32, 4, ctypes.byref(info)):  # 32-bit TrueColor: alpha
            sys.exit("no 32-bit visual")
        attrs = WindowAttributes(colormap=X.XCreateColormap(self.d, root, info.visual, 0))
        # Full screen like mangoapp, transparent everywhere but the label: gamescope fits overlays to the screen.
        self.win = X.XCreateWindow(self.d, root, 0, 0, self.w, self.h, 0, 32, 1, info.visual,
                                   (1 << 13) | (1 << 3) | (1 << 1), ctypes.byref(attrs))
        X.XStoreName(self.d, self.win, b"DeckyLS FPS counter")
        for name in (b"GAMESCOPE_EXTERNAL_OVERLAY", b"GAMESCOPE_NO_FOCUS"):
            one = ctypes.c_long(1)
            X.XChangeProperty(self.d, self.win, X.XInternAtom(self.d, name, 0), 6, 32, 0, ctypes.byref(one), 1)
        XF.XFixesSetWindowShapeRegion(self.d, self.win, SHAPE_INPUT, 0, 0, XF.XFixesCreateRegion(self.d, None, 0))
        self.surface = CAIRO.cairo_xlib_surface_create(self.d, self.win, info.visual, self.w, self.h)
        self.cr = CAIRO.cairo_create(self.surface)
        self.scale = self.h / 800  # sized like Steam's own overlay text on an 800p Deck
        self.mapped = False
        self.box = (0.0, 0.0, 0.0, 0.0)

    def show(self, label):
        cr = self.cr
        CAIRO.cairo_set_operator(cr, OPERATOR_SOURCE)
        CAIRO.cairo_set_source_rgba(cr, 0, 0, 0, 0)
        CAIRO.cairo_new_path(cr)
        CAIRO.cairo_rectangle(cr, *self.box)
        CAIRO.cairo_fill(cr)
        if not label:
            self.box = (0.0, 0.0, 0.0, 0.0)
            CAIRO.cairo_surface_flush(self.surface)
            if self.mapped:
                X.XUnmapWindow(self.d, self.win)  # nothing to show: gamescope need not composite the overlay
                self.mapped = False
            X.XFlush(self.d)
            return
        if not self.mapped:
            X.XMapWindow(self.d, self.win)  # before drawing: mapping clears the window to its background
            self.mapped = True
        text = label.encode()
        s = self.scale
        CAIRO.cairo_select_font_face(cr, b"Noto Sans", 0, 1)
        CAIRO.cairo_set_font_size(cr, 15 * s)
        ext = TextExtents()
        CAIRO.cairo_text_extents(cr, text, ctypes.byref(ext))
        x, y, pad, r = 6 * s, 6 * s, 6 * s, 5 * s
        w, h = ext.x_advance + 2 * pad, 15 * s * 1.35 + pad
        CAIRO.cairo_set_operator(cr, OPERATOR_OVER)
        CAIRO.cairo_set_source_rgba(cr, 0, 0, 0, 0.55)
        CAIRO.cairo_new_path(cr)
        CAIRO.cairo_arc(cr, x + w - r, y + r, r, -PI / 2, 0)
        CAIRO.cairo_arc(cr, x + w - r, y + h - r, r, 0, PI / 2)
        CAIRO.cairo_arc(cr, x + r, y + h - r, r, PI / 2, PI)
        CAIRO.cairo_arc(cr, x + r, y + r, r, PI, 3 * PI / 2)
        CAIRO.cairo_close_path(cr)
        CAIRO.cairo_fill(cr)
        CAIRO.cairo_set_source_rgba(cr, 1, 1, 1, 1)
        CAIRO.cairo_move_to(cr, x + pad, y + h / 2 - (ext.y_bearing + ext.height / 2))
        CAIRO.cairo_show_text(cr, text)
        CAIRO.cairo_surface_flush(self.surface)
        self.box = (0.0, 0.0, x + w + 2, y + h + 2)
        X.XFlush(self.d)


def main():
    overlay = Overlay(os.environ.get("DISPLAY", ":0"))
    stdin = sys.stdin.buffer
    while True:
        select.select([stdin], [], [])
        line = stdin.readline()
        if not line:
            return
        overlay.show(line.decode("utf-8", "replace").strip()[:64])


if __name__ == "__main__":
    main()
