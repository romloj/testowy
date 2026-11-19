#!/usr/bin/env python3
"""
Blender Python Script - MedSystem Ai Pro 1.5 Animation
=======================================================

This script creates a complete 3D animation scene for MedSystem Ai Pro presentation.
Run this in Blender's Scripting workspace.

Requirements:
- Blender 3.6+
- Python 3.10+

Usage:
1. Open Blender
2. Go to Scripting workspace
3. Open this file
4. Click "Run Script"

Features:
- Creates conference room environment
- Adds presenter character
- Creates MedSystem interface mockup
- Sets up lighting and cameras
- Configures animations
"""

import bpy
import math
import mathutils
from math import radians

# ============================================
# CLEANUP EXISTING SCENE
# ============================================

def cleanup_scene():
    """Remove all existing objects, materials, and lights"""
    print("Cleaning up existing scene...")
    
    # Remove all objects
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    
    # Remove all materials
    for mat in bpy.data.materials:
        bpy.data.materials.remove(mat)
    
    # Remove all meshes
    for mesh in bpy.data.meshes:
        bpy.data.meshes.remove(mesh)
    
    # Remove all textures
    for tex in bpy.data.textures:
        bpy.data.textures.remove(tex)
    
    # Remove all images
    for img in bpy.data.images:
        bpy.data.images.remove(img)
    
    print("Scene cleaned up.")


# ============================================
# COLOR CONFIGURATION
# ============================================

class Colors:
    PRIMARY = (0.18, 0.53, 0.67, 1)  # #2E86AB
    SECONDARY = (0.64, 0.23, 0.45, 1)  # #A23B72
    ACCENT = (1, 1, 1, 1)  # White
    BACKGROUND = (0.06, 0.13, 0.16, 1)  # #0f2027
    TEXT = (0.13, 0.23, 0.29, 1)  # #203a43
    WALL = (0.09, 0.13, 0.24, 1)  # #16213e
    FLOOR = (0.1, 0.1, 0.18, 1)  # #1a1a2e
    TABLE = (0.23, 0.29, 0.36, 1)  # #3a4a5c


# ============================================
# MATERIALS
# ============================================

def create_material(name, color, roughness=0.5, metallic=0.0, emission=(0, 0, 0, 1), emission_strength=0):
    """Create a PBR material"""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    
    # Clear existing nodes
    for node in nodes:
        nodes.remove(node)
    
    # Create Principled BSDF shader
    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Emission'].default_value = emission
    bsdf.inputs['Emission Strength'].default_value = emission_strength
    
    # Create Output node
    output = nodes.new(type='ShaderNodeOutputMaterial')
    
    # Link nodes
    links = mat.node_tree.links
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    
    return mat


def create_materials():
    """Create all necessary materials"""
    print("Creating materials...")
    
    materials = {}
    
    # Wall material
    materials['wall'] = create_material("Wall", Colors.WALL, roughness=0.7, metallic=0.1)
    
    # Floor material
    materials['floor'] = create_material("Floor", Colors.FLOOR, roughness=0.8, metallic=0.2)
    
    # Table material
    materials['table'] = create_material("Table", Colors.TABLE, roughness=0.4, metallic=0.3)
    
    # Screen material (emissive)
    materials['screen'] = create_material("Screen", (0, 0, 0, 1), 
                                          roughness=0.1, metallic=0.5,
                                          emission=Colors.PRIMARY, emission_strength=0.3)
    
    # Interface material
    materials['interface'] = create_material("Interface", Colors.PRIMARY,
                                            roughness=0.2, metallic=0.5,
                                            emission=Colors.PRIMARY, emission_strength=0.3)
    
    # Presenter body
    materials['skin'] = create_material("Skin", (1, 0.83, 0.65, 1), roughness=0.8)
    
    # Presenter coat
    materials['coat'] = create_material("Coat", Colors.ACCENT, roughness=0.5, metallic=0.1)
    
    # Logo material
    materials['logo'] = create_material("Logo", Colors.PRIMARY,
                                        roughness=0.2, metallic=0.5,
                                        emission=Colors.PRIMARY, emission_strength=0.5)
    
    return materials


