import bpy

from . import asset_cache

expanded_categories = {}
expanded_presets = {}

class BLENDIRECTOR_OT_toggle_category(bpy.types.Operator):

    bl_idname = "blendirector.toggle_category"
    bl_label = "Toggle Category"
    bl_description = "Expand or collapse this folder"

    category: bpy.props.StringProperty()

    def execute(self, context):

        expanded_categories[self.category] = not expanded_categories.get(self.category, True)

        return {'FINISHED'}


class BLENDIRECTOR_OT_toggle_preset(bpy.types.Operator):

    bl_idname = "blendirector.toggle_preset"
    bl_label = "Toggle Preset"

    key: bpy.props.StringProperty()
    tooltip: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        return properties.tooltip

    def execute(self, context):

        expanded_presets[self.key] = not expanded_presets.get(self.key, True)

        return {'FINISHED'}

def draw_tree(layout, node, path=""):

    for name, value in node.items():

        key = f"{path}/{name}" if path else name

        # Blend file (leaf)
        if isinstance(value, dict) and "blend_path" in value:

            expanded_presets.setdefault(key, False)

            meta = value.get("metadata", {})

            row = layout.row()

            icon = 'TRIA_DOWN' if expanded_presets[key] else 'TRIA_RIGHT'

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

            if not expanded_presets[key]:
                continue

            col = layout.column(align=True)

            info = col.box()

            info.label(
                text=meta.get("name", name),
                icon='INFO'
            )

            if meta.get("description"):
                info.label(text=meta["description"])

            row = info.row()
            row.scale_y = 0.8

            if meta.get("author"):
                row.label(text=f"Author: {meta['author']}")

            if meta.get("version"):
                row.label(text=f"Version: {meta['version']}")

            info.separator()

            for collection in value["collections"]:

                op = col.operator(
                    "blendirector.append_collection",
                    text=collection,
                    icon='OUTLINER_COLLECTION'
                )

                # We'll replace these with blend_path later
                op.blend_path = value["blend_path"]
                op.collection_name = collection

        # Folder
        else:

            expanded_categories.setdefault(key, False)

            row = layout.row()

            icon = 'TRIA_DOWN' if expanded_categories[key] else 'TRIA_RIGHT'

            op = row.operator(
                "blendirector.toggle_category",
                text=name,
                emboss=False,
                icon=icon
            )
            op.category = key

            if expanded_categories[key]:

                box = layout.box()

                draw_tree(box, value, key)

class BLENDIRECTOR_PT_panel(bpy.types.Panel):
    bl_label = "Blendirector"
    bl_idname = "BLENDIRECTOR_PT_panel"

    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Blendirector"

    def draw(self, context):

        layout = self.layout

        layout.operator("blendirector.refresh", icon='FILE_REFRESH')

        layout.separator()

        if not asset_cache:
            layout.label(text="No assets found", icon='ERROR')
            return

        draw_tree(layout, asset_cache)


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