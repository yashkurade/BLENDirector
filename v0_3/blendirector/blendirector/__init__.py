print("========== BLENDIRECTOR LOADED ==========")

bl_info = {
    "name": "Blendirector",
    "author": "YKreate",
    "version": (0, 3),
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


def register():
    operators.register()
    ui.register()

    # Scan assets once after Blender finishes loading
    bpy.app.timers.register(
        operators.scan_assets,
        first_interval=1.0
    )


def unregister():
    ui.unregister()
    operators.unregister()