# ============================================
# ENVIRONMENT (Conference Room)
# ============================================

def create_environment(materials):
    """Create the conference room environment"""
    print("Creating conference room...")
    
    # Floor
    bpy.ops.mesh.primitive_plane_add(size=30, enter_editmode=False, align='WORLD')
    floor = bpy.context.object
    floor.name = "Floor"
    floor.rotation_euler = (radians(-90), 0, 0)
    floor.data.materials.append(materials['floor'])
    
    # Walls
    # Back wall
    bpy.ops.mesh.primitive_plane_add(size=10, enter_editmode=False, align='WORLD')
    wall_back = bpy.context.object
    wall_back.name = "Wall_Back"
    wall_back.scale = (3, 1, 1)
    wall_back.location = (0, 5, -15)
    wall_back.data.materials.append(materials['wall'])
    
    # Left wall
    bpy.ops.mesh.primitive_plane_add(size=10, enter_editmode=False, align='WORLD')
    wall_left = bpy.context.object
    wall_left.name = "Wall_Left"
    wall_left.scale = (1, 1, 1)
    wall_left.rotation_euler = (0, radians(90), 0)
    wall_left.location = (-15, 5, 0)
    wall_left.data.materials.append(materials['wall'])
    
    # Right wall
    bpy.ops.mesh.primitive_plane_add(size=10, enter_editmode=False, align='WORLD')
    wall_right = bpy.context.object
    wall_right.name = "Wall_Right"
    wall_right.scale = (1, 1, 1)
    wall_right.rotation_euler = (0, radians(-90), 0)
    wall_right.location = (15, 5, 0)
    wall_right.data.materials.append(materials['wall'])
    
    # Ceiling
    bpy.ops.mesh.primitive_plane_add(size=30, enter_editmode=False, align='WORLD')
    ceiling = bpy.context.object
    ceiling.name = "Ceiling"
    ceiling.rotation_euler = (radians(90), 0, 0)
    ceiling.location = (0, 10, 0)
    ceiling.data.materials.append(materials['wall'])
    
    # LED Screen
    bpy.ops.mesh.primitive_plane_add(size=1, enter_editmode=False, align='WORLD')
    screen = bpy.context.object
    screen.name = "LED_Screen"
    screen.scale = (12, 7, 1)
    screen.location = (0, 4, -14.9)
    screen.data.materials.append(materials['screen'])
    
    # Conference table
    bpy.ops.mesh.primitive_cube_add(size=1, enter_editmode=False, align='WORLD')
    table = bpy.context.object
    table.name = "Conference_Table"
    table.scale = (6, 0.2, 3)
    table.location = (0, 0.1, -5)
    table.data.materials.append(materials['table'])
    
    # Chairs
    for i in range(-2, 3):
        bpy.ops.mesh.primitive_cube_add(size=1, enter_editmode=False, align='WORLD')
        chair = bpy.context.object
        chair.name = f"Chair_{i}"
        chair.scale = (0.8, 1, 0.8)
        chair.location = (i * 1.5, 0.5, -3)
        chair.data.materials.append(materials['table'])
    
    print("Conference room created.")


# ============================================
# PRESENTER CHARACTER
# ============================================

