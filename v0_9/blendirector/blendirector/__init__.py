print("========== BLENDIRECTOR LOADED ==========")

bl_info = {
    "name": "Blendirector",
    "author": "YKreate",
    "version": (0, 9),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar",
    "description": "Dynamic Collection Importer",
    "category": "Object",
}

import bpy

# Dynamic asset cache
#
# Structure:
#
# asset_cache = {
#     "Camera": {
#         "Studio": {
#             "blend_path": ".../assets/Camera/Studio.blend",
#             "collections": ["Hero", "Close", "Top"]
#         },
#         "Luxury": {
#             "blend_path": ".../Luxury.blend",
#             "collections": [...]
#         }
#     },
#
#     "Lighting": {
#         "Softbox": {
#             ...
#         }
#     }
# }

asset_cache = {}

from . import operators
from . import ui


def initial_scan():

    operators.scan_assets()

    scene = bpy.context.scene

    if scene is not None:

        from . import ui
        ui.rebuild_browser_items(scene)

    return None


def register():
    operators.register()
    ui.register()

    bpy.app.timers.register(
        initial_scan,
        first_interval=1.0
    )


def unregister():
    ui.unregister()
    operators.unregister()