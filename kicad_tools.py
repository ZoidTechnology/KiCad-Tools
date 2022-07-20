import bpy
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector
from math import radians

bl_info = {
	'name': 'KiCad Tools',
	'author': 'Zoid Technology',
	'version': (1, 0),
	'blender': (3, 2, 0)
}

LAYER_CORRECTION_INCREMENT = 0.0125 / 1000

WELD_DISTANCE = 0.00001
DECIMATE_ANGLE = 5
REMESH_DEPTH = 10

SUBSTRATE_THICKNESS = 1.6

PLATED_HOLE_THICKNESS_MULTIPLIER = 0.97
PLATED_HOLE_SUBDIVISION_LEVEL = 2
PLATED_HOLE_RIM_THICKNESS = 0.2

COPPER_THICKNESS = 0.04

MASK_THICKNESS = 0.04
MASK_DISPLACEMENT = 0.03

SILKSCREEN_THICKNESS = 0.04
SILKSCREEN_DISPLACEMENT = 0.02

PASTE_THICKNESS = COPPER_THICKNESS + 0.08
PASTE_REMESH_DEPTH = REMESH_DEPTH

SMOOTH_ANGLE = 45
COMPONENT_SMOOTH_ANGLE = 22.5

LAYERS = (
	{
		'name': 'Components',
		'smooth': COMPONENT_SMOOTH_ANGLE
	}, {
		'name': 'Substrate',
		'smooth': SMOOTH_ANGLE
	}, {
		'name': 'Front Copper',
		'correction': 1,
		'thickness': COPPER_THICKNESS,
		'smooth': SMOOTH_ANGLE
	}, {
		'name': 'Front Paste',
		'correction': 2,
		'thickness': PASTE_THICKNESS,
		'remesh': PASTE_REMESH_DEPTH
	}, {
		'name': 'Front Mask',
		'correction': 2,
		'thickness': MASK_THICKNESS,
		'displace': {
			'source': 'Front Copper',
			'scale': MASK_DISPLACEMENT
		}
	}, {
		'name': 'Back Copper',
		'correction': -1,
		'thickness': -COPPER_THICKNESS,
		'smooth': SMOOTH_ANGLE
	}, {
		'name': 'Back Paste',
		'correction': -2,
		'thickness': -PASTE_THICKNESS,
		'remesh': PASTE_REMESH_DEPTH
	}, {
		'name': 'Back Mask',
		'correction': -2,
		'thickness': -MASK_THICKNESS,
		'displace': {
			'source': 'Back Copper',
			'scale': -MASK_DISPLACEMENT
		}
	}, {
		'name': 'Plated Holes',
		'smooth': SMOOTH_ANGLE
	}, {
		'name': 'Front Silkscreen',
		'correction': 7,
		'offset': MASK_THICKNESS,
		'thickness': SILKSCREEN_THICKNESS,
		'displace': {
			'source': 'Front Copper',
			'scale': SILKSCREEN_DISPLACEMENT
		}
	}, {
		'name': 'Back Silkscreen',
		'correction': -7,
		'offset': -MASK_THICKNESS,
		'thickness': -SILKSCREEN_THICKNESS,
		'displace': {
			'source': 'Back Copper',
			'scale': -SILKSCREEN_DISPLACEMENT
		}
	}
)

class Import(bpy.types.Operator, ImportHelper):
	'''Import a KiCad PCB in VRML format'''

	bl_idname = 'kicad_tools.import'
	bl_label = 'Import KiCad PCB'
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		collection = bpy.data.collections.new('PCB')
		context.scene.collection.children.link(collection)

		layer_collection = context.view_layer.layer_collection.children[collection.name]
		context.view_layer.active_layer_collection = layer_collection

		bpy.ops.import_scene.x3d(filepath = self.properties.filepath, axis_up = 'Z')

		objects = len(collection.objects)
		layers = len(LAYERS) - 1

		if objects < layers:
			self.report({'ERROR'}, 'Too few objects to assign layers!')
			return {'CANCELLED'}

		bpy.ops.object.select_all(action = 'DESELECT')
		context.view_layer.objects.active = collection.objects[0]

		names = [layer['name'] for layer in LAYERS]

		if objects > layers:
			for object in collection.objects[:1 - len(LAYERS)]:
				object.select_set(True)

			bpy.ops.object.join()

		else:
			del names[0]

		for object, name in zip(collection.objects, names):
			object.name = name

		return {'FINISHED'}

