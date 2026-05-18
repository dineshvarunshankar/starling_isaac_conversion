# STEP to USD Conversion Guide for UAV Simulation

This guide documents the process of converting a UAV CAD model from a STEP file to a simulation-ready USD asset for use in Isaac Sim and Pegasus Simulator (with PX4 / QGroundControl).

While this guide was developed for the ModalAI Starling 2, **the pipeline applies to any drone or multi-rotor UAV**.

Most approaches online assume simple models with few components. This guide is designed for assemblies with 2000+ components where visual and collision fidelity must be preserved.

**Pipeline overview:**

```
STEP file → Fusion 360 / SolidWorks → Cleaned STEP → Isaac Sim → USD → Blender → Merged USD → Isaac Sim → Physics USD
```

---

## Prerequisites

- Fusion 360 or SolidWorks 2023+
- Isaac Sim (latest)
- Blender 3.x+
- (Optional) Pegasus Simulator + PX4 SITL

---

## A note on Pegasus Simulator

If you intend to use Pegasus Simulator (for PX4 / QGroundControl integration), be aware that **Pegasus enforces strict USD naming and hierarchy requirements**. It references rotor prims, joint prims, and the body prim entirely by name — any deviation will cause the simulator to fail to apply forces or animate rotors. The required structure and naming convention is described in detail in Step 4 and must be followed exactly.

---

## Step 1 — Pre-cleaning in Fusion 360 / SolidWorks

The raw STEP file typically contains components that are not needed for simulation and may have geometry or positioning issues. Clean these up before any conversion.

**Remove unwanted components:**
- Remove propeller guards, protective covers, or any other components not relevant to flight simulation
- Keep only what contributes to mass distribution, collision geometry, or visual fidelity

**Fix mispositioned components:**
- Some CAD files have components mispositioned from their local origin due to export errors
- Use the **Constrain** tool in Fusion 360 (or **Mate** in SolidWorks) to correct positions
- Before editing: break all external references and links to avoid propagating changes to other components sharing the same file

**Unfold propellers:**
- Set propellers to their deployed (unfolded) position using the **Move** tool
- Define the rotation axis and rotate to the correct deployed angle for your drone
- Repeat for all propeller pairs

**Export:**
- Once cleaning is complete, export the assembly as a STEP file

---

## Step 2 — Import into Isaac Sim

Import the cleaned STEP file into Isaac Sim:

1. `File → Import` → select the cleaned STEP file
2. In the import dialog: **uncheck "Enable Instancing"** — instancing prevents proper merging in Blender later
3. Save as USD

> **Note:** Ideally, mesh merging would happen here. However, Isaac Sim's merge tool fails on assemblies of this complexity and throws errors. Use Blender instead (Step 3).

---

## Step 3 — Merge Meshes in Blender

For a quadrotor, the target is **5 merged meshes**: 1 body + 4 rotors (plus any additional sensor geometry). For other configurations, adjust the number of rotor meshes accordingly.

**Import:**
- Open Blender
- `File → Import → USD` → select the Isaac Sim USD

**Align coordinate axes:**
- Before merging, ensure the drone's XYZ orientation matches Blender's XYZ (RGB) axis convention
- This is critical — Isaac Sim uses a specific coordinate convention and misalignment will cause physics and sensor issues downstream

**Merge meshes:**

For each group (body, rotor0, rotor1, rotor2, rotor3):
1. In the Outliner or Viewport, select all meshes belonging to that group
   - `Shift + Click` for multiple selection, or `A` to select all
2. `Ctrl + J` (or `Object → Join`) to merge into one mesh
3. Rename the merged object appropriately — names must match what Pegasus expects (see Step 4)

**Clean up geometry after merging:**

For each merged mesh:
1. Enter Edit Mode → `Tab`
2. Select everything → `A`
3. Merge duplicate vertices → `M` → By Distance
4. Recalculate normals → `Shift + N`
5. Triangulate → `Ctrl + T` (or `Face → Triangulate Faces`)

**Export from Blender:**

`File → Export → USD` with the following settings:
- Apply Modifiers: **ON**
- Export UVs: **ON**
- Normals: **ON**
- Triangulate Meshes: **ON**

