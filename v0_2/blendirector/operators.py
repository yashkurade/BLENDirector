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

        # Make sure user has selected an object
        selected_obj = context.active_object

        if selected_obj is None:
            self.report({'ERROR'}, "Please select an object first.")
            return {'CANCELLED'}

        blend_path = get_asset_path()

        # Append the selected collection
        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
            data_to.collections = [self.collection_name]

        # Get imported collection
        imported = bpy.data.collections.get(self.collection_name)

        print("Imported collection:", imported.name)

        print("Objects in collection:")
        for obj in imported.objects:
            print("  ", obj.name, obj.type, list(obj.keys()))

        print("All objects:")
        for obj in imported.all_objects:
            print("  ", obj.name, obj.type, list(obj.keys()))

        if imported is None:
            self.report({'ERROR'}, "Import failed")
            return {'CANCELLED'}

        # Link collection to current scene if not already linked
        already_linked = any(
            child.name == imported.name
            for child in context.scene.collection.children
        )

        if not already_linked:
            context.scene.collection.children.link(imported)

        # Find the product slot
        slot = None

        for obj in imported.all_objects:

            print("--------------------------------")
            print("Object:", obj.name)
            print("Type:", obj.type)
            print("Properties:", list(obj.keys()))

            if obj.get("blendirector_role") == "product_slot":
                print("FOUND PRODUCT SLOT!")
                slot = obj
                break

        if slot is None:
            self.report({'ERROR'}, "No product slot found in preset.")
            return {'CANCELLED'}

        selected_obj.location = slot.matrix_world.translation
        selected_obj.rotation_euler = slot.matrix_world.to_euler()

        selected_obj.parent = slot
        selected_obj.matrix_parent_inverse = slot.matrix_world.inverted()

        self.report({'INFO'}, f"Imported '{self.collection_name}'")

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