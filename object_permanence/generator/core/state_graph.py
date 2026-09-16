"""Selection helpers for bounded scene-state recording."""


def prioritize_recorded_objects(objects, is_target, is_dynamic, limit=48):
    """Keep semantic targets first, then other dynamic objects, then apparatus.

    Blender scenes may contain more meshes than the bounded trajectory contract can
    store.  Preserving source order within each priority class keeps the output
    deterministic while ensuring decorative geometry cannot evict the objects whose
    motion the sample is designed to supervise.
    """
    if limit < 0:
        raise ValueError("limit must be non-negative")
    objects = list(objects)
    if len(objects) <= limit:
        return objects
    ranked = sorted(
        enumerate(objects),
        key=lambda item: (
            0 if is_target(item[1]) else 1 if is_dynamic(item[1]) else 2,
            item[0],
        ),
    )
    return [obj for _, obj in ranked[:limit]]