def set_position(context):
	bpy.ops.object.select_all(action = 'DESELECT')

	substrate = bpy.data.objects['Substrate']
	substrate.select_set(True)

	bpy.ops.object.origin_set(type = 'ORIGIN_GEOMETRY', center = 'BOUNDS')

	for layer in LAYERS:
		name = layer['name']

		if name == 'Substrate' or name not in bpy.data.objects:
			continue

		mesh = bpy.data.objects[name]
		mesh.location -= substrate.location

		if 'correction' in layer:
			mesh.location -= Vector((0, 0, layer['correction'] * LAYER_CORRECTION_INCREMENT))
		
		if 'offset' in layer:
			mesh.location += Vector((0, 0, layer['offset'] / 1000))

		mesh.select_set(True)

	substrate.location = (0, 0, 0)

	context.scene.cursor.location = (0, 0, 0)

	bpy.data.objects['Plated Holes'].scale *= Vector((1, 1, PLATED_HOLE_THICKNESS_MULTIPLIER * ((SUBSTRATE_THICKNESS + COPPER_THICKNESS * 2) / SUBSTRATE_THICKNESS)))

	bpy.ops.object.origin_set(type = 'ORIGIN_CURSOR')
	bpy.ops.object.transform_apply(location = True, rotation = True, scale = True)

def create_node_group(name):
	group = bpy.data.node_groups.new(name, 'GeometryNodeTree')

	group.inputs.new('NodeSocketGeometry', 'Geometry')
	input = group.nodes.new('NodeGroupInput')

	group.outputs.new('NodeSocketGeometry', 'Geometry')
	output = group.nodes.new('NodeGroupOutput')

	return group, input, output

def create_extrude_node_group():
	group, input, output = create_node_group('Extrude')

	group.inputs.new('NodeSocketFloat', 'Height')

	combine_xyz = group.nodes.new('ShaderNodeCombineXYZ')
	group.links.new(input.outputs['Height'], combine_xyz.inputs['Z'])

	extrude_mesh = group.nodes.new('GeometryNodeExtrudeMesh')
	extrude_mesh.inputs['Individual'].default_value = False
	group.links.new(input.outputs['Geometry'], extrude_mesh.inputs['Mesh'])
	group.links.new(combine_xyz.outputs['Vector'], extrude_mesh.inputs['Offset'])

	group.links.new(extrude_mesh.outputs['Mesh'], output.inputs['Geometry'])

	return group

def create_displace_node_group():
	group, input, output = create_node_group('Displace')

	group.inputs.new('NodeSocketObject', 'Source')
	group.inputs.new('NodeSocketFloat', 'Scale')

	object_info = group.nodes.new('GeometryNodeObjectInfo')
	object_info.transform_space = 'RELATIVE'
	group.links.new(input.outputs['Source'], object_info.inputs['Object'])

	position = group.nodes.new('GeometryNodeInputPosition')

	compare = group.nodes.new('FunctionNodeCompare')
	group.links.new(input.outputs['Scale'], compare.inputs[0])
	
	switch = group.nodes.new('GeometryNodeSwitch')
	switch.input_type = 'VECTOR'
	switch.inputs[8].default_value = (0, 0, -1)
	switch.inputs[9].default_value = (0, 0, 1)
	group.links.new(compare.outputs['Result'], switch.inputs[0])

	vector_math = group.nodes.new('ShaderNodeVectorMath')
	group.links.new(position.outputs['Position'], vector_math.inputs[0])
	group.links.new(switch.outputs[3], vector_math.inputs[1])

	math = group.nodes.new('ShaderNodeMath')
	math.operation = 'SUBTRACT'
	math.inputs[0].default_value = 0
	group.links.new(input.outputs['Scale'], math.inputs[1])

	combine_xyz = group.nodes.new('ShaderNodeCombineXYZ')
	group.links.new(math.outputs['Value'], combine_xyz.inputs['Z'])

	raycast = group.nodes.new('GeometryNodeRaycast')
	group.links.new(object_info.outputs['Geometry'], raycast.inputs['Target Geometry'])
	group.links.new(vector_math.outputs['Vector'], raycast.inputs['Source Position'])
	group.links.new(combine_xyz.outputs['Vector'], raycast.inputs['Ray Direction'])

	combine_xyz = group.nodes.new('ShaderNodeCombineXYZ')
	group.links.new(input.outputs['Scale'], combine_xyz.inputs['Z'])

	set_position = group.nodes.new('GeometryNodeSetPosition')
	group.links.new(combine_xyz.outputs['Vector'], set_position.inputs['Offset'])
	group.links.new(input.outputs['Geometry'], set_position.inputs['Geometry'])
	group.links.new(raycast.outputs['Is Hit'], set_position.inputs['Selection'])

	group.links.new(set_position.outputs['Geometry'], output.inputs['Geometry'])

	return group

