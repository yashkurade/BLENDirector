import bpy

from . import asset_cache
from .operators import get_scene_duration


# TODO: replace with your real itch.io page before publishing
ITCH_URL = "https://ykreate.itch.io/"


# ==========================================================
# BROWSER ITEM (one row in the scrollable list)
# ==========================================================

class BLENDIRECTOR_PG_browser_item(bpy.types.PropertyGroup):

    display_name: bpy.props.StringProperty()
    is_folder: bpy.props.BoolProperty()
    full_key: bpy.props.StringProperty()  # "/" separated path into asset_cache


# ==========================================================
# HELPERS
# ==========================================================

def get_node_at_path(path):
    """Walk asset_cache using a '/' separated path. Empty path = root."""

    node = asset_cache

    if not path:
        return node

    for part in path.split("/"):

        if part == "":
            continue

        if not isinstance(node, dict) or part not in node:
            return {}

        node = node[part]

    return node


def rebuild_browser_items(scene):
    """Refill the scrollable list with the contents of the current folder."""

    items = scene.blendirector_browser_items
    items.clear()

    node = get_node_at_path(scene.blendirector_browser_path)

    if not isinstance(node, dict):
        return

    folders = []
    presets = []

    for name, value in node.items():

        if isinstance(value, dict) and "blend_path" in value:
            presets.append(name)
        else:
            folders.append(name)

    base = scene.blendirector_browser_path

    # Folders first, then presets, both alphabetical
    for name in sorted(folders):

        entry = items.add()
        entry.display_name = name
        entry.is_folder = True
        entry.full_key = f"{base}/{name}" if base else name

    for name in sorted(presets):

        value = node[name]
        meta = value.get("metadata", {})

        entry = items.add()
        entry.display_name = meta.get("name", name)
        entry.is_folder = False
        entry.full_key = f"{base}/{name}" if base else name

    scene.blendirector_browser_index = 0


# ==========================================================
# NAVIGATION OPERATORS
# ==========================================================

class BLENDIRECTOR_OT_browser_open(bpy.types.Operator):

    bl_idname = "blendirector.browser_open"
    bl_label = "Open"
    bl_description = "Open this folder, or select this preset"

    full_key: bpy.props.StringProperty()
    is_folder: bpy.props.BoolProperty()

    def execute(self, context):

        scene = context.scene

        if self.is_folder:

            scene.blendirector_browser_path = self.full_key
            scene.blendirector_selected_preset = ""

            rebuild_browser_items(scene)

        else:

            scene.blendirector_selected_preset = self.full_key

        return {'FINISHED'}


class BLENDIRECTOR_OT_browser_up(bpy.types.Operator):

    bl_idname = "blendirector.browser_up"
    bl_label = "Up"
    bl_description = "Go up one folder"

    def execute(self, context):

        scene = context.scene

        parts = [p for p in scene.blendirector_browser_path.split("/") if p]
        parts = parts[:-1]

        scene.blendirector_browser_path = "/".join(parts)
        scene.blendirector_selected_preset = ""

        rebuild_browser_items(scene)

        return {'FINISHED'}


class BLENDIRECTOR_OT_browser_root(bpy.types.Operator):

    bl_idname = "blendirector.browser_root"
    bl_label = "Root"
    bl_description = "Go to the asset library root"

    def execute(self, context):

        scene = context.scene

        scene.blendirector_browser_path = ""
        scene.blendirector_selected_preset = ""

        rebuild_browser_items(scene)

        return {'FINISHED'}


# ==========================================================
# SCROLLABLE LIST WIDGET
# ==========================================================

class BLENDIRECTOR_UL_asset_browser(bpy.types.UIList):

    bl_idname = "BLENDIRECTOR_UL_asset_browser"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):

        row = layout.row(align=True)

        icon_id = 'FILE_FOLDER' if item.is_folder else 'FILE_BLEND'

        op = row.operator(
            "blendirector.browser_open",
            text=item.display_name,
            icon=icon_id,
            emboss=False
        )

        op.full_key = item.full_key
        op.is_folder = item.is_folder


# ==========================================================
# TIMELINE UI
# ==========================================================

