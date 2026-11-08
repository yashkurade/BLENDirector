print("OPERATORS FILE LOADED")

import bpy
import os
import json
import sys
import subprocess

from . import asset_cache

# ----------------------------------------------------------
# Timeline
# ----------------------------------------------------------

class BLENDIRECTOR_PG_timeline_item(bpy.types.PropertyGroup):

    preset_name: bpy.props.StringProperty()

    blend_path: bpy.props.StringProperty()

    category: bpy.props.StringProperty()

    duration: bpy.props.IntProperty(
        default=90,
        min=1
    )

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

                preview_path = None

                for f in files:

                    if f.lower().endswith(".mp4"):

                        preview_path = os.path.join(root, f)
                        break

                try:

                    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):

                        node[preset_name] = {

                            "blend_path": blend_path,

                            "collections": list(data_from.collections),

                            "metadata": metadata,

                            "preview_path": preview_path

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


class BLENDIRECTOR_OT_preview_video(bpy.types.Operator):

    bl_idname = "blendirector.preview_video"
    bl_label = "Preview"
    bl_description = "Play the preview video for this preset"

    video_path: bpy.props.StringProperty()

    def execute(self, context):

        if not self.video_path or not os.path.exists(self.video_path):

            self.report({'ERROR'}, "Preview video not found.")
            return {'CANCELLED'}

        try:

            if sys.platform.startswith("win"):
                os.startfile(self.video_path)

            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.video_path])

            else:
                subprocess.Popen(["xdg-open", self.video_path])

        except Exception as e:

            self.report({'ERROR'}, f"Could not open video: {e}")
            return {'CANCELLED'}

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
# Add Preset To Timeline
# ----------------------------------------------------------

class BLENDIRECTOR_OT_add_to_timeline(bpy.types.Operator):

    bl_idname = "blendirector.add_to_timeline"
    bl_label = "Add To Timeline"

    blend_path: bpy.props.StringProperty()
    preset_name: bpy.props.StringProperty()
    category: bpy.props.StringProperty()

    def execute(self, context):

        item = context.scene.blendirector_timeline.add()

        item.preset_name = self.preset_name
        item.blend_path = self.blend_path
        item.category = self.category

        # Read duration from preset metadata
        duration = 90

        for node in asset_cache.values():

            if not isinstance(node, dict):
                continue

        # Search asset cache for matching preset
        def find_preset(node):

            if not isinstance(node, dict):
                return None

            for name, value in node.items():

                if isinstance(value, dict) and "blend_path" in value:

                    if value["blend_path"] == self.blend_path:
                        return value

                elif isinstance(value, dict):

                    result = find_preset(value)

                    if result:
                        return result

            return None

        preset = find_preset(asset_cache)

        if preset:
            metadata = preset.get("metadata", {})
            item.duration = int(metadata.get("duration", 90))

        self.report(
            {'INFO'},
            f"Added '{self.preset_name}' to timeline"
        )

        return {'FINISHED'}

# ----------------------------------------------------------
# Remove Timeline Item
# ----------------------------------------------------------

class BLENDIRECTOR_OT_remove_from_timeline(bpy.types.Operator):

    bl_idname = "blendirector.remove_from_timeline"
    bl_label = "Remove"

    index: bpy.props.IntProperty()

    def execute(self, context):

        timeline = context.scene.blendirector_timeline

        if self.index < len(timeline):

            timeline.remove(self.index)

        return {'FINISHED'}

# ----------------------------------------------------------
# Move Timeline Item Up
# ----------------------------------------------------------

class BLENDIRECTOR_OT_move_timeline_up(bpy.types.Operator):

    bl_idname = "blendirector.move_timeline_up"
    bl_label = "Move Up"

    index: bpy.props.IntProperty()

    def execute(self, context):

        timeline = context.scene.blendirector_timeline

        if self.index > 0:

            timeline.move(
                self.index,
                self.index - 1
            )

        return {'FINISHED'}       

# ----------------------------------------------------------
# Move Timeline Item Down
# ----------------------------------------------------------