---

## Step 4 — Apply Physics in Isaac Sim

Import the merged USD from Blender into Isaac Sim.

### Required USD structure

> **This structure is mandatory for Pegasus Simulator.** Pegasus looks up prims and joints entirely by name using hardcoded paths. The root, body, rotor, and joint names must match exactly as shown below. Using a different structure may work for Isaac Sim alone but will fail silently in Pegasus.

```
World (defaultPrim)
└── <drone_name> (Xform)
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

Naming rules enforced by Pegasus:
- Body prim: must be named `body`
- Rotor prims: must be named `rotor0`, `rotor1`, `rotor2`, `rotor3`
- Mesh inside each rotor Xform: must match the rotor name exactly (e.g. `rotor0`)
- Joints: must be named `joint0`, `joint1`, `joint2`, `joint3` and sit inside their respective rotor Xform

### Physics setup

1. Select the root prim → `Add → Physics → Articulation Root`
2. Select all prims → `Add → Physics → Colliders Preset`
3. For each rotor Xform → `Add → Physics → Rigid Body`
4. For the body Xform → `Add → Physics → Rigid Body` then `Add → Physics → Mass`

### Define joints

For each rotor, select the body prim and the rotor prim together, then:
- `Create → Physics → Joints → Revolute Joint`
- The joint will be created under the rotor Xform
- Total: 4 joints (`joint0` through `joint3`)

### Physical property values

Enter the following values for each link. Always use real-world measurements to reduce the sim-to-real gap. If using for simulation only and real values are unavailable, Pegasus Iris drone values can be used as a starting placeholder.

**Body:**

| Property | Description |
|---|---|
| Mass (kg) |Total drone weight including all rotor assemblies, this is the only mass value set in Isaac Sim (you can remove rotor weights if you add individual rotor mass in physics)|
| Center of Mass (CoM) | XYZ offset from body prim origin — `(0, 0, 0)` for symmetric frames, small Z offset otherwise |
| Ixx, Iyy, Izz (kg·m²) | Diagonal inertia tensor — obtain from CAD physical properties or calculated |
| Linear damping | Set to `0.0` — let aerodynamics handle drag |
| Angular damping | Set to `0.0` — let aerodynamics handle rotational drag |

**Each rotor:**

| Property | Description |
|---|---|
| Ixx, Iyy (kg·m²) | Lateral inertia — small for a rotor disk |
| Izz (kg·m²) | Spin axis inertia — most important value for rotor dynamics |
| Linear velocity | Initial value, typically `(0, 0, 0)` |
| Angular velocity | Initial value, typically `(0, 0, 0)` |
(only if you add separate rotor mass)
| Mass (kg) | Physical weight of one rotor assembly |
| Center of Mass (CoM) | Typically `(0, 0, 0)` in the rotor's local frame |

> To reduce the sim-to-real gap, always prefer measured values.

**Coordinate alignment:**
- Verify the drone's axis orientation matches Isaac Sim's coordinate convention
- This should match the alignment set in Blender — double-check before saving

---

## Step 5 — Optional Additions

**Visual materials:**
- Select any mesh → `Add → Look → OmniPBR`
- Set albedo color or texture for visual realism

**Onboard camera:**
- Select the body prim → `Create → Camera`
- Position and orient to match the physical sensor location on your drone
- Configure resolution, focal length, clipping range, and frame rate

**Additional sensors:**
- Add depth cameras, ToF sensors, LiDARs, IMUs as child prims of the body prim
- Configure each sensor's parameters to match real hardware specs
- Sensor placement relative to the body origin must match the physical drone

---

## Step 6 — Save Final USD

`File → Save` — this is the simulation-ready USD asset.

For use with Pegasus Simulator, place the USD in your assets folder and register it in `params.py`:

```python
ROBOTS = {
    "My Drone": ROBOTS_ASSETS + "/MyDrone/starling_2.usd"
}
```

---

## Rotor layout reference

Rotor numbering and axis convention must be consistent across the USD, Pegasus vehicle config, and PX4 airframe. for example:

```
        front
          +X
 rotor2        rotor0
  left          right
   +Y           -Y
 rotor1        rotor3
          -X
         back
```