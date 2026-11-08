print("========== BLENDIRECTOR LOADED ==========")

bl_info = {
    "name": "Blendirector",
    "author": "YKreate",
    "version": (0, 2),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar",
    "description": "Dynamic Collection Importer",
    "category": "Object",
}

import bpy

collection_cache = []

from . import operators, ui


def register():
    operators.register()
    ui.register()

    bpy.app.timers.register(operators.scan_collections, first_interval=1)


def unregister():
    ui.unregister()
    operators.unregister()