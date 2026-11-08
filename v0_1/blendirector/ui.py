import bpy

from . import collection_cache


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

        if not collection_cache:

            layout.label(text="No collections found")

            return

        for name in collection_cache:

            op = layout.operator(
                "blendirector.append_collection",
                text=name,
                icon='OUTLINER_COLLECTION'
            )

            op.collection_name = name


classes = (
    BLENDIRECTOR_PT_panel,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)