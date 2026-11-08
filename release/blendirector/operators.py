print("OPERATORS FILE LOADED")

import bpy
import os
import re
import json
import math
import sys
import subprocess

from mathutils import Matrix
from bpy_extras.io_utils import ImportHelper
from bpy.app.handlers import persistent

from . import asset_cache


# ==========================================================
# PRODUCT SLOT TAGS
# ==========================================================

SLOT_PATTERN = re.compile(r"^product_slot(?:_(\d+))?$")


def slot_number_from_role(role):
    """'product_slot_3' -> 3. The old plain 'product_slot' counts as 1."""

    if not isinstance(role, str):
        return None

    match = SLOT_PATTERN.match(role.strip())

    if match is None:
        return None

    return int(match.group(1)) if match.group(1) else 1


def read_slot_numbers(blend_path):
    """Peek into a preset .blend and return its sorted slot numbers.
    Never raises: on any problem it returns an empty list."""

    numbers = set()
    library = None

    try:

        with bpy.data.libraries.load(blend_path, link=True) as (data_from, data_to):

            data_to.objects = list(data_from.objects)

        for obj in data_to.objects:

            if obj is None:
                continue

            library = obj.library

            number = slot_number_from_role(obj.get("blendirector_role"))

            if number is not None:
                numbers.add(number)

    except Exception as e:

        print(f"Couldn't scan slots in {blend_path}: {e}")

    # Drop the temporary link so nothing is left in the file
    if library is not None:

        try:
            bpy.data.libraries.remove(library)
        except Exception as e:
            print(e)

    return sorted(numbers)


def find_product_slots(collections):
    """{slot_number: empty_object} for the imported collections."""

    slots = {}

    for collection in collections:

        for obj in collection.all_objects:

            number = slot_number_from_role(obj.get("blendirector_role"))

            if number is not None and number not in slots:
                slots[number] = obj

    return slots


# ==========================================================
# TIMELINE DATA
# ==========================================================

def product_poll(self, obj):
    # don't offer generated copies as a choice
    return not obj.name.startswith("BD_Product_")


class BLENDIRECTOR_PG_product_slot(bpy.types.PropertyGroup):

    slot_number: bpy.props.IntProperty()

    product: bpy.props.PointerProperty(
        name="Product",
        description="Object placed in this slot (leave empty to skip)",
        type=bpy.types.Object,
        poll=product_poll
    )


class BLENDIRECTOR_PG_sentence(bpy.types.PropertyGroup):

    enabled: bpy.props.BoolProperty(
        name="Use",
        description=(
            "Tick to include this row in the scene. Leave the text empty "
            "for a pause with no subtitle. Unticked rows are ignored"
        ),
        default=True
    )

    text: bpy.props.StringProperty(
        name="Text",
        description=(
            "Subtitle shown at the bottom of the frame (max two lines). "
            "Long text is split automatically, or type | to choose the line break"
        )
    )

    duration: bpy.props.IntProperty(
        name="Frames",
        description="How long this row stays on screen",
        default=48,
        min=1
    )

class BLENDIRECTOR_OT_support(bpy.types.Operator):

    bl_idname = "blendirector.support"
    bl_label = "Made with love by YKREATE"
    bl_description = "Support us on itch.io"

    url: bpy.props.StringProperty()

    def execute(self, context):

        if self.url:
            bpy.ops.wm.url_open(url=self.url)

        return {'FINISHED'}

class BLENDIRECTOR_PG_timeline_item(bpy.types.PropertyGroup):

    preset_name: bpy.props.StringProperty()

    blend_path: bpy.props.StringProperty()

    category: bpy.props.StringProperty()

    authored_length: bpy.props.IntProperty(
        name="Authored Length",
        description=(
            "Frames the preset's animation was made for "
            "(0 = detect from its keyframes)"
        ),
        default=0,
        min=0
    )

    fallback_duration: bpy.props.IntProperty(
        name="Default Length",
        description="Scene length used when no sentence row is ticked",
        default=90,
        min=1
    )

    products: bpy.props.CollectionProperty(
        type=BLENDIRECTOR_PG_product_slot
    )

    sentences: bpy.props.CollectionProperty(
        type=BLENDIRECTOR_PG_sentence
    )