class BLENDIRECTOR_OT_move_timeline_down(bpy.types.Operator):

    bl_idname = "blendirector.move_timeline_down"
    bl_label = "Move Down"

    index: bpy.props.IntProperty()

    def execute(self, context):

        timeline = context.scene.blendirector_timeline

        if self.index < len(timeline) - 1:

            timeline.move(
                self.index,
                self.index + 1
            )

        return {'FINISHED'}

def find_product_slot(collections):

    for collection in collections:

        for obj in collection.all_objects:

            if obj.get("blendirector_role") == "product_slot":

                return obj

    return None

def find_camera_recursive(obj):

    if obj.type == 'CAMERA':
        return obj

    for child in obj.children:

        camera = find_camera_recursive(child)

        if camera:
            return camera

    return None


def find_scene_camera(collections):

    scene_cameras = []

    for collection in collections:

        for obj in collection.all_objects:

            if obj.get("blendirector_role") == "scene_camera":

                scene_cameras.append(obj)

    # No camera rig
    if len(scene_cameras) == 0:
        return None, "No scene camera found."

    # More than one camera rig
    if len(scene_cameras) > 1:
        return None, "Multiple scene cameras found."

    # Exactly one
    camera = find_camera_recursive(scene_cameras[0])

    if camera is None:
        return None, "Scene camera rig has no camera."

    return camera, None

def set_product_visibility(obj, start_frame, end_frame):

    # Before shot
    obj.hide_viewport = True
    obj.hide_render = True

    obj.keyframe_insert(
        data_path="hide_viewport",
        frame=start_frame - 1
    )

    obj.keyframe_insert(
        data_path="hide_render",
        frame=start_frame - 1
    )

    # Shot starts
    obj.hide_viewport = False
    obj.hide_render = False

    obj.keyframe_insert(
        data_path="hide_viewport",
        frame=start_frame
    )

    obj.keyframe_insert(
        data_path="hide_render",
        frame=start_frame
    )

    # Shot ends
    obj.hide_viewport = False
    obj.hide_render = False

    obj.keyframe_insert(
        data_path="hide_viewport",
        frame=end_frame
    )

    obj.keyframe_insert(
        data_path="hide_render",
        frame=end_frame
    )

    # After shot
    obj.hide_viewport = True
    obj.hide_render = True

    obj.keyframe_insert(
        data_path="hide_viewport",
        frame=end_frame + 1
    )

    obj.keyframe_insert(
        data_path="hide_render",
        frame=end_frame + 1
    )

def set_shot_objects_visibility(collection, start_frame, end_frame):

    objects = list(collection.all_objects)

    for obj in objects:

        # --------------------------------------------------
        # DO NOT animate cameras or empties
        # Cameras are controlled by timeline markers.
        # Empties may be camera/product parents.
        # --------------------------------------------------

        if obj.type in {'CAMERA', 'EMPTY'}:
            continue

        # --------------------------------------------------
        # Hidden before shot
        # --------------------------------------------------

        obj.hide_render = True
        obj.keyframe_insert(
            data_path="hide_render",
            frame=start_frame - 1
        )

        # --------------------------------------------------
        # Visible during shot
        # --------------------------------------------------

        obj.hide_render = False
        obj.keyframe_insert(
            data_path="hide_render",
            frame=start_frame
        )

        obj.keyframe_insert(
            data_path="hide_render",
            frame=end_frame
        )

        # --------------------------------------------------
        # Hidden after shot
        # --------------------------------------------------

        obj.hide_render = True
        obj.keyframe_insert(
            data_path="hide_render",
            frame=end_frame + 1
        )

def update_shot_viewport_visibility(scene):

    # Find Blendirector commercial root
    root = bpy.data.collections.get("BLENDIRECTOR_COMMERCIAL")

    if root is None:
        return

    current_frame = scene.frame_current

    # Check every shot collection
    for shot_collection in root.children:

        # Only process our SHOT collections
        if not shot_collection.name.startswith("SHOT_"):
            continue

        start_frame = shot_collection.get("blendirector_start")
        end_frame = shot_collection.get("blendirector_end")

        if start_frame is None or end_frame is None:
            continue

        # Is this the currently active shot?
        visible = (
            start_frame <= current_frame <= end_frame
        )

        # Show/hide every object belonging to this shot
        for obj in shot_collection.all_objects:
            obj.hide_set(not visible)

