#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# GIMP 3.x plugin to slice the active layer(s) into sub-layers using the guides
# Original GIMP 2.x version (c) Ofnuts 2017
# Adapted for GIMP 3.x / 3.2 (PyGObject / GObject Introspection)
#
#   History:
#
#   v0.0: 2017-04-30 First published version (GIMP 2.x / gimpfu)
#   v3.0: 2026-11-18 Ported to GIMP 3.x / 3.2 (Gimp.PlugIn / Gimp.ImageProcedure)
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation; either version 3 of the License, or
#   (at your option) any later version.
#
#   This very file is the complete source code to the program.
#
#   If you make and redistribute changes to this code, please mark it
#   in reasonable ways as different from the original version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   The GPL v3 licence is available at: https://www.gnu.org/licenses/gpl-3.0.en.html

import sys
import gi

gi.require_version('Gimp', '3.0')
from gi.repository import Gimp
from gi.repository import GLib


def get_guides(image):
    """Collects horizontal and vertical guide positions sorted ascending."""
    h_guides = []
    v_guides = []
    gid = 0
    while True:
        gid = image.find_next_guide(gid)
        if not gid:
            break
        orientation = image.get_guide_orientation(gid)
        position = image.get_guide_position(gid)
        if orientation == Gimp.OrientationType.HORIZONTAL:
            h_guides.append(position)
        elif orientation == Gimp.OrientationType.VERTICAL:
            v_guides.append(position)
    h_guides.sort()
    v_guides.sort()
    return [h_guides, v_guides]


def iterate_segments(positions):
    """Yields successive (start, length) pairs from sorted guide positions."""
    for i in range(len(positions) - 1):
        length = positions[i + 1] - positions[i]
        if length > 0:
            yield positions[i], length


def iterate_squares(image, guides):
    """Yields (x, y, w, h) rectangles defined by image bounds and guides."""
    img_height = image.get_height()
    img_width = image.get_width()
    h_guides = sorted(set([0] + [p for p in guides[0] if 0 < p < img_height] + [img_height]))
    v_guides = sorted(set([0] + [p for p in guides[1] if 0 < p < img_width] + [img_width]))
    for y, h in iterate_segments(h_guides):
        for x, w in iterate_segments(v_guides):
            yield x, y, w, h


def intersect(x1, y1, w1, h1, x2, y2, w2, h2):
    """Returns intersection rectangle (x, y, w, h) or None if disjoint."""
    x1l, x1r, y1t, y1b = x1, x1 + w1, y1, y1 + h1
    x2l, x2r, y2t, y2b = x2, x2 + w2, y2, y2 + h2
    il = max(x1l, x2l)  # left side of intersection
    ir = min(x1r, x2r)  # right side
    it = max(y1t, y2t)  # top (GIMP coordinates)
    ib = min(y1b, y2b)  # bottom
    if ir <= il or ib <= it:
        return None
    return il, it, ir - il, ib - it


def new_layer(image, layer, x, y, w, h):
    """Creates a cropped sub-layer from the intersection of (x, y, w, h) and layer."""
    success, lx, ly = layer.get_offsets()
    if not success:
        lx, ly = 0, 0
    layer_w = layer.get_width()
    layer_h = layer.get_height()
    intersection = intersect(x, y, w, h, lx, ly, layer_w, layer_h)
    if intersection is None:
        return None

    new = layer.copy()
    parent = layer.get_parent()
    image.insert_layer(new, parent, 0)
    new.set_name(f"{layer.get_name()} @ ({x},{y})")
    ix, iy, iw, ih = intersection
    new.resize(iw, ih, lx - ix, ly - iy)
    return new


def guillotine_layer(image, layer):
    """Slices a single Gimp.Layer along image guides and hides the original."""
    guides = get_guides(image)
    for x, y, w, h in iterate_squares(image, guides):
        new_layer(image, layer, x, y, w, h)
    layer.set_visible(False)


class OfnGuillotineLayer(Gimp.PlugIn):
    def do_query_procedures(self):
        return ["ofn-guillotine-layer"]

    def do_create_procedure(self, name):
        if name != "ofn-guillotine-layer":
            return None
        procedure = Gimp.ImageProcedure.new(
            self,
            name,
            Gimp.PDBProcType.PLUGIN,
            self.run,
            None,
        )
        procedure.set_image_types("*")
        procedure.set_menu_label("Guillotine")
        procedure.add_menu_path("<Image>/Layer")
        procedure.set_documentation(
            "Slices the layer into sub-layers using the guides",
            "Slices the active layer(s) into sub-layers using the image guides as division lines. The original layer is kept but made invisible.",
            name,
        )
        procedure.set_attribution("Ofnuts", "Ofnuts", "2017")
        return procedure

    def run(self, procedure, run_mode, image, drawables, config, run_data):
        layers = [d for d in drawables if isinstance(d, Gimp.Layer)]
        if not layers:
            return procedure.new_return_values(
                Gimp.PDBStatusType.CALLING_ERROR,
                GLib.Error("At least one active layer must be selected."),
            )

        image.undo_group_start()
        try:
            for layer in layers:
                guillotine_layer(image, layer)
        finally:
            image.undo_group_end()

        Gimp.displays_flush()
        return procedure.new_return_values(
            Gimp.PDBStatusType.SUCCESS,
            GLib.Error(),
        )


Gimp.main(OfnGuillotineLayer.__gtype__, sys.argv)