def get_scene_duration(item):
    """Scene length = sum of the ticked sentence durations."""

    total = sum(s.duration for s in item.sentences if s.enabled)

    if total > 0:
        return total

    return max(item.fallback_duration, 1)


# ==========================================================
# SET PRODUCT FROM OUTLINER SELECTION
# ==========================================================

class BLENDIRECTOR_OT_set_timeline_product(bpy.types.Operator):

    bl_idname = "blendirector.set_timeline_product"
    bl_label = "Use Active Object"
    bl_description = "Use the object currently selected in the Outliner for this slot"

    index: bpy.props.IntProperty()
    slot_number: bpy.props.IntProperty()

    def execute(self, context):

        timeline = context.scene.blendirector_timeline

        if self.index >= len(timeline):
            return {'CANCELLED'}

        obj = context.active_object

        if obj is None:
            self.report({'ERROR'}, "Select an object in the Outliner first.")
            return {'CANCELLED'}

        if obj.name.startswith("BD_Product_"):
            self.report({'ERROR'}, "That's a generated copy. Pick your original object.")
            return {'CANCELLED'}

        for entry in timeline[self.index].products:

            if entry.slot_number == self.slot_number:
                entry.product = obj
                return {'FINISHED'}

        return {'CANCELLED'}


# ==========================================================
# ASSET FOLDER
# ==========================================================

def get_assets_dir():
    addon_dir = os.path.dirname(__file__)
    return os.path.join(addon_dir, "assets")


# ----------------------------------------------------------
# Load a single preset .blend into a node of asset_cache.
# Shared by scan_assets() and the "Import External Preset"
# operator, so both build entries the exact same way.
# ----------------------------------------------------------

def build_preset_entry(node, blend_path):
    """Read one preset .blend on disk and store it under node[preset_name].
    Returns the preset_name on success, None on failure."""

    folder = os.path.dirname(blend_path)
    file = os.path.basename(blend_path)

    preset_name = os.path.splitext(file)[0]

    metadata_path = os.path.join(folder, "preset.json")

    metadata = {}

    if os.path.exists(metadata_path):

        try:

            with open(metadata_path, "r", encoding="utf-8") as f:

                metadata = json.load(f)

        except Exception as e:

            print(e)

    preview_path = None

    for f in os.listdir(folder):

        if f.lower().endswith(".mp4"):

            preview_path = os.path.join(folder, f)
            break

    slots = read_slot_numbers(blend_path)

    try:

        with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):

            node[preset_name] = {

                "blend_path": blend_path,

                "collections": list(data_from.collections),

                "metadata": metadata,

                "preview_path": preview_path,

                "slots": slots

            }

    except Exception as e:

        print(f"Couldn't read {blend_path}")
        print(e)
        return None

    return preset_name


# ----------------------------------------------------------
# Scan Assets
# ----------------------------------------------------------

def scan_assets():

    asset_cache.clear()

    assets_dir = get_assets_dir()

    if not os.path.exists(assets_dir):
        print("Assets folder not found.")
        return None

    # Single pass over every .blend anywhere under assets/,
    # at any folder depth.

    for root, dirs, files in os.walk(assets_dir):

        for file in sorted(files):

            if not file.lower().endswith(".blend"):
                continue

            blend_path = os.path.join(root, file)

            # Folder hierarchy relative to assets/
            relative_path = os.path.relpath(root, assets_dir)

            folders = [] if relative_path == "." else relative_path.split(os.sep)

            node = asset_cache

            # Create nested dictionary automatically
            for folder in folders:

                node = node.setdefault(folder, {})

            build_preset_entry(node, blend_path)

    def print_node(node, indent=0):

        # A "preset" leaf has a blend_path; anything else
        # is just another folder level to recurse into.

        for name, value in sorted(node.items()):

            if not isinstance(value, dict):
                continue

            if "blend_path" in value:

                print("   " * indent, "-", name)

                for col in value.get("collections", []):
                    print("   " * (indent + 1), "*", col)

            else:

                print("   " * indent, f"[{name}]")
                print_node(value, indent + 1)

    print("\n========== ASSET CACHE ==========")
    print_node(asset_cache)
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

        from . import ui
        ui.rebuild_browser_items(context.scene)

        self.report({'INFO'}, "Assets refreshed")

        return {'FINISHED'}


# ----------------------------------------------------------
# Import an external preset (a .blend the user made themselves,
# living outside the addon's bundled assets/ folder)
# ----------------------------------------------------------

