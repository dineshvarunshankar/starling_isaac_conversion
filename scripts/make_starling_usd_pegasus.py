"""
Pegasus Simulator compatible USD builder for Starling 2.

Generates starling_2_pegasus.usd with:
  - /body             (main chassis, articulation root)
  - /rotor0..rotor3   (prop links with revolute joints)
  - joint0..joint3    (revolute joints around local Z for prop spin animation)

Pegasus expects:
  - Body prim named "/body"
  - Rotor prims named "/rotor0" through "/rotor3"
  - Revolute joints named "joint0" through "joint3"
  - Forces applied via apply_force([0,0,Fz], body_part="/rotor{i}")
  - Rolling moment torque applied to "/body"

Rotor ordering follows PX4 standard quadrotor X frame:
  rotor0 = front_right (CW)
  rotor1 = back_left   (CW)
  rotor2 = front_left  (CCW)
  rotor3 = back_right  (CCW)

Run:
  ~/IsaacLab/isaaclab.sh -p scripts/make_starling_usd_pegasus.py
"""

from isaaclab.app import AppLauncher

app_launcher = AppLauncher(headless=True)
simulation_app = app_launcher.app

from pathlib import Path
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Sdf, Gf

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = REPO_ROOT / "assets" / "starling_2"
MESH_DIR = ASSET_DIR / "meshes"
USD_PATH = ASSET_DIR / "starling_2_pegasus.usd"

MESH_FILES = {
    "body": "base_link.usdz",
    "rotor0": "front_right_prop.usdz",
    "rotor1": "back_left_prop.usdz",
    "rotor2": "front_left_prop.usdz",
    "rotor3": "back_right_prop.usdz",
}

# Real-world physical dimensions measured from Starling 2 hardware:
# X (front/back center-to-center) = 132 mm -> +/- 0.066 m
# Y (left/right center-to-center) = 176 mm -> +/- 0.088 m
# Z (bottom plane to rotor top) = 50.75 mm -> +0.05075 m
#
# PX4 quadrotor X frame rotor mapping:
#   rotor0 = front_right  (+X, -Y)
#   rotor1 = back_left    (-X, +Y)
#   rotor2 = front_left   (+X, +Y)
#   rotor3 = back_right   (-X, -Y)
CENTERS = {
    "rotor0": Gf.Vec3f( 0.066, -0.088, 0.05075),  # front_right
    "rotor1": Gf.Vec3f(-0.066,  0.088, 0.05075),  # back_left
    "rotor2": Gf.Vec3f( 0.066,  0.088, 0.05075),  # front_left
    "rotor3": Gf.Vec3f(-0.066, -0.088, 0.05075),  # back_right
}

# Configuration: Choose between Daytime (310g) or Nighttime (410g) payload
# Daytime: Body Mass = 0.250 kg | Nighttime: Body Mass = 0.350 kg
BODY_MASS = 0.250


def add_rigid_body(stage, path, mass, inertia, articulation_root=False, translate=None):
    prim = stage.DefinePrim(path, "Xform")
    if translate is not None:
        UsdGeom.Xformable(prim).AddTranslateOp().Set(translate)

    UsdPhysics.RigidBodyAPI.Apply(prim)
    mass_api = UsdPhysics.MassAPI.Apply(prim)
    mass_api.CreateMassAttr(float(mass))
    mass_api.CreateDiagonalInertiaAttr(Gf.Vec3f(*inertia))
    mass_api.CreatePrincipalAxesAttr(Gf.Quatf(1.0, 0.0, 0.0, 0.0))

    if articulation_root:
        UsdPhysics.ArticulationRootAPI.Apply(prim)
        PhysxSchema.PhysxArticulationAPI.Apply(prim).CreateEnabledSelfCollisionsAttr(False)

    return prim


def reference_usdz(stage, prim_path, rel_asset_path, center=None):
    prim = stage.DefinePrim(prim_path, "Xform")

    # Source USDZ: X left/right, Y up, Z front/back, mm.
    # Target Isaac: X forward, Y left, Z up, meters.
    m = Gf.Matrix4d(
        0.0,  0.001, 0.0, 0.0,
        0.0,  0.0,   0.001, 0.0,
        0.001, 0.0,  0.0, 0.0,
        0.0,  0.0,   0.0, 1.0,
    )

    if center is not None:
        m.SetTranslateOnly(Gf.Vec3d(-center[0], -center[1], -center[2]))

    UsdGeom.Xformable(prim).AddTransformOp().Set(m)
    prim.GetReferences().AddReference(rel_asset_path)
    return prim