def offset_object_animation(obj, offset):

    animation = obj.animation_data

    if animation is None:
        return

    # ------------------------------------------------------
    # Active Action
    # ------------------------------------------------------

    if animation.action:

        action = animation.action.copy()

        for fcurve in action.fcurves:

            for keyframe in fcurve.keyframe_points:

                keyframe.co.x += offset
                keyframe.handle_left.x += offset
                keyframe.handle_right.x += offset

        animation.action = action

    # ------------------------------------------------------
    # NLA
    # ------------------------------------------------------

    for track in animation.nla_tracks:

        for strip in track.strips:

            strip.frame_start += offset
            strip.frame_end += offset

class BLENDIRECTOR_OT_generate_commercial(bpy.types.Operator):

    bl_idname = "blendirector.generate_commercial"
    bl_label = "Generate Commercial"

    def execute(self, context):

        timeline = context.scene.blendirector_timeline

        # --------------------------------------------------
        # Validation
        # --------------------------------------------------

        if len(timeline) == 0:

            self.report(
                {'ERROR'},
                "Timeline is empty."
            )

            return {'CANCELLED'}

        selected_obj = context.active_object

        if selected_obj is None:

            self.report(
                {'ERROR'},
                "Please select your product first."
            )

            return {'CANCELLED'}

        scene = context.scene

        # --------------------------------------------------
        # Remove previous generated commercial
        # --------------------------------------------------

        old_root = bpy.data.collections.get(
            "BLENDIRECTOR_COMMERCIAL"
        )

        if old_root:

            for child in list(old_root.children):
                bpy.data.collections.remove(
                    child,
                    do_unlink=True
                )

            for obj in list(old_root.objects):
                bpy.data.objects.remove(
                    obj,
                    do_unlink=True
                )

            bpy.data.collections.remove(
                old_root
            )

        # --------------------------------------------------
        # Create generated root collection
        # --------------------------------------------------

        root = bpy.data.collections.new(
            "BLENDIRECTOR_COMMERCIAL"
        )

        scene.collection.children.link(root)

        # --------------------------------------------------
        # Remove old Blendirector camera markers
        # --------------------------------------------------

        for marker in list(scene.timeline_markers):

            if marker.name.startswith("BD_SCENE_"):

                scene.timeline_markers.remove(marker)

        # --------------------------------------------------
        # Timeline generation
        # --------------------------------------------------

        current_frame = 1

        total_frames = 0

        for index, item in enumerate(timeline):

            self.report(
                {'INFO'},
                f"Generating Scene {index + 1}: {item.preset_name}"
            )

            # ==========================================================
            # LOAD PRESET COLLECTIONS
            # ==========================================================

            with bpy.data.libraries.load(
                item.blend_path,
                link=False
            ) as (data_from, data_to):

                collection_names = list(data_from.collections)

                data_to.collections = collection_names


            # data_to.collections now contains the actual
            # imported Blender Collection objects

            imported_collections = [
                collection
                for collection in data_to.collections
                if collection is not None
            ]

            # ==========================================================
            # CREATE SHOT COLLECTION
            # ==========================================================

            shot_collection = bpy.data.collections.new(
                f"SHOT_{index + 1:02d}_{item.preset_name}"
            )

            root.children.link(shot_collection)

            if not imported_collections:

                self.report(
                    {'WARNING'},
                    f"No collections found in {item.preset_name}"
                )

                current_frame += item.duration
                total_frames += item.duration

                continue

            # ==========================================================
            # PUT PRESET CONTENT INSIDE SHOT COLLECTION
            # ==========================================================

            for collection in imported_collections:

                # Link preset collection to this shot
                shot_collection.children.link(collection)

                # Remove direct link from commercial root if present
                if collection.name in root.children:
                    root.children.unlink(collection)

            # ==============================================
            # Find product slot
            # ==============================================

            slot = find_product_slot(
                imported_collections
            )

            if slot is None:

                self.report(
                    {'WARNING'},
                    f"No product slot in {item.preset_name}"
                )

            # ==============================================
            # Duplicate product
            # ==============================================

            product_copy = selected_obj.copy()

            if selected_obj.data:

                try:

                    product_copy.data = (
                        selected_obj.data.copy()
                    )

                except:

                    pass

            product_copy.name = (
                f"BD_Product_{index + 1:02d}"
            )

            shot_collection.objects.link(product_copy)

            # ==============================================
            # Place product
            # ==============================================

            if slot:

                product_copy.location = (
                    slot.matrix_world.translation
                )

                product_copy.rotation_euler = (
                    slot.matrix_world.to_euler()
                )

                product_copy.parent = slot

                product_copy.matrix_parent_inverse = (
                    slot.matrix_world.inverted()
                )

            # ==============================================
            # Product visibility for this shot
            # ==============================================

            shot_start = current_frame
            shot_end = current_frame + item.duration - 1

            shot_collection["blendirector_start"] = shot_start
            shot_collection["blendirector_end"] = shot_end

            set_shot_objects_visibility(
                shot_collection,
                shot_start,
                shot_end
            )

            # ==============================================
            # Shift all animations
            # ==============================================

            processed_objects = set()

            for collection in imported_collections:

                for obj in collection.all_objects:

                    if obj.name in processed_objects:
                        continue

                    processed_objects.add(
                        obj.name
                    )

                    offset_object_animation(
                        obj,
                        current_frame - 1
                    )

            # ==============================================
            # Find scene camera
            # ==============================================

            camera, camera_error = find_scene_camera(
                imported_collections
            )

            if camera is None:

                self.report(
                    {'ERROR'},
                    f"{item.preset_name}: {camera_error}"
                )

                return {'CANCELLED'}

            marker = scene.timeline_markers.new(
                f"BD_SCENE_{index + 1:02d}_{item.preset_name}",
                frame=current_frame
            )

            marker.camera = camera

            if index == 0:

                scene.camera = camera

            # ==============================================
            # Next scene
            # ==============================================

            current_frame += item.duration

            total_frames += item.duration

        selected_obj.hide_render = True
        selected_obj.hide_viewport = True

        update_shot_viewport_visibility(context.scene)

        # --------------------------------------------------
        # Set final timeline
        # --------------------------------------------------

        scene.frame_start = 1

        scene.frame_end = total_frames

        scene.frame_set(1)

        self.report(
            {'INFO'},
            f"Commercial generated: {total_frames} frames"
        )

        return {'FINISHED'}