def create_presenter(materials):
    """Create a simplified presenter character"""
    print("Creating presenter character...")
    
    # Create armature for animations
    bpy.ops.object.armature_add(enter_editmode=False, align='WORLD')
    armature = bpy.context.object
    armature.name = "Presenter_Armature"
    armature.location = (0, 0, -3)
    
    # Edit mode for bones
    bpy.ops.object.mode_set(mode='EDIT')
    
    # Create bones
    # Spine
    bone = armature.data.edit_bones.new('Spine')
    bone.head = (0, 0.9, 0)
    bone.tail = (0, 1.8, 0)
    
    # Head
    bone = armature.data.edit_bones.new('Head')
    bone.head = (0, 1.8, 0)
    bone.tail = (0, 2.2, 0)
    bone.parent = armature.data.edit_bones['Spine']
    
    # Left arm
    bone = armature.data.edit_bones.new('Left_Arm')
    bone.head = (0, 1.6, 0)
    bone.tail = (-0.5, 1.2, 0)
    bone.parent = armature.data.edit_bones['Spine']
    
    # Right arm
    bone = armature.data.edit_bones.new('Right_Arm')
    bone.head = (0, 1.6, 0)
    bone.tail = (0.5, 1.2, 0)
    bone.parent = armature.data.edit_bones['Spine']
    
    # Left leg
    bone = armature.data.edit_bones.new('Left_Leg')
    bone.head = (0, 0.9, 0)
    bone.tail = (-0.2, 0.3, 0)
    bone.parent = armature.data.edit_bones['Spine']
    
    # Right leg
    bone = armature.data.edit_bones.new('Right_Leg')
    bone.head = (0, 0.9, 0)
    bone.tail = (0.2, 0.3, 0)
    bone.parent = armature.data.edit_bones['Spine']
    
    # Exit edit mode
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Create body mesh
    bpy.ops.mesh.primitive_cylinder_add(radius=0.3, depth=1.8, enter_editmode=False, align='WORLD')
    body = bpy.context.object
    body.name = "Presenter_Body"
    body.location = (0, 0.9, -3)
    body.data.materials.append(materials['coat'])
    
    # Parent body to armature
    body.parent = armature
    
    # Create head
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, enter_editmode=False, align='WORLD')
    head = bpy.context.object
    head.name = "Presenter_Head"
    head.location = (0, 1.8, -3)
    head.data.materials.append(materials['skin'])
    head.parent = armature
    
    # Create coat
    bpy.ops.mesh.primitive_cylinder_add(radius=0.35, depth=1.5, enter_editmode=False, align='WORLD')
    coat = bpy.context.object
    coat.name = "Presenter_Coat"
    coat.location = (0, 0.75, -3)
    coat.data.materials.append(materials['coat'])
    coat.parent = armature
    
    # Create arms
    for side in ['Left', 'Right']:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=0.8, enter_editmode=False, align='WORLD')
        arm = bpy.context.object
        arm.name = f"Presenter_{side}_Arm"
        arm.rotation_euler = (0, 0, radians(45) if side == 'Left' else radians(-45))
        arm.location = (0.4 if side == 'Right' else -0.4, 1.4, -3)
        arm.data.materials.append(materials['skin'])
        arm.parent = armature
    
    # Create legs
    for side in ['Left', 'Right']:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.1, depth=0.8, enter_editmode=False, align='WORLD')
        leg = bpy.context.object
        leg.name = f"Presenter_{side}_Leg"
        leg.location = (0.15 if side == 'Right' else -0.15, 0.4, -3)
        leg.data.materials.append(materials['table'])
        leg.parent = armature
    
    # Create shoes
    for side in ['Left', 'Right']:
        bpy.ops.mesh.primitive_cube_add(size=1, enter_editmode=False, align='WORLD')
        shoe = bpy.context.object
        shoe.name = f"Presenter_{side}_Shoe"
        shoe.scale = (0.2, 0.1, 0.3)
        shoe.location = (0.15 if side == 'Right' else -0.15, 0.1, -2.7)
        shoe.data.materials.append(materials['table'])
        shoe.parent = armature
    
    print("Presenter character created.")
    return armature


# ============================================
# MEDSYSTEM INTERFACE
# ============================================