def apply_collision_to_meshes(stage, root_path):
    root = stage.GetPrimAtPath(root_path)
    if not root:
        return 0
    count = 0
    for prim in Usd.PrimRange(root):
        if prim.GetTypeName() == "Mesh":
            UsdPhysics.CollisionAPI.Apply(prim)
            count += 1
    return count


def set_color(stage, path, rgb):
    prim = stage.GetPrimAtPath(path)
    if prim:
        UsdGeom.PrimvarsAPI(prim).CreatePrimvar("displayColor", Sdf.ValueTypeNames.Color3fArray).Set([Gf.Vec3f(*rgb)])


def add_revolute_joint(stage, joint_name, parent_path, child_path, pos):
    """Create a revolute joint spinning around the local Z-axis (prop spin axis)."""
    joint_path = f"{child_path}/{joint_name}"
    joint = UsdPhysics.RevoluteJoint.Define(stage, joint_path)
    joint.CreateBody0Rel().SetTargets([Sdf.Path(parent_path)])
    joint.CreateBody1Rel().SetTargets([Sdf.Path(child_path)])
    joint.CreateAxisAttr("Z")
    joint.CreateLocalPos0Attr(pos)
    joint.CreateLocalPos1Attr(Gf.Vec3f(0.0, 0.0, 0.0))
    joint.CreateLocalRot0Attr(Gf.Quatf(1.0, 0.0, 0.0, 0.0))
    joint.CreateLocalRot1Attr(Gf.Quatf(1.0, 0.0, 0.0, 0.0))
    joint.CreateCollisionEnabledAttr(False)

    # No joint limits — free spinning propeller
    joint.CreateLowerLimitAttr(-1e10)
    joint.CreateUpperLimitAttr(1e10)

    return joint


# ── Build the stage ──────────────────────────────────────────────────────────

ASSET_DIR.mkdir(parents=True, exist_ok=True)

stage = Usd.Stage.CreateNew(str(USD_PATH))
UsdGeom.SetStageMetersPerUnit(stage, 1.0)
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)

root = UsdGeom.Xform.Define(stage, "/starling_2")
stage.SetDefaultPrim(root.GetPrim())

# ── Body (main chassis) ─────────────────────────────────────────────────────
# Inertia derived from uniform box bounds: 0.14m x 0.18m x 0.07685m
add_rigid_body(stage, "/starling_2/body", BODY_MASS, (8.0e-4, 5.3e-4, 1.1e-3), articulation_root=True)
UsdGeom.Xform.Define(stage, "/starling_2/body/visuals")
UsdGeom.Xform.Define(stage, "/starling_2/body/collisions")
set_color(stage, "/starling_2/body/visuals", (0.1, 0.1, 0.1))
reference_usdz(stage, "/starling_2/body/visuals/body_asset", "./meshes/base_link.usdz")
reference_usdz(stage, "/starling_2/body/collisions/body_asset", "./meshes/base_link.usdz")
apply_collision_to_meshes(stage, "/starling_2/body/collisions/body_asset")

# ── Rotors (with revolute joints) ───────────────────────────────────────────
for rotor_name, center in CENTERS.items():
    rotor_path = f"/starling_2/{rotor_name}"
    mesh_file = MESH_FILES[rotor_name]

    add_rigid_body(stage, rotor_path, 0.015, (6.0e-6, 3.5e-6, 8.5e-6), translate=center)
    UsdGeom.Xform.Define(stage, f"{rotor_path}/visuals")
    UsdGeom.Xform.Define(stage, f"{rotor_path}/collisions")

    # Color coding: Blue for front props (rotor0, rotor2), Red for back props (rotor1, rotor3)
    color = (0.0, 0.4, 1.0) if rotor_name in ["rotor0", "rotor2"] else (1.0, 0.2, 0.2)
    set_color(stage, f"{rotor_path}/visuals", color)

    reference_usdz(stage, f"{rotor_path}/visuals/{rotor_name}_asset", f"./meshes/{mesh_file}", center=center)
    reference_usdz(stage, f"{rotor_path}/collisions/{rotor_name}_asset", f"./meshes/{mesh_file}", center=center)
    apply_collision_to_meshes(stage, f"{rotor_path}/collisions/{rotor_name}_asset")

    # Revolute joint: "joint0" for "rotor0", nested inside rotor prim
    joint_name = rotor_name.replace("rotor", "joint")
    add_revolute_joint(stage, joint_name, "/starling_2/body", rotor_path, center)

# ── Save as a single flattened file ──────────────────────────────────────────
stage.GetRootLayer().Save()
flat_layer = stage.Flatten()
flat_layer.Export(str(USD_PATH))
print("Wrote flattened Pegasus-compatible asset to", USD_PATH)

simulation_app.close()