def draw_timeline(layout, context):

    scene = context.scene

    fps = scene.render.fps / scene.render.fps_base

    box = layout.box()

    row = box.row()

    row.label(
        text="Timeline",
        icon='TIME'
    )

    timeline = scene.blendirector_timeline

    if len(timeline) == 0:

        box.separator()

        row = box.row()

        row.label(
            text="No scenes added",
            icon='INFO'
        )

        box.separator()

        box.label(
            text="Use + Add on a preset below"
        )

        return

    total_duration = 0

    for index, item in enumerate(timeline):

        scene_frames = get_scene_duration(item)

        item_box = box.box()

        # --------------------------------------------------
        # Header: number, name, length, move / remove
        # --------------------------------------------------

        row = item_box.row(align=True)

        number = row.row()
        number.scale_x = 0.35

        number.label(
            text=f"{index + 1:02d}"
        )

        name = row.row()
        name.label(
            text=item.preset_name
        )

        length = row.row()
        length.scale_x = 0.9

        length.label(
            text=f"{scene_frames}f · {scene_frames / fps:.1f}s"
        )

        up = row.operator(
            "blendirector.move_timeline_up",
            text="",
            icon='TRIA_UP'
        )

        up.index = index

        down = row.operator(
            "blendirector.move_timeline_down",
            text="",
            icon='TRIA_DOWN'
        )

        down.index = index

        remove = row.operator(
            "blendirector.remove_from_timeline",
            text="",
            icon='X'
        )

        remove.index = index

        # --------------------------------------------------
        # Product slots (one field per slot in the preset)
        # --------------------------------------------------

        if len(item.products) == 0:

            item_box.label(
                text="No product slots in this preset",
                icon='INFO'
            )

        for slot in item.products:

            product_row = item_box.row(align=True)

            split = product_row.split(factor=0.3)

            split.label(text=f"Slot {slot.slot_number}")

            field_row = split.row(align=True)

            field_row.prop(
                slot,
                "product",
                text="",
                icon='OBJECT_DATA'
            )

            pick = field_row.operator(
                "blendirector.set_timeline_product",
                text="",
                icon='RESTRICT_SELECT_OFF'
            )

            pick.index = index
            pick.slot_number = slot.slot_number

        # --------------------------------------------------
        # Sentences: [tick] [text] [frames] [remove]
        # --------------------------------------------------

        sentence_col = item_box.column(align=True)

        for sentence_index, sentence in enumerate(item.sentences):

            sentence_row = sentence_col.row(align=True)

            sentence_row.prop(
                sentence,
                "enabled",
                text=""
            )

            text_row = sentence_row.row(align=True)
            text_row.active = sentence.enabled

            text_row.prop(
                sentence,
                "text",
                text=""
            )

            frames_row = sentence_row.row(align=True)
            frames_row.scale_x = 0.55
            frames_row.active = sentence.enabled

            frames_row.prop(
                sentence,
                "duration",
                text=""
            )

            delete = sentence_row.operator(
                "blendirector.remove_sentence",
                text="",
                icon='X'
            )

            delete.index = index
            delete.sentence_index = sentence_index

        add_sentence = item_box.operator(
            "blendirector.add_sentence",
            text="Add Sentence",
            icon='ADD'
        )

        add_sentence.index = index

        if not any(s.enabled for s in item.sentences):

            item_box.label(
                text=f"No row ticked: scene runs {item.fallback_duration}f",
                icon='INFO'
            )

        total_duration += scene_frames

    box.separator()

    row = box.row()

    row.label(
        text=f"Total Duration: {total_duration} frames ({total_duration / fps:.1f}s)",
        icon='TIME'
    )

    box.separator()

    generate_row = box.row()

    generate_row.scale_y = 1.5

    generate_row.operator(
        "blendirector.generate_commercial",
        text="Build Sequence",
        icon='PLAY'
    )


# ==========================================================
# SUBTITLE STYLE
# ==========================================================

def draw_subtitle_style(layout, context):

    scene = context.scene

    box = layout.box()

    box.label(
        text="Subtitle Style",
        icon='FONT_DATA'
    )

    col = box.column(align=True)

    col.prop(scene, "blendirector_sub_font", text="Font")
    col.prop(scene, "blendirector_sub_size", text="Size")
    col.prop(scene, "blendirector_sub_margin", text="Bottom Margin")
    col.prop(scene, "blendirector_sub_color", text="Color")


# ==========================================================
# SELECTED PRESET DETAIL
# ==========================================================