def create_interface(materials):
    """Create the MedSystem interface mockup"""
    print("Creating MedSystem interface...")
    
    interface = bpy.data.objects.new("MedSystem_Interface", None)
    bpy.context.collection.objects.link(interface)
    interface.location = (2, 2, -6)
    
    # Main window
    bpy.ops.mesh.primitive_cube_add(size=1, enter_editmode=False, align='WORLD')
    main_window = bpy.context.object
    main_window.name = "Interface_MainWindow"
    main_window.scale = (3, 2, 0.1)
    main_window.parent = interface
    main_window.data.materials.append(materials['interface'])
    
    # Header
    bpy.ops.mesh.primitive_cube_add(size=1, enter_editmode=False, align='WORLD')
    header = bpy.context.object
    header.name = "Interface_Header"
    header.scale = (3, 0.3, 0.1)
    header.location = (0, 0.95, 0)
    header.parent = main_window
    header.data.materials.append(materials['table'])
    
    # Chart area
    bpy.ops.mesh.primitive_cube_add(size=1, enter_editmode=False, align='WORLD')
    chart = bpy.context.object
    chart.name = "Interface_Chart"
    chart.scale = (1.2, 0.8, 0.05)
    chart.location = (-0.7, 0, 0.06)
    chart.parent = main_window
    chart.data.materials.append(materials['secondary'])
    
    # Patient data area
    bpy.ops.mesh.primitive_cube_add(size=1, enter_editmode=False, align='WORLD')
    patient = bpy.context.object
    patient.name = "Interface_PatientData"
    patient.scale = (1.2, 0.8, 0.05)
    patient.location = (0.7, 0, 0.06)
    patient.parent = main_window
    patient.data.materials.append(materials['interface'])
    
    # Buttons
    for i in range(3):
        bpy.ops.mesh.primitive_cube_add(size=1, enter_editmode=False, align='WORLD')
        button = bpy.context.object
        button.name = f"Interface_Button_{i}"
        button.scale = (0.4, 0.15, 0.05)
        button.location = (i * 0.5 - 0.5, -0.7, 0.06)
        button.parent = main_window
        button.data.materials.append(materials['accent'])
    
    print("MedSystem interface created.")
    return interface


# ============================================
# LOGO
# ============================================

def create_logo(materials):
    """Create the MedSystem logo"""
    print("Creating MedSystem logo...")
    
    logo = bpy.data.objects.new("MedSystem_Logo", None)
    bpy.context.collection.objects.link(logo)
    logo.location = (0, 3, -8)
    
    # Logo background
    bpy.ops.mesh.primitive_circle_add(radius=1, enter_editmode=False, align='WORLD')
    logo_back = bpy.context.object
    logo_back.name = "Logo_Background"
    logo_back.parent = logo
    logo_back.data.materials.append(materials['logo'])
    
    # Logo glow effect
    bpy.ops.mesh.primitive_circle_add(radius=1.2, enter_editmode=False, align='WORLD')
    glow = bpy.context.object
    glow.name = "Logo_Glow"
    glow.parent = logo
    glow.location.z = -0.1
    
    # Create glow material
    glow_mat = create_material("Logo_Glow", Colors.PRIMARY, 
                               roughness=0.2, metallic=0.5,
                               emission=Colors.PRIMARY, emission_strength=0.3)
    glow.data.materials.append(glow_mat)
    
    print("MedSystem logo created.")
    return logo


# ============================================
# LIGHTING
# ============================================