class BLENDIRECTOR_OT_import_external_preset(bpy.types.Operator, ImportHelper):

    bl_idname = "blendirector.import_external_preset"
    bl_label = "Import External Preset"
    bl_description = (
        "Add a preset .blend file from anywhere on disk — must contain "
        "the same properly tagged empties/collections as a bundled preset"
    )

    filename_ext = ".blend"

    filter_glob: bpy.props.StringProperty(
        default="*.blend",
        options={'HIDDEN'}
    )

    def execute(self, context):

        blend_path = self.filepath

        if not os.path.isfile(blend_path):

            self.report({'ERROR'}, "File not found")
            return {'CANCELLED'}

        # External presets get their own top-level folder in the
        # browser, so they never collide with names from assets/
        node = asset_cache.setdefault("External", {})

        preset_name = build_preset_entry(node, blend_path)

        if preset_name is None:

            self.report({'ERROR'}, "Couldn't read that .blend as a preset")
            return {'CANCELLED'}

        scene = context.scene

        if scene is not None:

            from . import ui
            scene.blendirector_browser_path = "External"
            scene.blendirector_selected_preset = ""
            ui.rebuild_browser_items(scene)

        self.report({'INFO'}, f"Imported preset: {preset_name}")

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

            if slot_number_from_role(obj.get("blendirector_role")) is not None:

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

        authored = 0

        if preset:

            metadata = preset.get("metadata", {})

            try:
                authored = int(metadata.get("duration", 0))
            except (TypeError, ValueError):
                authored = 0

            for number in preset.get("slots", []):

                entry = item.products.add()
                entry.slot_number = number

        item.authored_length = max(authored, 0)
        item.fallback_duration = authored if authored > 0 else 90

        # Every scene starts with one ticked, empty row that runs
        # for the preset's own length (= normal speed, no retiming).
        sentence = item.sentences.add()
        sentence.enabled = True
        sentence.text = ""
        sentence.duration = item.fallback_duration

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


# ----------------------------------------------------------
# Add / Remove Sentence
# ----------------------------------------------------------

class BLENDIRECTOR_OT_add_sentence(bpy.types.Operator):

    bl_idname = "blendirector.add_sentence"
    bl_label = "Add Sentence"
    bl_description = "Add another subtitle row to this scene"

    index: bpy.props.IntProperty()

    def execute(self, context):

        timeline = context.scene.blendirector_timeline

        if self.index >= len(timeline):
            return {'CANCELLED'}

        render = context.scene.render
        fps = render.fps / render.fps_base

        sentence = timeline[self.index].sentences.add()
        sentence.enabled = True
        sentence.text = ""
        sentence.duration = max(int(round(fps * 2)), 1)   # 2 seconds

        return {'FINISHED'}


class BLENDIRECTOR_OT_remove_sentence(bpy.types.Operator):

    bl_idname = "blendirector.remove_sentence"
    bl_label = "Remove Sentence"
    bl_description = "Remove this subtitle row"

    index: bpy.props.IntProperty()
    sentence_index: bpy.props.IntProperty()

    def execute(self, context):

        timeline = context.scene.blendirector_timeline

        if self.index >= len(timeline):
            return {'CANCELLED'}

        sentences = timeline[self.index].sentences

        if self.sentence_index < len(sentences):
            sentences.remove(self.sentence_index)

        return {'FINISHED'}


# ==========================================================
# CAMERA / PRODUCT HELPERS
# ==========================================================

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


def unique_objects(collections):
    """Every object in the given collections, each listed once."""

    seen = set()
    result = []

    for collection in collections:

        for obj in collection.all_objects:

            if obj.name in seen:
                continue

            seen.add(obj.name)
            result.append(obj)

    return result


def duplicate_hierarchy(source, shot_collection, name_prefix):
    """Copy an object and every descendant, keep the same parent
    structure between the copies, and link them all into the shot.
    Returns the copy of the top-level object."""

    def clone(obj, new_parent):

        new = obj.copy()

        if obj.data:

            try:
                new.data = obj.data.copy()
            except:
                pass

        new.name = f"{name_prefix}_{obj.name}"

        shot_collection.objects.link(new)

        # obj.copy() still points at the ORIGINAL parent,
        # so re-parent to the copied parent instead
        new.parent = new_parent

        if new_parent is not None:
            new.matrix_parent_inverse = obj.matrix_parent_inverse.copy()

        for child in obj.children:
            clone(child, new)

        return new

    return clone(source, None)


