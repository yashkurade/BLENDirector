import bpy

from . import asset_cache


# ==========================================================
# UI STATE
# ==========================================================

expanded_categories = {}
expanded_presets = {}


# ==========================================================
# CATEGORY TOGGLE
# ==========================================================

class BLENDIRECTOR_OT_toggle_category(bpy.types.Operator):

    bl_idname = "blendirector.toggle_category"
    bl_label = "Toggle Category"
    bl_description = "Expand or collapse this folder"

    category: bpy.props.StringProperty()

    def execute(self, context):

        expanded_categories[self.category] = not expanded_categories.get(
            self.category,
            True
        )

        return {'FINISHED'}


# ==========================================================
# PRESET TOGGLE
# ==========================================================

class BLENDIRECTOR_OT_toggle_preset(bpy.types.Operator):

    bl_idname = "blendirector.toggle_preset"
    bl_label = "Toggle Preset"

    key: bpy.props.StringProperty()
    tooltip: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        return properties.tooltip

    def execute(self, context):

        expanded_presets[self.key] = not expanded_presets.get(
            self.key,
            False
        )

        return {'FINISHED'}


# ==========================================================
# TIMELINE UI
# ==========================================================

def draw_timeline(layout, context):

    box = layout.box()

    # Header
    row = box.row()

    row.label(
        text="Advertisement",
        icon='TIME'
    )

    timeline = context.scene.blendirector_timeline

    # No scenes
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

    # ------------------------------------------------------
    # Timeline Items
    # ------------------------------------------------------

    total_duration = 0

    for index, item in enumerate(timeline):

        row = box.row(align=True)

        # Scene number
        number = row.row()
        number.scale_x = 0.35

        number.label(
            text=f"{index + 1:02d}"
        )

        # Preset name
        name = row.row()
        name.label(
            text=item.preset_name
        )

        # Duration
        duration = row.row()
        duration.scale_x = 0.55

        duration.label(
            text=f"{item.duration}f"
        )

        # Move up
        up = row.operator(
            "blendirector.move_timeline_up",
            text="",
            icon='TRIA_UP'
        )

        up.index = index

        # Move down
        down = row.operator(
            "blendirector.move_timeline_down",
            text="",
            icon='TRIA_DOWN'
        )

        down.index = index

        # Delete
        remove = row.operator(
            "blendirector.remove_from_timeline",
            text="",
            icon='X'
        )

        remove.index = index

        total_duration += item.duration

    # ------------------------------------------------------
    # Total
    # ------------------------------------------------------

    box.separator()

    row = box.row()

    row.label(
        text=f"Total Duration: {total_duration} frames",
        icon='TIME'
    )

    box.separator()

    generate_row = box.row()

    generate_row.scale_y = 1.5

    generate_row.operator(
        "blendirector.generate_commercial",
        text="Generate Commercial",
        icon='PLAY'
    )

# ==========================================================
# ASSET TREE
# ==========================================================

def draw_tree(layout, node, path=""):

    for name, value in node.items():

        key = f"{path}/{name}" if path else name

        # ==================================================
        # BLEND FILE / PRESET
        # ==================================================

        if isinstance(value, dict) and "blend_path" in value:

            expanded_presets.setdefault(key, False)

            meta = value.get("metadata", {})

            # ------------------------------------------------
            # Preset Header
            # ------------------------------------------------

            row = layout.row(align=True)

            icon = (
                'TRIA_DOWN'
                if expanded_presets[key]
                else 'TRIA_RIGHT'
            )

            op = row.operator(
                "blendirector.toggle_preset",
                text=meta.get("name", name),
                emboss=False,
                icon=icon
            )

            op.key = key

            op.tooltip = meta.get(
                "description",
                "Show preset information"
            )

            # ------------------------------------------------
            # Preset Expanded Content
            # ------------------------------------------------

            if not expanded_presets[key]:
                continue

            box = layout.box()

            # Name
            box.label(
                text=meta.get("name", name),
                icon='INFO'
            )

            # Description
            if meta.get("description"):

                box.label(
                    text=meta["description"]
                )

            # Metadata
            meta_row = box.row()

            if meta.get("author"):

                meta_row.label(
                    text=f"Author: {meta['author']}"
                )

            if meta.get("version"):

                meta_row.label(
                    text=f"v{meta['version']}"
                )

            # Duration
            if meta.get("duration"):

                meta_row.label(
                    text=f"{meta['duration']}f"
                )

            box.separator()

            # =================================================
            # ACTION BUTTONS
            # =================================================

            action_row = box.row(align=True)

            add = action_row.operator(
                "blendirector.add_to_timeline",
                text="Add",
                icon='ADD'
            )

            add.blend_path = value["blend_path"]
            add.preset_name = meta.get(
                "name",
                name
            )
            add.category = path

            # =================================================
            # EXISTING COLLECTION IMPORT
            # =================================================

            box.separator()

            box.label(
                text="Collections",
                icon='OUTLINER_COLLECTION'
            )

            for collection in value["collections"]:

                op = box.operator(
                    "blendirector.append_collection",
                    text=collection,
                    icon='OUTLINER_COLLECTION'
                )

                op.blend_path = value["blend_path"]
                op.collection_name = collection

        # ==================================================
        # FOLDER
        # ==================================================

        else:

            expanded_categories.setdefault(
                key,
                False
            )

            row = layout.row()

            icon = (
                'TRIA_DOWN'
                if expanded_categories[key]
                else 'TRIA_RIGHT'
            )

            op = row.operator(
                "blendirector.toggle_category",
                text=name,
                emboss=False,
                icon=icon
            )

            op.category = key

            if expanded_categories[key]:

                box = layout.box()

                draw_tree(
                    box,
                    value,
                    key
                )


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

        # ==================================================
        # REFRESH
        # ==================================================

        layout.operator(
            "blendirector.refresh",
            icon='FILE_REFRESH'
        )

        layout.separator()

        # ==================================================
        # ADVERTISEMENT TIMELINE
        # ==================================================

        draw_timeline(
            layout,
            context
        )

        layout.separator()

        # ==================================================
        # ASSET LIBRARY
        # ==================================================

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

        draw_tree(
            library_box,
            asset_cache
        )


# ==========================================================
# REGISTRATION
# ==========================================================

classes = (

    BLENDIRECTOR_OT_toggle_category,
    BLENDIRECTOR_OT_toggle_preset,

    BLENDIRECTOR_PT_panel,

)


def register():

    for c in classes:

        bpy.utils.register_class(c)


def unregister():

    for c in reversed(classes):

        bpy.utils.unregister_class(c)