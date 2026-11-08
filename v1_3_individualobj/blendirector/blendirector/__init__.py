print("========== BLENDIRECTOR LOADED ==========")

bl_info = {
    "name": "Blendirector",
    "author": "YKreate",
    "version": (1, 0),
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


def set_world_black():

    scene = bpy.context.scene

    if scene is None:
        return

    if scene.world is None:
        scene.world = bpy.data.worlds.new("BLENDIRECTOR_WORLD")

    world = scene.world

    if not world.use_nodes:
        world.use_nodes = True

    bg = world.node_tree.nodes.get("Background")

    if bg is not None:
        bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)


def initial_scan():

    operators.scan_assets()

    set_world_black()

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