def place_product(product_copy, slot):

    ad = product_copy.animation_data

    animated = ad is not None and ad.action is not None

    if animated:

        # Keyframes are treated as relative to the slot
        product_copy.parent = slot
        product_copy.matrix_parent_inverse = Matrix.Identity(4)
        product_copy.location = (0, 0, 0)
        product_copy.rotation_euler = (0, 0, 0)

    else:

        # Static product: placed exactly on the slot
        product_copy.location = slot.matrix_world.translation
        product_copy.rotation_euler = slot.matrix_world.to_euler()

        product_copy.parent = slot
        product_copy.matrix_parent_inverse = slot.matrix_world.inverted()


# ==========================================================
# RETIMING
#
# Every animated property (transform, rotation, scale, shape
# keys, light/camera settings, material values ...) of every
# element in a scene is stretched/squashed so the animation
# fills the scene's final length, then moved to the scene's
# start frame.
#
# Convention: animation is authored starting at frame 1.
# ==========================================================

def anim_owners(obj, include_materials, protect_shared):
    """Datablocks that can carry keyframes for this object."""

    owners = [obj]

    data = obj.data

    if data is not None and not (protect_shared and data.users > 1):

        owners.append(data)

        shape_keys = getattr(data, "shape_keys", None)

        if shape_keys is not None:
            owners.append(shape_keys)

    if include_materials:

        for slot in obj.material_slots:

            mat = slot.material

            if mat is None:
                continue

            owners.append(mat)

            if mat.node_tree is not None:
                owners.append(mat.node_tree)

    return owners


def animation_end_frame(objects, include_materials, protect_shared):
    """Last keyframe found on the given objects (0 if none)."""

    end = 0.0
    seen = set()

    for obj in objects:

        for owner in anim_owners(obj, include_materials, protect_shared):

            key = owner.as_pointer()

            if key in seen:
                continue

            seen.add(key)

            ad = owner.animation_data

            if ad is None or ad.action is None:
                continue

            for fcurve in ad.action.fcurves:

                for keyframe in fcurve.keyframe_points:

                    end = max(end, keyframe.co.x)

    return end


def retime_owner(owner, offset, factor):

    animation = owner.animation_data

    if animation is None:
        return

    def remap(x):
        return 1 + (x - 1) * factor + offset

    # ------------------------------------------------------
    # Active Action (copied, so the source is never touched)
    # ------------------------------------------------------

    if animation.action:

        action = animation.action.copy()

        for fcurve in action.fcurves:

            for keyframe in fcurve.keyframe_points:

                keyframe.co.x = remap(keyframe.co.x)
                keyframe.handle_left.x = remap(keyframe.handle_left.x)
                keyframe.handle_right.x = remap(keyframe.handle_right.x)

            fcurve.update()

        animation.action = action

    # ------------------------------------------------------
    # NLA strips
    # ------------------------------------------------------

    for track in animation.nla_tracks:

        strips = list(track.strips)

        # move the last strip first when shifting forward so
        # strips never bump into each other
        strips.sort(
            key=lambda s: s.frame_start,
            reverse=(offset > 0 or factor > 1.0)
        )

        for strip in strips:

            try:

                old_start = strip.frame_start

                if factor != 1.0:
                    strip.scale = strip.scale * factor

                new_start = remap(old_start)

                if hasattr(strip, "frame_start_ui"):

                    strip.frame_start_ui = new_start

                else:

                    delta = new_start - old_start
                    strip.frame_end += delta
                    strip.frame_start += delta

            except Exception as e:

                print(f"Blendirector: couldn't retime NLA strip: {e}")


def retime_animation(objects, offset, factor, include_materials, protect_shared):

    seen = set()

    for obj in objects:

        for owner in anim_owners(obj, include_materials, protect_shared):

            key = owner.as_pointer()

            if key in seen:
                continue

            seen.add(key)

            retime_owner(owner, offset, factor)


def fit_factor(duration, authored_end):
    """Stretch factor that maps frames 1..authored_end onto 1..duration."""

    if authored_end <= 1 or duration <= 1:
        return 1.0

    return (duration - 1) / (authored_end - 1)


