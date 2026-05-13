# Starling 2 CAD to Isaac Sim Robot Description Workflow

This document explains how to convert the Starling 2 CAD model into robot description files for Isaac Sim / Isaac Lab simulation.

In this workflow, the robot description is not just one mesh file. It is a small set of files:

```text
Fusion 360 CAD model
  -> per-link USDZ geometry files
  -> one robot USD file with physics and joints
  -> one Isaac Lab Python config for spawning and actuating the robot
```

The final target is Isaac Lab. Isaac Lab loads the robot from USD, then uses Python configuration to define the multirotor actuators, rotor order, rotor directions, and allocation matrix.

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
${PROJECT_ROOT}/assets/starling_2/
  starling_2.usd
  meshes/
    base_link.usdz
    front_left_prop.usdz
    front_right_prop.usdz
    back_left_prop.usdz
    back_right_prop.usdz
  source_stl/
    optional original STL exports used for bounds/debugging
```

The files have different roles:

```text
meshes/*.usdz
  Geometry exported from Fusion.
  These files contain visual meshes and materials.

starling_2.usd
  The actual Isaac Sim robot description.
  It references the USDZ files and adds rigid bodies, collisions, mass, inertia, joints, and articulation metadata.

starling_2.py
  Isaac Lab robot config.
  It points to starling_2.usd and defines multirotor actuator behavior.
```

Example environment variables used in the commands below:

```bash
export PROJECT_ROOT=/path/to/starling_isaac_conversion
export ISAACLAB_ROOT=~/IsaacLab
```

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
${ISAACLAB_ROOT}/isaaclab.sh -p -c "
from isaaclab.app import AppLauncher
app_launcher = AppLauncher(headless=True)
simulation_app = app_launcher.app

from pxr import Usd, UsdGeom

path = '${PROJECT_ROOT}/assets/starling_2/meshes/front_left_prop.usdz'
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

## 6. Convert Starling 2 Coordinates to Isaac Coordinates

Different CAD exports may use different source frames. For this Starling 2 export, the effective source frame was:

```text
source X = left/right
source Y = up
source Z = front/back
source units = millimeters
```

The Isaac target frame is:

```text
target X = forward/back
target Y = left/right
target Z = up
target units = meters
```

The conversion used for the geometry is:

```text
target_x =  source_z * 0.001
target_y = -source_x * 0.001
target_z =  source_y * 0.001
```

Equivalent short form:

```text
target = (source_Z, -source_X, source_Y) * 0.001
```

The `0.001` factor converts millimeters to meters:

```text
1 mm = 0.001 m
```

In the USD creation script, this is applied as a transform on the referenced geometry:

```python
m = Gf.Matrix4d(
    0.0, -0.001, 0.0, 0.0,
    0.0,  0.0,   0.001, 0.0,
    0.001, 0.0,  0.0, 0.0,
    0.0,  0.0,   0.0, 1.0,
)
```

This step is critical. Without it, the robot can appear sideways, collapsed, shifted, or mirrored in Isaac Sim.

## 7. Calculate Rotor Centers

The rotor centers are needed for joints, visual checks, and the multirotor allocation matrix.

For each propeller USDZ, compute the bounding box center in Fusion/source coordinates:

```text
center_source = (min + max) / 2
```

Example for one prop:

```text
min = (-100.145, 1.900, 29.863) mm
max = (-33.874, 20.771, 78.927) mm
```

Calculate each coordinate:

```text
center_source_x = (-100.145 + -33.874) / 2 = -67.010 mm
center_source_y = (1.900 + 20.771) / 2 = 11.336 mm
center_source_z = (29.863 + 78.927) / 2 = 54.395 mm
```

So:

```text
center_source = (-67.010, 11.336, 54.395) mm
```

Apply the Fusion-to-Isaac conversion:

```text
center_target = (source_Z, -source_X, source_Y) * 0.001
center_target = (54.395, 67.010, 11.336) * 0.001
center_target = (0.054395, 0.067010, 0.011336) m
```

Final rotor centers used:

```python
CENTERS = {
    "front_left_prop":  ( 0.054395216,  0.067009726, 0.011335516),
    "front_right_prop": ( 0.053360999, -0.065594356, 0.011335516),
    "back_left_prop":   (-0.054392057,  0.067008565, 0.011335516),
    "back_right_prop":  (-0.054395216, -0.067009726, 0.011335516),
}
```

The signs are useful sanity checks:

```text
front props: x > 0
back props:  x < 0
left props:  y > 0
right props: y < 0
```

## 8. Build the Robot USD

The robot USD is generated with:

```text
${PROJECT_ROOT}/scripts/make_starling_usd_from_usdz.py
```

Run it with Isaac Lab Python:

```bash
${ISAACLAB_ROOT}/isaaclab.sh -p ${PROJECT_ROOT}/scripts/make_starling_usd_from_usdz.py
```

The script writes:

```text
${PROJECT_ROOT}/assets/starling_2/starling_2.usd
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

A mesh by itself is only shape. Isaac Sim also needs physics schemas.

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

For a first-pass simulator inertia, approximate each link as a box:

```text
Ixx = (1/12) * m * (y^2 + z^2)
Iyy = (1/12) * m * (x^2 + z^2)
Izz = (1/12) * m * (x^2 + y^2)
```

Approximate base dimensions:

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
${ISAACLAB_ROOT}/isaaclab.sh -p -c "
from isaaclab.app import AppLauncher
app_launcher = AppLauncher(headless=True)
simulation_app = app_launcher.app

from pxr import Usd, UsdGeom

stage = Usd.Stage.Open('${PROJECT_ROOT}/assets/starling_2/starling_2.usd')
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
${ISAACLAB_ROOT}/isaaclab.sh -p -c "
from isaaclab.app import AppLauncher
app_launcher = AppLauncher(headless=True)
simulation_app = app_launcher.app

from pxr import Usd, UsdPhysics

stage = Usd.Stage.Open('${PROJECT_ROOT}/assets/starling_2/starling_2.usd')

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
${ISAACLAB_ROOT}/source/isaaclab_assets/isaaclab_assets/robots/arl_robot_1.py
```

Use it as the template for:

```text
${ISAACLAB_ROOT}/source/isaaclab_assets/isaaclab_assets/robots/starling_2.py
```

The Starling config must point to the new USD:

```python
usd_path="${PROJECT_ROOT}/assets/starling_2/starling_2.usd"
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
    [-0.053543396, -0.052976705, 0.053611006, 0.053543396],
    [-0.067218193, 0.065842438, -0.067263916, 0.067218193],
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
cp -r ${ISAACLAB_ROOT}/source/isaaclab_tasks/isaaclab_tasks/manager_based/drone_arl/track_position_state_based/config/arl_robot_1 \
      ${ISAACLAB_ROOT}/source/isaaclab_tasks/isaaclab_tasks/manager_based/drone_arl/track_position_state_based/config/starling_2
```

Edit:

```text
${ISAACLAB_ROOT}/source/isaaclab_tasks/isaaclab_tasks/manager_based/drone_arl/track_position_state_based/config/starling_2/no_obstacle_env_cfg.py
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
${ISAACLAB_ROOT}/isaaclab.sh -p -c "
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
${ISAACLAB_ROOT}/isaaclab.sh -p -c "
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
${PROJECT_ROOT}/assets/starling_2/starling_2.usd
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

## 18. Python Files to Keep

From the Python files created during this workflow, keep only the files that are part of the final Isaac USD pipeline or useful for inspection.

Keep:

```text
make_starling_usd_from_usdz.py
```

This is the main generator. It reads the five Fusion-exported USDZ files, creates `starling_2.usd`, references the geometry under the correct link prims, applies the Starling 2 coordinate conversion, creates collision prims, adds rigid-body physics, and creates the fixed joints.

```text
set_starling_mass.py
```

Keep this if mass and inertia assignment is separate from the main USD generation script. It is useful because mass, center of mass, and inertia are values we may tune later without rebuilding the whole geometry pipeline.

```text
view_starling_usd.py
```

Optional, but useful. This opens or frames the generated USD in Isaac Sim for visual inspection. Keep it if you want a quick way to check whether the robot is visible, correctly scaled, and oriented correctly.

```text
check_stl_bounds.py
```

Optional diagnostic file. This was useful for understanding the original CAD/STL coordinate frame and scale. It is not required for the final USDZ-based workflow, but it is worth keeping if you want a record of how the Starling 2 source-frame conversion was derived.

Ignore or delete:

```text
convert_starling_stl_to_usd.py
```

This belongs to the older STL-based path. The final workflow uses Fusion-exported USDZ files, so this is no longer needed.

```text
make_starling_usd_from_usdz_old.py
```

This is an older version of the current USDZ generator. Once `make_starling_usd_from_usdz.py` works, the old copy is not needed.

```text
make_starling_usd.py
```

This was part of an earlier approach before the USDZ-based pipeline was finalized. If it does not contain anything newer than `make_starling_usd_from_usdz.py`, ignore or delete it.

Final files that must remain for Isaac Lab:

```text
${PROJECT_ROOT}/assets/starling_2/starling_2.usd
${PROJECT_ROOT}/assets/starling_2/meshes/*.usdz
${PROJECT_ROOT}/scripts/make_starling_usd_from_usdz.py
${PROJECT_ROOT}/scripts/set_starling_mass.py
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

## 20. Why Fusion Combine Was Not the Main Path

Fusion Combine sounds attractive because it seems like each prop group could be merged into one body before export. In practice, it caused more problems than it solved.

The CAD model contains many nested parts. Some prop groups had large numbers of bodies, tiny overlapping faces, linked/external components, and occurrence transforms from the Fusion assembly tree.

The main failure modes were:

- Fusion's boolean kernel struggled with very large combine operations.
- Coincident or nearly coincident faces caused combine errors.
- Linked components caused instance and external-reference issues.
- Moving bodies out of nested occurrences could reinterpret their transforms.
- Parts could shift, stack, collapse, or appear in the wrong coordinate space.

The solution was to avoid boolean merging. We used Fusion only to make link-level groups and export them as USDZ. The robot structure was then authored in USD, where Isaac Sim actually needs it.

## 21. Why We Did Not Use Fusion2URDF

`fusion2urdf` was not used because it expects the Fusion assembly to already be organized like a clean robot model:

- one component per link,
- no nested component trees inside each link,
- a valid `base_link`,
- supported joints,
- correct parent/child joint structure,
- geometry that can be exported without transform or instance problems.

The Starling CAD model did not satisfy those assumptions. A prop group still expanded into motor parts, propeller blades, screws, nuts, and nested child components. Making it compatible would have required flattening or combining the model inside Fusion, which is exactly where the instance errors, external reference problems, and coordinate collapse happened.

Also, the final target is Isaac Sim / Isaac Lab, which uses USD directly. The cleanest path was therefore:

```text
Fusion grouped CAD
  -> USDZ geometry files
  -> Isaac robot USD
  -> Isaac Lab MultirotorCfg
```

That path keeps Fusion responsible for geometry export and keeps Isaac responsible for simulation structure.
