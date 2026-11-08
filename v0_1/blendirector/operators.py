print("OPERATORS FILE LOADED")

import bpy
import os

from . import collection_cache


def get_asset_path():
    addon_dir = os.path.dirname(__file__)
    return os.path.join(addon_dir, "assets", "master.blend")

def scan_collections():

    collection_cache.clear()

    blend_path = get_asset_path()

    if not os.path.exists(blend_path):
        return None

    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        collection_cache.extend(data_from.collections)

        print("Collections:", collection_cache)

        return None


class BLENDIRECTOR_OT_refresh(bpy.types.Operator):
    bl_idname = "blendirector.refresh"
    bl_label = "Refresh"

    def execute(self, context):

        scan_collections()

        self.report({'INFO'}, f"Found {len(collection_cache)} collections")

        return {'FINISHED'}


class BLENDIRECTOR_OT_append(bpy.types.Operator):
    bl_idname = "blendirector.append_collection"
    bl_label = "Append Collection"

    collection_name: bpy.props.StringProperty()

    def execute(self, context):

        blend_path = get_asset_path()

        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
            data_to.collections = [self.collection_name]

        imported = bpy.data.collections.get(self.collection_name)

        if imported is None:
            self.report({'ERROR'}, "Import failed")
            return {'CANCELLED'}

        if imported.name not in context.scene.collection.children:
            context.scene.collection.children.link(imported)

        self.report({'INFO'}, f"Imported {self.collection_name}")

        return {'FINISHED'}


classes = (
    BLENDIRECTOR_OT_refresh,
    BLENDIRECTOR_OT_append,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)