# ==========================================================
# VISIBILITY KEYFRAMES
# ==========================================================

def set_shot_objects_visibility(collection, start_frame, end_frame):

    objects = list(collection.all_objects)

    for obj in objects:

        # Cameras are controlled by timeline markers.
        if obj.type in {'CAMERA'}:
            continue

        # Subtitles have their own per-sentence visibility.
        if obj.get("blendirector_subtitle"):
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


@persistent
def update_shot_viewport_visibility(scene, *args):

    if bpy.app.is_job_running('RENDER'):
        return

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

            # Subtitles are keyframed per sentence instead
            if obj.get("blendirector_subtitle"):
                continue

            obj.hide_set(not visible)


# ==========================================================
# SUBTITLES
# ==========================================================

SUBTITLE_CHARS_PER_LINE = 45


def format_subtitle(text):
    """Return the text with at most two lines.
    '|' forces a line break; otherwise long text is split near the middle."""

    text = (text or "").strip()

    if not text:
        return ""

    if "|" in text:

        parts = [p.strip() for p in text.split("|") if p.strip()]

        if not parts:
            return ""

        if len(parts) > 2:
            parts = [parts[0], " ".join(parts[1:])]

        return "\n".join(parts)

    if len(text) <= SUBTITLE_CHARS_PER_LINE:
        return text

    middle = len(text) // 2

    left = text.rfind(" ", 0, middle + 1)
    right = text.find(" ", middle)

    candidates = [i for i in (left, right) if i != -1]

    if not candidates:
        return text

    split_at = min(candidates, key=lambda i: abs(i - middle))

    return text[:split_at].strip() + "\n" + text[split_at:].strip()


def get_subtitle_material(color):

    mat = bpy.data.materials.get("BD_Subtitle")

    if mat is None:
        mat = bpy.data.materials.new("BD_Subtitle")

    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")

    emission.inputs["Color"].default_value = (
        color[0], color[1], color[2], 1.0
    )
    emission.inputs["Strength"].default_value = 1.0

    mat.node_tree.links.new(
        emission.outputs["Emission"],
        output.inputs["Surface"]
    )

    return mat


def frame_half_size(scene, cam_data, distance):
    """Half width / half height of what the camera sees at `distance`."""

    render = scene.render

    width = max(render.resolution_x * render.pixel_aspect_x, 1.0)
    height = max(render.resolution_y * render.pixel_aspect_y, 1.0)

    ratio = width / height

    if cam_data.type == 'ORTHO':
        span = cam_data.ortho_scale / 2.0
    else:
        span = distance * math.tan(cam_data.angle / 2.0)

    fit = cam_data.sensor_fit

    if fit == 'VERTICAL' or (fit == 'AUTO' and ratio < 1.0):
        half_h = span
        half_w = span * ratio
    else:
        half_w = span
        half_h = span / ratio

    return half_w, half_h


