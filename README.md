# Starling 2 CAD to USD

Convert the ModalAI Starling 2 STEP assembly into a USD asset for Isaac Sim and Pegasus Simulator.

[CAD files and USD asset](https://drive.google.com/drive/folders/1k4Sfebg8j9LJh4NXsCWhVzftJGb4_1UY?usp=sharing)

```text
STEP → Fusion 360 / SolidWorks → Isaac Sim → Blender → Isaac Sim → USD
```

The earlier scripted conversion is in [`old/`](old/).

## Requirements

- Fusion 360 or SolidWorks
- Isaac Sim with STEP import support
- Blender with USD import and export support
- Pegasus Simulator and PX4 SITL for autopilot integration

## 1. Prepare the CAD assembly

Open the STEP assembly in Fusion 360 or SolidWorks.

1. Remove components that are unnecessary for visual or collision geometry.
2. Before edits to linked components, break their external references.
3. Correct component positions with Constrain or Mate.
4. Rotate each propeller into its deployed position.
5. Export the assembly as STEP.

## 2. Import into Isaac Sim

1. Use `File → Import` to open the STEP file.
2. Disable **Enable Instancing** in the import dialog.
3. Save the assembly as USD.

## 3. Merge meshes in Blender

Import the USD through `File → Import → USD`.

Use a forward-left-up body frame: +X forward, +Y left, +Z up. Preserve the physical dimensions through each export.

For each group (`body`, `rotor0`, `rotor1`, `rotor2`, `rotor3`):

1. Select only the meshes in that group.
2. Use `Ctrl + J` to join them.
3. Rename the merged object to match the group.
4. Enter Edit Mode with `Tab`.
5. Select all vertices with `A`.
6. Use `M → By Distance` to merge duplicate vertices.
7. Recalculate normals with `Shift + N`.
8. Triangulate with `Ctrl + T`.

Export through `File → Export → USD`. Enable **Apply Modifiers**, **Export UVs**, **Normals**, and **Triangulate Meshes**.

## 4. Configure physics in Isaac Sim

Open the merged USD. Set the drone Xform as the asset's `defaultPrim`.

Pegasus expects `body` and `rotor0`–`rotor3` directly under the referenced vehicle root. It identifies rotor joints by the names `joint0`–`joint3`.

```text
starling_2 (Xform, defaultPrim)
├── body (Xform)
│   └── body (Mesh)
├── rotor0 (Xform)
│   ├── rotor0 (Mesh)
│   └── joint0 (PhysicsRevoluteJoint)
├── rotor1 (Xform)
│   ├── rotor1 (Mesh)
│   └── joint1 (PhysicsRevoluteJoint)
├── rotor2 (Xform)
│   ├── rotor2 (Mesh)
│   └── joint2 (PhysicsRevoluteJoint)
└── rotor3 (Xform)
    ├── rotor3 (Mesh)
    └── joint3 (PhysicsRevoluteJoint)
```

Mesh names and joint locations in this example are organizational choices.

1. Add **Physics → Articulation Root** to the drone root.
2. Add colliders to the collision meshes.
3. Add **Physics → Rigid Body** to the body and each rotor Xform.
4. Add **Physics → Mass** to each rigid body.
5. Create a revolute joint between the body and each rotor.
6. Name the joints `joint0` through `joint3` to match their rotors.
7. Align each joint axis with its rotor shaft.

Use measured mass and CAD mass properties for each rigid body. The sum of the body and rotor masses must equal the total vehicle mass.

| Property | Body | Each rotor |
|---|---|---|
| Mass (kg) | Vehicle mass minus the rotor assemblies | Rotor assembly mass |
| Center of mass (m) | Offset in the body frame | Offset in the rotor frame |
| Diagonal inertia (kg·m²) | Chassis inertia about its center of mass | Rotor assembly inertia about its center of mass |
| Initial linear velocity (m/s) | `(0, 0, 0)` | `(0, 0, 0)` |
| Initial angular velocity (rad/s) | `(0, 0, 0)` | `(0, 0, 0)` |

If the simulation models aerodynamic drag separately, set rigid-body linear and angular damping to `0.0`.

Check the scale, body orientation, rotor positions, and joint connections before simulation.

## 5. Add materials and sensors

Assign OmniPBR materials to the visual meshes.

Add cameras and other sensors as children of the body. Match their positions, orientations, and parameters to the hardware.

## 6. Save and register the asset

Save the asset as `starling_2.usd`.

For Pegasus, place the asset in its robot assets directory. Add an entry to the existing `ROBOTS` dictionary in `params.py`:

```python
"My Drone": ROBOTS_ASSETS + "/MyDrone/starling_2.usd"
```

## Rotor layout

Match rotor numbering and spin directions across the USD, Pegasus vehicle configuration, and PX4 airframe.

Example quadrotor layout, viewed from above:

```text
        front
          +X
 rotor2        rotor0
  left          right
   +Y           -Y
 rotor1        rotor3
          -X
         back
```
