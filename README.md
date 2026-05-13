# Starling 2 CAD to Isaac Sim Robot Description Workflow

*(Note: The final simulation-ready `starling_2.usd` asset and original source STEP CAD files can be downloaded directly from [Google Drive](https://drive.google.com/drive/folders/1k4Sfebg8j9LJh4NXsCWhVzftJGb4_1UY?usp=sharing)).*

This document explains how to prepare the ModalAI Starling 2 CAD model and convert it into a fully functional robot simulation asset for Isaac Sim and Isaac Lab.

The conversion workflow is broken down into three straightforward steps:

1. **CAD Export:** Export the visual and collision meshes from Fusion 360 as standard `.usdz` files.
2. **USD Generation:** Run the provided Python script to compile the individual meshes into a single self-contained `starling_2.usd` asset with all mass properties and fixed joints applied.
3. **Isaac Lab Setup:** Reference the generated USD file inside an Isaac Lab Python configuration class to define the multirotor actuators and control allocation matrix.

## 1. What We Are Building

Isaac Sim needs to know more than what the robot looks like. For simulation, the robot description must answer these questions:

- What are the rigid bodies?
- Where is the visible geometry for each rigid body?
- Which bodies collide with the world?
- What is the mass and inertia of each body?
- How are the bodies connected?
- Which bodies are thrusters in Isaac Lab?

For Starling 2, we model the robot as five rigid links:

```text
base_link
front_left_prop
front_right_prop
back_left_prop
back_right_prop
```

Each prop link is treated as one rigid motor/propeller/screw/nut group. The propeller blade rotation is not modeled as a revolute joint. Isaac Lab applies thrust to the named prop bodies through its multirotor actuator model.

## 2. Final File Structure

Use a layout like this:

```text
assets/starling_2/
  starling_2.usd           # Fully self-contained monolithic OpenUSD robot asset
  meshes/
    base_link.usdz         # Source geometry exports from Fusion 360
    front_left_prop.usdz
    front_right_prop.usdz
    back_left_prop.usdz
    back_right_prop.usdz
```

The files in this repository have the following roles:

| File | Role |
| :--- | :--- |
| **`README.md`** | Instructions for CAD preparation, coordinate conversion, and Isaac Lab setup. |
| **`scripts/make_starling_usd_from_usdz.py`** | Builds and flattens `starling_2.usd` into a self-contained single file asset with embedded physics and joints. |
| **`scripts/set_starling_mass.py`** | Updates mass, center of mass, and inertia parameters on an existing USD stage. |
| **`scripts/view_starling_usd.py`** | Loads `starling_2.usd` in Isaac Sim for visual inspection. |


## 3. Load the CAD Model in Fusion 360

Start with the Starling 2 STEP/CAD assembly in Fusion 360.

After loading, inspect the model as an assembly, not as one solid part. The imported model contains many nested components: frame parts, electronics, motors, propeller blades, screws, nuts, and other small pieces.

For simulation, we do not need every screw to become a separate simulated body. We only need rigid groups that match how the robot moves in Isaac Lab.

The target grouping is:

```text
base_link_assembly
propeller_1
propeller_2
propeller_3
propeller_4
```

Map those Fusion groups to Isaac link names:

```text
base_link_assembly -> base_link
propeller_1        -> front_left_prop
propeller_2        -> back_left_prop
propeller_3        -> back_right_prop
propeller_4        -> front_right_prop
```

The important rule is simple: each group should contain everything that moves as one rigid body in simulation. The group does not need to be one combined Fusion body.

## 4. Export One USDZ Per Rigid Link

Export each rigid group from Fusion as USDZ:

```text
base_link_assembly.usdz
propeller_1.usdz
propeller_2.usdz
propeller_3.usdz
propeller_4.usdz
```

Place them under `assets/starling_2/meshes/` using the Isaac link names:

```text
base_link.usdz
front_left_prop.usdz
back_left_prop.usdz
back_right_prop.usdz
front_right_prop.usdz
```

Why USDZ here:

- Fusion can export geometry-rich USDZ files.
- USDZ preserves the visual meshes better than trying to reference STL directly from USD.
- The USDZ files are used only as geometry inputs.
- Physics is added later in the top-level robot USD.

## 5. Verify the Exported USDZ Files

Before building the robot USD, verify that each USDZ file actually contains mesh points.

Use Isaac Lab's Python environment:

```bash
~/IsaacLab/isaaclab.sh -p -c "
from isaaclab.app import AppLauncher
app_launcher = AppLauncher(headless=True)
simulation_app = app_launcher.app

from pxr import Usd, UsdGeom

path = 'assets/starling_2/meshes/front_left_prop.usdz'
stage = Usd.Stage.Open(path)

print('opened:', bool(stage))
print('defaultPrim:', stage.GetDefaultPrim().GetPath() if stage and stage.GetDefaultPrim() else None)

meshes = 0
points_total = 0
for prim in stage.Traverse():
    if prim.GetTypeName() == 'Mesh':
        meshes += 1
        pts = UsdGeom.Mesh(prim).GetPointsAttr().Get()
        points_total += 0 if pts is None else len(pts)

print('mesh_count:', meshes)
print('points_total:', points_total)

simulation_app.close()
"
```

Expected:

```text
opened: True
mesh_count: greater than 0
points_total: greater than 0
```

If `points_total` is zero, the file is not useful as geometry. This was the problem with directly referencing STL files from USD: the USD stage could reference the file path, but there were no USD mesh points available for Isaac to render and simulate properly.

## 6. Convert CAD Coordinates to Simulation Coordinates

> [!NOTE]
> **Pre-coded in scripts:** The conversions below are already hardcoded into `scripts/make_starling_usd_from_usdz.py`. You do not need to apply these transformations manually.

The original CAD exports define axes differently than the simulation target. The effective source frame of the raw CAD exports is:

```text
source X = left/right (negative values = left side)
source Y = up
source Z = front/back
source units = millimeters
```

The standard simulation target frame (Forward-Left-Up) requires:

```text
target X = forward/back
target Y = left/right (positive values = left side)
target Z = up
target units = meters
```

To map the CAD geometry into the simulation frame, the script applies the following conversion:

```text
target_x =  source_z * 0.001
target_y = -source_x * 0.001
target_z =  source_y * 0.001
```

*(Note: `target_y` uses a negative sign because the source CAD files define the left side using negative values, whereas the simulation target frame requires positive values for the left axis).*

In the generator script, this mapping is authored as a 4x4 matrix transform on the referenced geometry:

```python
m = Gf.Matrix4d(
    0.0, -0.001, 0.0, 0.0,
    0.0,  0.0,   0.001, 0.0,
    0.001, 0.0,  0.0, 0.0,
    0.0,  0.0,   0.0, 1.0,
)
```

## 7. Pre-Calculated Rotor Centers

> [!NOTE]
> **Pre-coded in scripts:** The final rotor centers are already measured and hardcoded into the `CENTERS` dictionary in the generation script. They determine joint placements and the control allocation matrix.

To determine where the propeller links connect to the base frame, spatial extents were measured directly from the raw CAD source geometry. 

Applying the conversion formula to the measured CAD origins yields the final simulation centers in meters:

```python
CENTERS = {
    "front_left_prop":  ( 0.054395216,  0.067009726, 0.011335516),
    "front_right_prop": ( 0.053360999, -0.065594356, 0.011335516),
    "back_left_prop":   (-0.054392057,  0.067008565, 0.011335516),
    "back_right_prop":  (-0.054395216, -0.067009726, 0.011335516),
}
```

The resulting signs verify correct physical placement in the simulation target frame:

```text
front props: x > 0
back props:  x < 0
left props:  y > 0
right props: y < 0
```

## 8. Build the Robot USD

Before compiling the robot USD stage, ensure you have completed the following prerequisites:

1. **Activate Environment:** Activate your Isaac Lab/sim conda environment:
   ```bash
   conda activate env_isaaclab
   ```
2. **Verify Mesh Placement:** Ensure the five exported `.usdz` component files are positioned inside the target asset directory:
   ```text
   assets/starling_2/meshes/
     base_link.usdz
     front_left_prop.usdz
     front_right_prop.usdz
     back_left_prop.usdz
     back_right_prop.usdz
   ```

Once the files are in place, navigate to the repository root directory and compile the master stage file by running the generator script:

```bash
~/IsaacLab/isaaclab.sh -p scripts/make_starling_usd_from_usdz.py
```

The script dynamically resolves local file paths and exports the flattened standalone asset directly into:

```text
assets/starling_2/starling_2.usd
```

To visually inspect the final compiled asset inside the Isaac Sim stage viewer GUI, run:

```bash
~/IsaacLab/isaaclab.sh -p scripts/view_starling_usd.py
```

The script should create this prim structure:

```text
/starling_2
  /base_link
    /visuals
    /collisions
  /front_left_prop
    /visuals
    /collisions
  /front_right_prop
    /visuals
    /collisions
  /back_left_prop
    /visuals
    /collisions
  /back_right_prop
    /visuals
    /collisions
  /joints
    /base_link_to_front_left_prop
    /base_link_to_front_right_prop
    /base_link_to_back_left_prop
    /base_link_to_back_right_prop
```

The geometry under each `visuals` prim references the corresponding USDZ file. The geometry under each `collisions` prim can reference the same geometry, but should have collision APIs applied and can be hidden from rendering.

## 9. Add Physics Meaning to the USD

A mesh by itself is only shape. Isaac Sim also needs physics schemas to simulate rigid body dynamics. `scripts/make_starling_usd_from_usdz.py` applies these properties directly to the prims in the USD file.

Apply these APIs to `base_link`:

```text
PhysicsRigidBodyAPI
PhysicsMassAPI
PhysicsArticulationRootAPI
PhysxArticulationAPI
```

Apply these APIs to each prop link:

```text
PhysicsRigidBodyAPI
PhysicsMassAPI
```

Apply this API to collision geometry:

```text
PhysicsCollisionAPI
```

Create four fixed joints:

```text
PhysicsFixedJoint
```

The prop links are fixed to `base_link` because the Starling is simulated as a multirotor with thrust applied at the prop bodies. We are not simulating motor shaft rotation or blade spinning as articulated motion.

## 10. Assign Mass and Inertia

*(Note: The mass and inertia values derived below are hardcoded directly inside `scripts/make_starling_usd_from_usdz.py` and are assigned automatically during stage generation).*

The ModalAI Starling 2 datasheet lists:

```text
takeoff weight: 285 g
diagonal size: 230 mm
motors: 1504 3000kv
propellers: 120 mm
frame: 3 mm carbon fiber
```

Reference: [ModalAI Starling 2 datasheet](https://docs.modalai.com/starling-2-datasheet/)

Use a rounded total mass:

```text
total mass = 0.300 kg
```

Split the mass into one main body and four prop/motor groups:

```text
base_link:        0.240 kg
front_left_prop:  0.015 kg
front_right_prop: 0.015 kg
back_left_prop:   0.015 kg
back_right_prop:  0.015 kg
```

Check:

```text
0.240 + 4 * 0.015 = 0.300 kg
```

### Inertia Calculation

*(Formula represents the standard mass moment of inertia for a uniform solid box rotating around its center of mass).*

For a first-pass simulator inertia, approximate each link as a box:

```text
Ixx = (1/12) * m * (y^2 + z^2)
Iyy = (1/12) * m * (x^2 + z^2)
Izz = (1/12) * m * (x^2 + y^2)
```

Approximate base dimensions *(measured directly from the outer bounding box extents of the `base_link` CAD geometry)*:

```text
x = 0.151 m
y = 0.194 m
z = 0.086 m
m = 0.240 kg
```

Example `Ixx` calculation:

```text
Ixx = (1/12) * 0.240 * (0.194^2 + 0.086^2)
Ixx = 0.020 * (0.037636 + 0.007396)
Ixx = 0.020 * 0.045032
Ixx = 0.00090064 kg*m^2
Ixx ≈ 9.0e-4 kg*m^2
```

Used inertia values:

```text
base_link:      (9.0e-4, 6.0e-4, 1.2e-3) kg*m^2
each prop link: (6.0e-6, 3.5e-6, 8.5e-6) kg*m^2
```

These are approximate but stable first-pass values. Replace them later with measured CAD inertia if available.

## 11. Verify Robot USD Bounds

After generating the robot USD, verify that the geometry is the right size and in the right quadrants.

```bash
~/IsaacLab/isaaclab.sh -p -c "
from isaaclab.app import AppLauncher
app_launcher = AppLauncher(headless=True)
simulation_app = app_launcher.app

from pxr import Usd, UsdGeom

stage = Usd.Stage.Open('assets/starling_2/starling_2.usd')
cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render', 'proxy'])

for p in [
    '/starling_2/base_link',
    '/starling_2/front_left_prop',
    '/starling_2/front_right_prop',
    '/starling_2/back_left_prop',
    '/starling_2/back_right_prop',
]:
    prim = stage.GetPrimAtPath(p)
    box = cache.ComputeWorldBound(prim).ComputeAlignedBox()
    print('\\n', p)
    print(' center:', (box.GetMin() + box.GetMax()) * 0.5)
    print(' size:', box.GetSize())

simulation_app.close()
"
```

Expected approximate result:

```text
base_link size: about 0.15 x 0.19 x 0.09 m
prop centers: around +/-0.054 m and +/-0.067 m
prop z: about 0.011 m
```

## 12. Verify Fixed Joints

Check that each prop is connected to `base_link`:

```bash
~/IsaacLab/isaaclab.sh -p -c "
from isaaclab.app import AppLauncher
app_launcher = AppLauncher(headless=True)
simulation_app = app_launcher.app

from pxr import Usd, UsdPhysics

stage = Usd.Stage.Open('assets/starling_2/starling_2.usd')

for name in ['front_left_prop','front_right_prop','back_left_prop','back_right_prop']:
    path = f'/starling_2/joints/base_link_to_{name}'
    joint = UsdPhysics.FixedJoint(stage.GetPrimAtPath(path))
    print('\\n', path)
    print('body0:', joint.GetBody0Rel().GetTargets())
    print('body1:', joint.GetBody1Rel().GetTargets())
    print('localPos0:', joint.GetLocalPos0Attr().Get())
    print('localPos1:', joint.GetLocalPos1Attr().Get())
    print('collisionEnabled:', joint.GetCollisionEnabledAttr().Get())

simulation_app.close()
"
```

Expected:

```text
body0: /starling_2/base_link
body1: /starling_2/<prop_link>
localPos1: (0, 0, 0)
collisionEnabled: False
```

## 13. Create the Isaac Lab Robot Config

The lab already had a working multirotor robot config:

```text
~/IsaacLab/source/isaaclab_assets/isaaclab_assets/robots/arl_robot_1.py
```

Use it as the template for:

```text
~/IsaacLab/source/isaaclab_assets/isaaclab_assets/robots/starling_2.py
```

The Starling config must point to the new USD:

```python
usd_path="assets/starling_2/starling_2.usd"
```

Define the thrusters:

```python
STARLING_2_THRUSTER = ThrusterCfg(
    thrust_range=(0.1, 10.0),
    thrust_const_range=(9.26312e-06, 1.826312e-05),
    tau_inc_range=(0.05, 0.08),
    tau_dec_range=(0.005, 0.005),
    torque_to_thrust_ratio=0.07,
    thruster_names_expr=[
        "back_left_prop",
        "back_right_prop",
        "front_left_prop",
        "front_right_prop",
    ],
)
```

Then connect it to the robot config:

```python
actuators={"thrusters": STARLING_2_THRUSTER}
```

Do not leave the old template actuator variable in place.

## 14. Allocation Matrix

Isaac Lab needs a matrix that maps rotor thrusts to body force and body moments.

The column order used here is:

```text
back_left_prop
back_right_prop
front_left_prop
front_right_prop
```

Each rotor mainly produces vertical force, so the force rows are:

```text
Fx row = 0, 0, 0, 0
Fy row = 0, 0, 0, 0
Fz row = 1, 1, 1, 1
```

Moment contribution comes from the rotor position relative to the body frame. For a rotor at:

```text
r = (x, y, z)
```

and upward thrust:

```text
F = (0, 0, T)
```

the basic cross product is:

```text
moment = r x F
Mx =  y * T
My = -x * T
Mz = motor_reaction_torque
```

The final signs must match the Isaac Lab body-frame convention and the rotor order from the existing multirotor template.

The matrix used:

```python
allocation_matrix=[
    [0.0, 0.0, 0.0, 0.0],
    [0.0, 0.0, 0.0, 0.0],
    [1.0, 1.0, 1.0, 1.0],
    [0.067008565, -0.067009726, 0.067009726, -0.065594356],
    [0.054392057, 0.054395216, -0.054395216, -0.053360999],
    [-0.07, 0.07, -0.07, 0.07],
]
```

The last row uses alternating signs because adjacent rotors spin in opposite directions:

```text
rotor_directions = [1, -1, 1, -1]
torque_to_thrust_ratio = 0.07
```

## 15. Register the Starling Task

Copy the existing ARL task config:

```bash
cp -r ~/IsaacLab/source/isaaclab_tasks/isaaclab_tasks/manager_based/drone_arl/track_position_state_based/config/arl_robot_1 \
      ~/IsaacLab/source/isaaclab_tasks/isaaclab_tasks/manager_based/drone_arl/track_position_state_based/config/starling_2
```

Edit:

```text
~/IsaacLab/source/isaaclab_tasks/isaaclab_tasks/manager_based/drone_arl/track_position_state_based/config/starling_2/no_obstacle_env_cfg.py
```

Change the robot import:

```python
from isaaclab_assets.robots.starling_2 import STARLING_2_CFG
```

Set the scene robot:

```python
self.scene.robot = STARLING_2_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")
```

Edit:

```text
config/starling_2/__init__.py
```

Use task IDs:

```python
id="Isaac-TrackPositionNoObstacles-Starling-2-v0"
id="Isaac-TrackPositionNoObstacles-Starling-2-Play-v0"
```

## 16. Test the Isaac Lab Config

Check that the robot config imports:

```bash
~/IsaacLab/isaaclab.sh -p -c "
from isaaclab.app import AppLauncher
app_launcher = AppLauncher(headless=True)
simulation_app = app_launcher.app

from isaaclab_assets.robots.starling_2 import STARLING_2_CFG

print('USD:', STARLING_2_CFG.spawn.usd_path)
print('thrusters:', STARLING_2_CFG.actuators['thrusters'].thruster_names_expr)
print('rotor_directions:', STARLING_2_CFG.rotor_directions)
print('allocation_matrix:', STARLING_2_CFG.allocation_matrix)

simulation_app.close()
"
```

Expected:

```text
thrusters: ['back_left_prop', 'back_right_prop', 'front_left_prop', 'front_right_prop']
rotor_directions: [1, -1, 1, -1]
```

Check that the task registers:

```bash
~/IsaacLab/isaaclab.sh -p -c "
from isaaclab.app import AppLauncher
app_launcher = AppLauncher(headless=True)
simulation_app = app_launcher.app

import gymnasium as gym
import isaaclab_tasks
import isaaclab_tasks.manager_based.drone_arl.track_position_state_based.config.starling_2

env_id = 'Isaac-TrackPositionNoObstacles-Starling-2-Play-v0'
print('registered:', env_id in gym.registry)
print(gym.spec(env_id))

simulation_app.close()
"
```

Expected:

```text
registered: True
```

## 17. Visual Inspection in Isaac Sim

Open:

```text
assets/starling_2/starling_2.usd
```

Inspect:

- The robot is visible.
- The robot is not sideways.
- The props are in the correct quadrants.
- The scale looks like a small drone, not a huge model.
- Collision geometry is hidden or visually distinguishable.
- The Stage tree contains `/starling_2` and all five links.

If the robot appears in the Stage tree but not in the viewport:

1. Select `/starling_2`.
2. Press `F` to frame selection.
3. If only bounds show, check the mesh references and material visibility.

If the robot appears with random colors, Fusion materials are still active. For debugging, bind stronger debug materials directly to the mesh prims or hide collision meshes.

## 18. Python Files Overview

As noted in Section 2, the main scripts for this workflow are:

* **`make_starling_usd_from_usdz.py`**: Generates the USD file, applies coordinate transforms, sets initial mass values, and defines fixed joints.
* **`set_starling_mass.py`**: Optional script to update physical properties on an existing stage.
* **`view_starling_usd.py`**: Script to open and inspect the generated USD file in Isaac Sim.

Final required output files for Isaac Lab integration:

```text
assets/starling_2/starling_2.usd
assets/starling_2/meshes/*.usdz
scripts/make_starling_usd_from_usdz.py
scripts/set_starling_mass.py
```

## 19. Final Checklist

Before using the asset for training or simulation, verify:

- `starling_2.usd` opens in Isaac Sim.
- `/starling_2` is the default prim.
- Geometry is visible.
- Dimensions are in meters.
- Props are in the right quadrants.
- `base_link` has articulation root APIs.
- Each prop link has rigid body and mass APIs.
- Four fixed joints exist.
- Total mass is about `0.300 kg`.
- `STARLING_2_CFG` imports.
- Starling task ID registers.

## 20. Technical Note: CAD Boolean Operations

Merging sub-assemblies into single solid bodies using CAD boolean tools (such as Fusion 360's Combine feature) is simple and highly effective for models like the Starling 2 if you do not need to preserve individual hardware components (such as internal screws, nuts, and circuit boards).

However, if your simulation requires retaining distinct internal components, combining can trigger geometry kernel errors:

- Overlapping or coincident faces between small hardware items cause boolean failures.
- Linked external components lose their assembly reference paths.
- Flattening nested sub-assemblies can break local origin transformations during export.

Exporting uncombined `.usdz` component groups preserves the individual raw bodies without triggering boolean errors.

## 21. Technical Note: URDF Exporter Compatibility

Standard CAD-to-URDF plugins require a flat assembly tree where each physical link is a single solid component with predefined joint origins. 

Because the Starling assembly uses nested sub-components for motors and hardware, converting it to URDF requires destructive CAD flattening that triggers the coordinate shifting issues noted in Section 20. Natively exporting USDZ meshes and defining the rigid body hierarchy directly in OpenUSD avoids CAD restructuring.