def create_subtitle(scene, camera, text, name, shot_collection, start, end):
    """Make one 3D text object parented to the camera, visible only
    from frame `start` to frame `end`."""

    body = format_subtitle(text)

    if not body:
        return None

    size_percent = scene.blendirector_sub_size
    margin_percent = scene.blendirector_sub_margin
    color = scene.blendirector_sub_color
    font_path = bpy.path.abspath(scene.blendirector_sub_font)

    cam_data = camera.data

    # Close to the camera so nothing in the set gets in front of it
    distance = max(cam_data.clip_start * 3.0, 0.1)

    half_w, half_h = frame_half_size(scene, cam_data, distance)

    frame_h = 2.0 * half_h
    frame_w = 2.0 * half_w

    # A scaled camera rig would scale its children too: compensate
    scale = camera.matrix_world.to_scale()
    average = (abs(scale.x) + abs(scale.y) + abs(scale.z)) / 3.0

    if average < 1e-6:
        average = 1.0

    unit = 1.0 / average

    size = frame_h * size_percent / 100.0

    # Rough guard: shrink the text if the longest line would
    # run past ~90% of the frame width
    lines = body.split("\n")
    longest = max(len(line) for line in lines)
    estimated_width = longest * 0.55 * size

    if estimated_width > frame_w * 0.9:
        size *= (frame_w * 0.9) / estimated_width

    curve = bpy.data.curves.new(name=name, type='FONT')

    curve.body = body
    curve.size = size * unit
    curve.align_x = 'CENTER'
    curve.align_y = 'BOTTOM'

    if font_path and os.path.isfile(font_path):

        try:
            curve.font = bpy.data.fonts.load(font_path, check_existing=True)
        except Exception as e:
            print(f"Blendirector: couldn't load font {font_path}: {e}")

    curve.materials.append(get_subtitle_material(color))

    obj = bpy.data.objects.new(name, curve)

    shot_collection.objects.link(obj)

    # Child of the camera itself, so it follows every camera move
    obj.parent = camera
    obj.matrix_parent_inverse = Matrix.Identity(4)

    bottom = -half_h + frame_h * margin_percent / 100.0

    obj.location = (0.0, bottom * unit, -distance * unit)

    obj["blendirector_subtitle"] = True

    # No shadows / reflections from the text
    for attr in (
        "visible_diffuse",
        "visible_glossy",
        "visible_transmission",
        "visible_volume_scatter",
        "visible_shadow",
    ):

        if hasattr(obj, attr):
            setattr(obj, attr, False)

    # Visible only while its sentence is on screen
    for prop in ("hide_viewport", "hide_render"):

        setattr(obj, prop, True)
        obj.keyframe_insert(data_path=prop, frame=start - 1)

        setattr(obj, prop, False)
        obj.keyframe_insert(data_path=prop, frame=start)
        obj.keyframe_insert(data_path=prop, frame=end)

        setattr(obj, prop, True)
        obj.keyframe_insert(data_path=prop, frame=end + 1)

    return obj


# ==========================================================
# GENERATE COMMERCIAL
# ==========================================================

class BLENDIRECTOR_OT_generate_commercial(bpy.types.Operator):

    bl_idname = "blendirector.generate_commercial"
    bl_label = "Build Sequence"

    def execute(self, context):

        scene = context.scene

        timeline = scene.blendirector_timeline

        # --------------------------------------------------
        # Validation
        # --------------------------------------------------

        if len(timeline) == 0:

            self.report(
                {'ERROR'},
                "Timeline is empty."
            )

            return {'CANCELLED'}

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

            # Scene length = sum of the ticked sentence durations
            duration = get_scene_duration(item)

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

                current_frame += duration
                total_frames += duration

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
            # Find product slots
            # ==============================================

            slots = find_product_slots(
                imported_collections
            )

            if not slots:

                self.report(
                    {'WARNING'},
                    f"No product slots in {item.preset_name}"
                )

            # ==============================================
            # Duplicate + place a product for each FILLED slot.
            # Vacant slots are skipped, never an error.
            # ==============================================

            product_copies = []

            for entry in item.products:

                if entry.product is None:
                    continue

                slot = slots.get(entry.slot_number)

                if slot is None:

                    self.report(
                        {'WARNING'},
                        f"{item.preset_name}: slot {entry.slot_number} not found, skipped"
                    )

                    continue

                product_copy = duplicate_hierarchy(
                    entry.product,
                    shot_collection,
                    f"BD_Product_{index + 1:02d}_S{entry.slot_number}"
                )

                place_product(product_copy, slot)

                product_copies.append(product_copy)

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

            # ==============================================
            # Retime ALL animation in this scene so it fills
            # the scene's final length, and move it to the
            # scene's start frame. (Must run BEFORE the
            # visibility keyframes are added below.)
            # ==============================================

            shift = current_frame - 1

            preset_objects = unique_objects(imported_collections)

            if item.authored_length > 1:
                preset_end = float(item.authored_length)
            else:
                preset_end = animation_end_frame(
                    preset_objects,
                    include_materials=True,
                    protect_shared=False
                )

            retime_animation(
                preset_objects,
                shift,
                fit_factor(duration, preset_end),
                include_materials=True,
                protect_shared=False
            )

            product_objects = []

            for product_copy in product_copies:

                product_objects.append(product_copy)
                product_objects.extend(product_copy.children_recursive)

            product_end = animation_end_frame(
                product_objects,
                include_materials=False,
                protect_shared=True
            )

            retime_animation(
                product_objects,
                shift,
                fit_factor(duration, product_end),
                include_materials=False,
                protect_shared=True
            )

            # ==============================================
            # Visibility for this shot
            # ==============================================

            shot_start = current_frame
            shot_end = current_frame + duration - 1

            shot_collection["blendirector_start"] = shot_start
            shot_collection["blendirector_end"] = shot_end

            set_shot_objects_visibility(
                shot_collection,
                shot_start,
                shot_end
            )

            # ==============================================
            # Subtitles: one text object per ticked sentence,
            # played one after another from the scene's start
            # ==============================================

            sentence_start = shot_start

            for number, sentence in enumerate(item.sentences):

                if not sentence.enabled:
                    continue

                sentence_end = sentence_start + sentence.duration - 1

                create_subtitle(
                    scene,
                    camera,
                    sentence.text,
                    f"BD_Subtitle_{index + 1:02d}_{number + 1:02d}",
                    shot_collection,
                    sentence_start,
                    sentence_end
                )

                sentence_start += sentence.duration

            # ==============================================
            # Camera marker
            # ==============================================

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

            current_frame += duration

            total_frames += duration

        update_shot_viewport_visibility(context.scene)

        # --------------------------------------------------
        # Set final timeline
        # --------------------------------------------------

        scene.frame_start = 1

        scene.frame_end = total_frames

        scene.frame_set(1)

        self.report(
            {'INFO'},
            f"Sequence Built successfully: {total_frames} frames"
        )

        return {'FINISHED'}