def setup_lighting():
    """Set up all lights for the scene"""
    print("Setting up lighting...")
    
    # Ambient light
    bpy.ops.object.light_add(type='SUN', align='WORLD')
    ambient = bpy.context.object
    ambient.name = "Ambient_Light"
    ambient.data.type = 'SUN'
    ambient.data.energy = 0.5
    ambient.data.color = (0.5, 0.5, 0.5, 1)
    
    # Main directional light (sun)
    bpy.ops.object.light_add(type='SUN', align='WORLD')
    main_light = bpy.context.object
    main_light.name = "Main_Light"
    main_light.location = (5, 10, 7)
    main_light.data.energy = 0.8
    main_light.data.color = (1, 1, 1, 1)
    main_light.data.use_shadow = True
    main_light.data.shadow_soft_size = 0.5
    
    # Blue accent light
    bpy.ops.object.light_add(type='POINT', align='WORLD')
    blue_light = bpy.context.object
    blue_light.name = "Blue_Light"
    blue_light.location = (-5, 5, -5)
    blue_light.data.energy = 100
    blue_light.data.color = Colors.PRIMARY
    blue_light.data.shadow_soft_size = 1
    
    # Pink accent light
    bpy.ops.object.light_add(type='POINT', align='WORLD')
    pink_light = bpy.context.object
    pink_light.name = "Pink_Light"
    pink_light.location = (5, 5, -5)
    pink_light.data.energy = 100
    pink_light.data.color = Colors.SECONDARY
    pink_light.data.shadow_soft_size = 1
    
    # World lighting (HDRI)
    bpy.context.scene.world.use_nodes = True
    world_nodes = bpy.context.scene.world.node_tree.nodes
    world_nodes.clear()
    
    # Background node
    bg_node = world_nodes.new(type='ShaderNodeBackground')
    bg_node.inputs['Color'].default_value = Colors.BACKGROUND
    
    # Output node
    output_node = world_nodes.new(type='ShaderNodeOutputWorld')
    
    # Link nodes
    links = bpy.context.scene.world.node_tree.links
    links.new(bg_node.outputs['Background'], output_node.inputs['Surface'])
    
    print("Lighting set up.")


# ============================================
# CAMERAS
# ============================================

def setup_cameras():
    """Set up cameras for different scenes"""
    print("Setting up cameras...")
    
    # Main camera
    bpy.ops.object.camera_add(location=(0, 2, 5), rotation=(radians(0), 0, 0), align='WORLD')
    camera = bpy.context.object
    camera.name = "Main_Camera"
    camera.data.lens = 60
    camera.data.sensor_width = 36
    
    # Set as active camera
    bpy.context.scene.camera = camera
    
    # Camera constraints (track to presenter)
    bpy.ops.object.empty_add(type='PLAIN_AXES', align='WORLD')
    target = bpy.context.object
    target.name = "Camera_Target"
    target.location = (0, 1, -3)
    
    # Track to constraint
    constraint = camera.constraints.new('TRACK_TO')
    constraint.target = target
    constraint.track_axis = 'TRACK_NEGATIVE_Z'
    constraint.up_axis = 'UP_Y'
    
    print("Cameras set up.")
    return camera


# ============================================
# ANIMATIONS
# ============================================

