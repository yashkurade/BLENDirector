print("OPERATORS FILE LOADED")

import bpy
import os
import json

from . import asset_cache


# ----------------------------------------------------------
# Asset Folder
# ----------------------------------------------------------

def get_assets_dir():
    addon_dir = os.path.dirname(__file__)
    return os.path.join(addon_dir, "assets")


# ----------------------------------------------------------
# Scan Assets
# ----------------------------------------------------------

def scan_assets():

    asset_cache.clear()

    assets_dir = get_assets_dir()

    if not os.path.exists(assets_dir):
        print("Assets folder not found.")
        return None

    # Scan every folder inside assets
    for category in sorted(os.listdir(assets_dir)):

        category_path = os.path.join(assets_dir, category)

        if not os.path.isdir(category_path):
            continue

        asset_cache[category] = {}

        # Scan every .blend recursively

        for root, dirs, files in os.walk(assets_dir):

            for file in sorted(files):

                if not file.lower().endswith(".blend"):
                    continue

                blend_path = os.path.join(root, file)

                preset_name = os.path.splitext(file)[0]

                metadata_path = os.path.join(root, "preset.json")

                metadata = {}

                if os.path.exists(metadata_path):

                    try:

                        with open(metadata_path, "r", encoding="utf-8") as f:

                            metadata = json.load(f)

                    except Exception as e:

                        print(e)

                # Folder hierarchy relative to assets/
                relative_path = os.path.relpath(root, assets_dir)

                folders = relative_path.split(os.sep)

                node = asset_cache

                # Create nested dictionary automatically
                for folder in folders:

                    node = node.setdefault(folder, {})

                try:

                    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):

                        node[preset_name] = {

                            "blend_path": blend_path,

                            "collections": list(data_from.collections),

                            "metadata": metadata

                        }

                except Exception as e:

                    print(f"Couldn't read {blend_path}")
                    print(e)

    print("\n========== ASSET CACHE ==========")

    for category, presets in asset_cache.items():

        print(category)

        for preset, data in presets.items():

            print("   ", preset)

            for col in data["collections"]:

                print("      -", col)

    print("================================\n")

    return None


# ----------------------------------------------------------
# Refresh
# ----------------------------------------------------------

class BLENDIRECTOR_OT_refresh(bpy.types.Operator):

    bl_idname = "blendirector.refresh"
    bl_label = "Refresh"

    def execute(self, context):

        scan_assets()

        self.report({'INFO'}, "Assets refreshed")

        return {'FINISHED'}


# ----------------------------------------------------------
# Append Collection
# ----------------------------------------------------------

class BLENDIRECTOR_OT_append(bpy.types.Operator):

    bl_idname = "blendirector.append_collection"
    bl_label = "Append Collection"

    blend_path: bpy.props.StringProperty()

    collection_name: bpy.props.StringProperty()

    def execute(self, context):

        selected_obj = context.active_object

        if selected_obj is None:

            self.report({'ERROR'}, "Please select an object first.")
            return {'CANCELLED'}

        blend_path = self.blend_path

        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):

            data_to.collections = [self.collection_name]

        imported = bpy.data.collections.get(self.collection_name)

        if imported is None:

            self.report({'ERROR'}, "Import failed")
            return {'CANCELLED'}

        already_linked = any(
            child.name == imported.name
            for child in context.scene.collection.children
        )

        if not already_linked:

            context.scene.collection.children.link(imported)

        slot = None

        for obj in imported.all_objects:

            if obj.get("blendirector_role") == "product_slot":

                slot = obj
                break

        if slot is None:

            self.report({'ERROR'}, "No product slot found.")
            return {'CANCELLED'}

        selected_obj.location = slot.matrix_world.translation
        selected_obj.rotation_euler = slot.matrix_world.to_euler()

        selected_obj.parent = slot
        selected_obj.matrix_parent_inverse = slot.matrix_world.inverted()

        self.report({'INFO'}, f"Imported {self.collection_name}")

        return {'FINISHED'}


# ----------------------------------------------------------
# Registration
# ----------------------------------------------------------

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