def add_basic_modifiers(target):
	modifier = target.modifiers.new('Weld', 'WELD')
	modifier.merge_threshold = WELD_DISTANCE

	modifier = target.modifiers.new('Decimate', 'DECIMATE')
	modifier.decimate_type = 'DISSOLVE'
	modifier.angle_limit = radians(DECIMATE_ANGLE)
	modifier.delimit = {'MATERIAL'}

def add_extrude_modifier(target, node_group, height):
	modifier = target.modifiers.new('Extrude', 'NODES')
	modifier.node_group = node_group
	modifier['Input_2'] = height

def add_remesh_modifier(target, depth):
	modifier = target.modifiers.new('Remesh', 'REMESH')
	modifier.mode = 'SMOOTH'
	modifier.octree_depth = depth
	modifier.use_remove_disconnected  = False
	modifier.use_smooth_shade = True

def add_displacement_modifier(target, node_group, source, scale):
	modifier = target.modifiers.new('Displace', 'NODES')
	modifier.node_group = node_group
	modifier['Input_2'] = source
	modifier['Input_3'] = scale

def add_plated_hole_modifiers():
	target = bpy.data.objects['Plated Holes']

	modifier = target.modifiers.new('Subdivision', 'SUBSURF')
	modifier.levels = PLATED_HOLE_SUBDIVISION_LEVEL
	modifier.render_levels = PLATED_HOLE_SUBDIVISION_LEVEL

	modifier = target.modifiers.new('Solidify', 'SOLIDIFY')
	modifier.thickness = PLATED_HOLE_RIM_THICKNESS / 1000
	modifier.use_rim_only = True

class CreateNodes(bpy.types.Operator):
	'''Create KiCad geometry node groups and apply them to PCB objects'''

	bl_idname = 'kicad_tools.create_nodes'
	bl_label = 'Create KiCad Nodes'
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		set_position(context)

		extrude_node_group = create_extrude_node_group()
		displace_node_group = create_displace_node_group()

		for layer in LAYERS:
			name = layer['name']

			if name not in bpy.data.objects:
				continue

			target = bpy.data.objects[name]

			target.modifiers.clear()

			add_basic_modifiers(target)

			if 'thickness' in layer:
				add_extrude_modifier(target, extrude_node_group, layer['thickness'] / 1000)
			
			if 'remesh' in layer:
				add_remesh_modifier(target, layer['remesh'])
			elif 'displace' in layer:
				add_remesh_modifier(target, REMESH_DEPTH)
				add_displacement_modifier(target, displace_node_group, bpy.data.objects[layer['displace']['source']], layer['displace']['scale'] / 1000)
			elif 'smooth' in layer:
				target.data.use_auto_smooth = True
				target.data.auto_smooth_angle = radians(layer['smooth'])
				
				for polygon in target.data.polygons:
					polygon.use_smooth = True
		
		add_plated_hole_modifiers()

		bpy.ops.object.select_all(action = 'DESELECT')

		return {'FINISHED'}

class ApplyModifiers(bpy.types.Operator):
	'''Apply all modifiers to KiCad objects'''

	bl_idname = 'kicad_tools.apply_modifiers'
	bl_label = 'Apply KiCad Modifiers'
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		for layer in LAYERS:
			name = layer['name']

			if name not in bpy.data.objects:
				continue

			context.view_layer.objects.active = bpy.data.objects[name]

			for modifier in context.view_layer.objects.active.modifiers:
				bpy.ops.object.modifier_apply(modifier = modifier.name)

		return {'FINISHED'}

def import_menu(self, context):
	self.layout.operator(Import.bl_idname, text = 'KiCad PCB')

def object_menu(self, context):
	self.layout.separator()
	self.layout.operator(CreateNodes.bl_idname)
	self.layout.operator(ApplyModifiers.bl_idname)

def register():
	bpy.utils.register_class(Import)
	bpy.utils.register_class(CreateNodes)
	bpy.utils.register_class(ApplyModifiers)

	bpy.types.TOPBAR_MT_file_import.append(import_menu)
	bpy.types.VIEW3D_MT_object.append(object_menu)

def unregister():
	bpy.types.TOPBAR_MT_file_import.remove(import_menu)
	bpy.types.VIEW3D_MT_object.remove(object_menu)