def draw_selected_preset(layout, context):

    scene = context.scene
    key = scene.blendirector_selected_preset

    if not key:
        return

    value = get_node_at_path(key)

    if not isinstance(value, dict) or "blend_path" not in value:
        return

    meta = value.get("metadata", {})

    box = layout.box()

    box.label(
        text=meta.get("name", key.split("/")[-1]),
        icon='INFO'
    )

    if meta.get("description"):

        box.label(
            text=meta["description"]
        )

    meta_row = box.row()

    if meta.get("author"):

        meta_row.label(
            text=f"Author: {meta['author']}"
        )

    if meta.get("version"):

        meta_row.label(
            text=f"v{meta['version']}"
        )

    if meta.get("duration"):

        meta_row.label(
            text=f"{meta['duration']}f"
        )

    box.separator()

    action_row = box.row(align=True)

    add = action_row.operator(
        "blendirector.add_to_timeline",
        text="Add",
        icon='ADD'
    )

    add.blend_path = value["blend_path"]
    add.preset_name = meta.get("name", key.split("/")[-1])
    add.category = "/".join(key.split("/")[:-1])

    box.separator()

    preview_path = value.get("preview_path")

    preview_row = box.row()
    preview_row.scale_y = 1.2
    preview_row.enabled = bool(preview_path)

    preview_op = preview_row.operator(
        "blendirector.preview_video",
        text="Preview" if preview_path else "No preview available",
        icon='PLAY'
    )

    preview_op.video_path = preview_path or ""


# ==========================================================
# MAIN PANEL
# ==========================================================

class BLENDIRECTOR_PT_panel(bpy.types.Panel):

    bl_label = "Blendirector"
    bl_idname = "BLENDIRECTOR_PT_panel"

    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Blendirector"

    def draw(self, context):

        layout = self.layout
        scene = context.scene

        top_row = layout.row(align=True)

        top_row.operator(
            "blendirector.refresh",
            icon='FILE_REFRESH'
        )

        top_row.operator(
            "blendirector.import_external_preset",
            text="",
            icon='FILEBROWSER'
        )

        donate = top_row.operator(
            "blendirector.support",
            text="",
            icon='FUND'
        )

        donate.url = ITCH_URL

        layout.separator()

        draw_timeline(layout, context)

        layout.separator()

        draw_subtitle_style(layout, context)

        layout.separator()

        library_box = layout.box()

        library_box.label(
            text="Asset Library",
            icon='ASSET_MANAGER'
        )

        if not asset_cache:

            library_box.label(
                text="No assets found",
                icon='ERROR'
            )

            return

        # --------------------------------------------------
        # Breadcrumb
        # --------------------------------------------------

        crumb_row = library_box.row(align=True)

        crumb_row.operator(
            "blendirector.browser_root",
            text="",
            icon='HOME'
        )

        crumb_row.label(
            text=scene.blendirector_browser_path or "/"
        )

        if scene.blendirector_browser_path:

            crumb_row.operator(
                "blendirector.browser_up",
                text="",
                icon='FILE_PARENT'
            )

        # --------------------------------------------------
        # Scrollable list
        # --------------------------------------------------

        library_box.template_list(
            "BLENDIRECTOR_UL_asset_browser",
            "",
            scene,
            "blendirector_browser_items",
            scene,
            "blendirector_browser_index",
            rows=8
        )

        # --------------------------------------------------
        # Selected preset detail
        # --------------------------------------------------

        draw_selected_preset(library_box, context)


# ==========================================================
# REGISTRATION
# ==========================================================

classes = (

    BLENDIRECTOR_PG_browser_item,
    BLENDIRECTOR_UL_asset_browser,

    BLENDIRECTOR_OT_browser_open,
    BLENDIRECTOR_OT_browser_up,
    BLENDIRECTOR_OT_browser_root,

    BLENDIRECTOR_PT_panel,

)


def register_browser_props():

    bpy.types.Scene.blendirector_browser_items = bpy.props.CollectionProperty(
        type=BLENDIRECTOR_PG_browser_item
    )

    bpy.types.Scene.blendirector_browser_index = bpy.props.IntProperty(default=0)

    bpy.types.Scene.blendirector_browser_path = bpy.props.StringProperty(default="")

    bpy.types.Scene.blendirector_selected_preset = bpy.props.StringProperty(default="")


def unregister_browser_props():

    del bpy.types.Scene.blendirector_selected_preset
    del bpy.types.Scene.blendirector_browser_path
    del bpy.types.Scene.blendirector_browser_index
    del bpy.types.Scene.blendirector_browser_items


def register():

    for c in classes:

        bpy.utils.register_class(c)

    register_browser_props()


def unregister():

    unregister_browser_props()

    for c in reversed(classes):

        bpy.utils.unregister_class(c)
