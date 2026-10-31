"""Validation, normalisation and GLB export of InstantMesh OBJ output."""
from pathlib import Path

import numpy as np
import trimesh

# Cyclic axis permutation (x, y, z) -> (y, z, x): turns InstantMesh's Z-up
# output into glTF's Y-up convention. It is a proper rotation, so face
# winding and normals are preserved. Matches the official InstantMesh app.
_Z_UP_TO_Y_UP = np.array([[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0], [0, 0, 0, 1]], dtype=float)


class MeshError(Exception):
    pass


def _visual_kind(mesh: trimesh.Trimesh) -> str:
    """'vertex', 'face', 'texture' (only with an actual image) or 'none'."""
    kind = mesh.visual.kind
    if kind == "texture":
        material = mesh.visual.material
        has_image = getattr(material, "image", None) is not None or getattr(material, "baseColorTexture", None) is not None
        return "texture" if has_image else "none"
    return kind or "none"


def _summarise(meshes: list[trimesh.Trimesh]) -> dict:
    bounds = np.array([mesh.bounds for mesh in meshes])
    low, high = bounds[:, 0].min(axis=0), bounds[:, 1].max(axis=0)
    return {"vertices": int(sum(len(mesh.vertices) for mesh in meshes)),
            "faces": int(sum(len(mesh.faces) for mesh in meshes)),
            "bounds_min": low.round(6).tolist(), "bounds_max": high.round(6).tolist(),
            "dimensions": (high - low).round(6).tolist()}


def load_and_prepare(source: Path, convert_z_up: bool, max_faces: int) -> tuple[list[trimesh.Trimesh], dict]:
    """Load and validate an OBJ, remove degenerate geometry, then centre and scale it."""
    try:
        # process=False keeps vertex order so per-vertex colours stay aligned.
        loaded = trimesh.load(source, force="scene", process=False)
    except Exception as exc:
        raise MeshError("The generated OBJ could not be parsed.") from exc
    meshes = [geometry for geometry in loaded.geometry.values() if isinstance(geometry, trimesh.Trimesh)]
    meshes = [mesh for mesh in meshes if len(mesh.vertices) and len(mesh.faces)]
    if not meshes:
        raise MeshError("The generated mesh contains no vertices or faces.")
    for mesh in meshes:
        if not np.isfinite(mesh.vertices).all():
            raise MeshError("The generated mesh has non-finite vertex coordinates.")
        if mesh.faces.min() < 0 or mesh.faces.max() >= len(mesh.vertices):
            raise MeshError("The generated mesh has out-of-range face indices.")
    original = _summarise(meshes)
    if original["faces"] > max_faces:
        raise MeshError(f"The generated mesh has {original['faces']:,} faces, above the {max_faces:,} face limit for the viewer.")

    removed_faces = 0
    for mesh in meshes:
        keep = mesh.nondegenerate_faces()
        removed_faces += int((~keep).sum())
        if not keep.all():
            mesh.update_faces(keep)
        mesh.remove_unreferenced_vertices()
    meshes = [mesh for mesh in meshes if len(mesh.faces)]
    if not meshes:
        raise MeshError("The generated mesh only contains degenerate faces.")

    transform = _Z_UP_TO_Y_UP.copy() if convert_z_up else np.eye(4)
    for mesh in meshes:
        mesh.apply_transform(transform)
    rotated = _summarise(meshes)
    largest = max(rotated["dimensions"])
    if not np.isfinite(largest) or largest <= 0:
        raise MeshError("The generated mesh has zero size.")
    centre = (np.array(rotated["bounds_min"]) + np.array(rotated["bounds_max"])) / 2
    normalise = trimesh.transformations.scale_matrix(1.0 / largest) @ trimesh.transformations.translation_matrix(-centre)
    for mesh in meshes:
        mesh.apply_transform(normalise)
        if not np.isfinite(mesh.face_normals).all():
            raise MeshError("The generated mesh has invalid face normals.")

    kinds = {_visual_kind(mesh) for mesh in meshes}
    report = {
        "source_vertices": original["vertices"], "source_faces": original["faces"],
        "source_dimensions": original["dimensions"], "degenerate_faces_removed": removed_faces,
        "watertight": all(mesh.is_watertight for mesh in meshes),
        "winding_consistent": all(mesh.is_winding_consistent for mesh in meshes),
        "has_vertex_colors": "vertex" in kinds, "has_texture": "texture" in kinds,
        "up_axis_converted": convert_z_up,
        "normalization": "centred at the origin and scaled to a largest extent of 1",
    }
    return meshes, report


def export_glb(meshes: list[trimesh.Trimesh], destination: Path, report: dict) -> dict:
    """Write a GLB, then reload it independently and confirm it matches what was written."""
    scene = trimesh.Scene()
    for index, mesh in enumerate(meshes):
        scene.add_geometry(mesh, geom_name=f"mesh_{index}")
    temporary = destination.with_suffix(".glb.tmp")
    temporary.write_bytes(scene.export(file_type="glb"))
    try:
        reloaded = trimesh.load(temporary, file_type="glb", force="scene", process=False)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise MeshError("The exported GLB could not be reloaded.") from exc
    reloaded_meshes = [geometry for geometry in reloaded.geometry.values() if isinstance(geometry, trimesh.Trimesh)]
    expected = _summarise(meshes)
    if not reloaded_meshes:
        temporary.unlink(missing_ok=True)
        raise MeshError("The exported GLB contains no geometry.")
    actual = _summarise(reloaded_meshes)
    if (actual["vertices"], actual["faces"]) != (expected["vertices"], expected["faces"]) or not np.isfinite(actual["dimensions"]).all():
        temporary.unlink(missing_ok=True)
        raise MeshError("The exported GLB does not match the processed mesh.")
    kinds = {_visual_kind(mesh) for mesh in reloaded_meshes}
    if report["has_vertex_colors"] and "vertex" not in kinds or report["has_texture"] and "texture" not in kinds:
        temporary.unlink(missing_ok=True)
        raise MeshError("The exported GLB lost the mesh's colour information.")
    temporary.replace(destination)
    return {**report, "vertices": actual["vertices"], "faces": actual["faces"],
            "dimensions": actual["dimensions"], "bounds_min": actual["bounds_min"], "bounds_max": actual["bounds_max"],
            "glb_bytes": destination.stat().st_size}