# ==========================================================
# TIMELINE + SUBTITLE STYLE PROPERTIES
# ==========================================================

def register_timeline():

    bpy.utils.register_class(BLENDIRECTOR_PG_product_slot)
    bpy.utils.register_class(BLENDIRECTOR_PG_sentence)
    bpy.utils.register_class(BLENDIRECTOR_PG_timeline_item)

    bpy.types.Scene.blendirector_timeline = bpy.props.CollectionProperty(
        type=BLENDIRECTOR_PG_timeline_item
    )

    bpy.types.Scene.blendirector_sub_font = bpy.props.StringProperty(
        name="Font",
        description="Font file (.ttf / .otf) for subtitles. Empty = Blender's built-in font",
        subtype='FILE_PATH',
        default=""
    )

    bpy.types.Scene.blendirector_sub_size = bpy.props.FloatProperty(
        name="Size",
        description="Text height as a percentage of the frame height",
        default=5.0,
        min=1.0,
        max=25.0,
        precision=1,
        subtype='PERCENTAGE'
    )

    bpy.types.Scene.blendirector_sub_margin = bpy.props.FloatProperty(
        name="Bottom Margin",
        description="Distance from the bottom edge, as a percentage of the frame height",
        default=6.0,
        min=0.0,
        max=40.0,
        precision=1,
        subtype='PERCENTAGE'
    )

    bpy.types.Scene.blendirector_sub_color = bpy.props.FloatVectorProperty(
        name="Color",
        description="Subtitle color",
        subtype='COLOR',
        size=3,
        min=0.0,
        max=1.0,
        default=(1.0, 1.0, 1.0)
    )


def unregister_timeline():

    del bpy.types.Scene.blendirector_sub_color
    del bpy.types.Scene.blendirector_sub_margin
    del bpy.types.Scene.blendirector_sub_size
    del bpy.types.Scene.blendirector_sub_font
    del bpy.types.Scene.blendirector_timeline

    bpy.utils.unregister_class(BLENDIRECTOR_PG_timeline_item)
    bpy.utils.unregister_class(BLENDIRECTOR_PG_sentence)
    bpy.utils.unregister_class(BLENDIRECTOR_PG_product_slot)


# ==========================================================
# REGISTRATION
# ==========================================================

classes = (

    BLENDIRECTOR_OT_refresh,
    BLENDIRECTOR_OT_import_external_preset,
    BLENDIRECTOR_OT_append,
    BLENDIRECTOR_OT_preview_video,

    BLENDIRECTOR_OT_add_to_timeline,
    BLENDIRECTOR_OT_remove_from_timeline,
    BLENDIRECTOR_OT_move_timeline_up,
    BLENDIRECTOR_OT_move_timeline_down,

    BLENDIRECTOR_OT_add_sentence,
    BLENDIRECTOR_OT_remove_sentence,

    BLENDIRECTOR_OT_generate_commercial,
    BLENDIRECTOR_OT_set_timeline_product,
    BLENDIRECTOR_OT_support,

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