# ----------------------------------------------------------
# Timeline Property
# ----------------------------------------------------------

def register_timeline():

    bpy.utils.register_class(
        BLENDIRECTOR_PG_timeline_item
    )

    bpy.types.Scene.blendirector_timeline = bpy.props.CollectionProperty(
        type=BLENDIRECTOR_PG_timeline_item
    )


def unregister_timeline():

    del bpy.types.Scene.blendirector_timeline

    bpy.utils.unregister_class(
        BLENDIRECTOR_PG_timeline_item
    )

# ----------------------------------------------------------
# Registration
# ----------------------------------------------------------

classes = (

    BLENDIRECTOR_OT_refresh,
    BLENDIRECTOR_OT_append,
    BLENDIRECTOR_OT_preview_video,

    BLENDIRECTOR_OT_add_to_timeline,
    BLENDIRECTOR_OT_remove_from_timeline,
    BLENDIRECTOR_OT_move_timeline_up,
    BLENDIRECTOR_OT_move_timeline_down,

    BLENDIRECTOR_OT_generate_commercial,

)


def register():

    for c in classes:
        bpy.utils.register_class(c)

    if update_shot_viewport_visibility not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(
            update_shot_viewport_visibility
        )

    register_timeline()


def unregister():

    unregister_timeline()

    if update_shot_viewport_visibility in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(
            update_shot_viewport_visibility
        )

    for c in reversed(classes):
        bpy.utils.unregister_class(c)