def setup_animations(presenter, interface, logo):
    """Set up animations for the scene"""
    print("Setting up animations...")
    
    # Set timeline range
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 250
    bpy.context.scene.frame_current = 1
    
    # Keyframe presenter animations
    # Wave animation (frames 50-100)
    presenter.location = (0, 0, -3)
    presenter.keyframe_insert(data_path="location", frame=50)
    
    # Arm animation
    right_arm = bpy.data.objects.get("Presenter_Right_Arm")
    if right_arm:
        right_arm.rotation_euler = (0, 0, radians(-45))
        right_arm.keyframe_insert(data_path="rotation_euler", frame=50)
        
        right_arm.rotation_euler = (0, 0, radians(-90))
        right_arm.keyframe_insert(data_path="rotation_euler", frame=75)
        
        right_arm.rotation_euler = (0, 0, radians(-45))
        right_arm.keyframe_insert(data_path="rotation_euler", frame=100)
    
    # Interface appear animation (frames 100-150)
    interface.location = (2, 2, -6)
    interface.scale = (0, 0, 0)
    interface.keyframe_insert(data_path="scale", frame=100)
    interface.keyframe_insert(data_path="location", frame=100)
    
    interface.location = (2, 2, -6)
    interface.scale = (1, 1, 1)
    interface.keyframe_insert(data_path="scale", frame=150)
    interface.keyframe_insert(data_path="location", frame=150)
    
    # Logo appear animation (frames 200-250)
    logo.location = (0, 3, -8)
    logo.scale = (0, 0, 0)
    logo.keyframe_insert(data_path="scale", frame=200)
    
    logo.scale = (1, 1, 1)
    logo.keyframe_insert(data_path="scale", frame=250)
    
    # Camera animations
    camera = bpy.context.scene.camera
    if camera:
        # Intro camera movement (frames 1-50)
        camera.location = (0, 2, 5)
        camera.keyframe_insert(data_path="location", frame=1)
        
        camera.location = (Math.sin(radians(90)) * 2, 2, 5 + Math.cos(radians(90)) * 2)
        camera.keyframe_insert(data_path="location", frame=25)
        
        camera.location = (0, 2, 5)
        camera.keyframe_insert(data_path="location", frame=50)
        
        # Solution camera movement (frames 100-150)
        camera.location = (0, 2, 5)
        camera.keyframe_insert(data_path="location", frame=100)
        
        camera.location = (4, 3, 2)
        camera.keyframe_insert(data_path="location", frame=150)
    
    print("Animations set up.")


# ============================================
# RENDER SETTINGS
# ============================================

def setup_render():
    """Configure render settings"""
    print("Setting up render settings...")
    
    scene = bpy.context.scene
    
    # Resolution
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    
    # Output
    scene.render.filepath = "//render/medsystem_animation_"
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MP4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
    
    # Samples
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 128
    scene.cycles.preview_samples = 64
    
    # Denoising
    scene.cycles.use_denoising = True
    
    # Light paths
    scene.cycles.max_bounces = 8
    scene.cycles.diffuse_bounces = 4
    scene.cycles.glossy_bounces = 4
    
    # Performance
    scene.render.threads_mode = 'AUTO'
    scene.render.threads = 0
    
    print("Render settings configured.")


# ============================================
# MAIN FUNCTION
# ============================================

def create_medsystem_animation():
    """Create the complete MedSystem animation"""
    print("\n" + "="*60)
    print("MEDSYSTEM AI PRO 1.5 - 3D ANIMATION CREATOR")
    print("="*60 + "\n")
    
    # Clean up
    cleanup_scene()
    
    # Create materials
    materials = create_materials()
    
    # Create environment
    create_environment(materials)
    
    # Create presenter
    presenter = create_presenter(materials)
    
    # Create interface
    interface = create_interface(materials)
    
    # Create logo
    logo = create_logo(materials)
    
    # Setup lighting
    setup_lighting()
    
    # Setup cameras
    setup_cameras()
    
    # Setup animations
    setup_animations(presenter, interface, logo)
    
    # Setup render
    setup_render()
    
    # Set up view
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.scene.camera.select_set(True)
    bpy.context.view_layer.objects.active = bpy.context.scene.camera
    
    # Set view to camera
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.region_3d.view_perspective = 'CAMERA'
    
    print("\n" + "="*60)
    print("ANIMATION CREATED SUCCESSFULLY!")
    print("="*60)
    print("\nNext steps:")
    print("1. Press SPACE to play animation")
    print("2. Press F12 to render")
    print("3. Save file (Ctrl+S)")
    print("\nScenes:")
    print("- Frames 1-50: Introdukcja")
    print("- Frames 50-100: Problemy Medyczne")
    print("- Frames 100-150: Rozwiązanie - MedSystem")
    print("- Frames 150-200: Funkcjonalności")
    print("- Frames 200-250: Korzyści + Call to Action")
    print("="*60 + "\n")


# ============================================
# RUN SCRIPT
# ============================================

if __name__ == "__main__":
    create_medsystem_animation()
