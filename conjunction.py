"""
OrbitGuard - conjunction detection (Week 4)
----------------------------------------------
Given a list of propagated object positions (from orbit_engine.propagate_many),
find pairs of objects that are dangerously close to each other right now.

Two implementations, matching the plan's "start naive, then optimize" advice:

  find_conjunctions_naive()  - O(n^2): compares every object against every
                                other. Fine for the ~10-1000 range. Simple
                                and easy to verify correct.

  find_conjunctions_kdtree() - uses scipy's KDTree to only compare objects
                                that are already spatially close, which is
                                much faster once you're at thousands of
                                objects (the plan's optimization step).

Both return the same shape, so main.py can swap between them freely.
"""

import math
import itertools

# threshold below which we call two objects a "conjunction" (close approach)
DEFAULT_THRESHOLD_KM = 5.0


def _distance_km(a: dict, b: dict) -> float:
    """Straight-line (Euclidean) distance between two propagated positions, in km."""
    pa, pb = a["position_km"], b["position_km"]
    return math.sqrt(
        (pa["x"] - pb["x"]) ** 2 +
        (pa["y"] - pb["y"]) ** 2 +
        (pa["z"] - pb["z"]) ** 2
    )


def _relative_velocity_km_s(a: dict, b: dict) -> float:
    va, vb = a["velocity_km_s"], b["velocity_km_s"]
    return math.sqrt(
        (va["x"] - vb["x"]) ** 2 +
        (va["y"] - vb["y"]) ** 2 +
        (va["z"] - vb["z"]) ** 2
    )


def _risk_level(distance_km: float) -> str:
    """Simple rule-based risk level, per the plan's Week 5 starting point."""
    if distance_km < 1.0:
        return "HIGH"
    elif distance_km < 5.0:
        return "MEDIUM"
    return "LOW"


def _make_conjunction(a: dict, b: dict, distance_km: float) -> dict:
    return {
        "object_1": {"name": a["name"], "norad_id": a["norad_id"]},
        "object_2": {"name": b["name"], "norad_id": b["norad_id"]},
        "distance_km": round(distance_km, 3),
        "relative_velocity_km_s": round(_relative_velocity_km_s(a, b), 3),
        "risk_level": _risk_level(distance_km),
    }


def simulate_altitude_adjustment(
    object_to_move: dict, other_object: dict, altitude_delta_km: float
) -> dict:
    """
    What-if maneuver simulator (Week 7).

    Shifts object_to_move's position radially outward (positive delta) or
    inward (negative delta) by altitude_delta_km, then recomputes its distance
    to other_object. This is a simplified simulation, not a real spacecraft
    maneuver planner - per the plan, it just needs to demonstrate how a
    trajectory change affects the predicted conjunction.

    Returns before/after distance and risk level.
    """
    p = object_to_move["position_km"]
    radius = math.sqrt(p["x"] ** 2 + p["y"] ** 2 + p["z"] ** 2)
    if radius == 0:
        raise ValueError("Cannot adjust altitude of an object at the origin")

    # unit vector pointing away from Earth's center, then push the object
    # along it by altitude_delta_km (a simple radial burn approximation)
    scale = (radius + altitude_delta_km) / radius
    new_position = {
        "x": p["x"] * scale,
        "y": p["y"] * scale,
        "z": p["z"] * scale,
    }
    adjusted = dict(object_to_move)
    adjusted["position_km"] = new_position
    adjusted["altitude_km"] = round(object_to_move["altitude_km"] + altitude_delta_km, 2)

    before_distance = _distance_km(object_to_move, other_object)
    after_distance = _distance_km(adjusted, other_object)

    return {
        "altitude_delta_km": altitude_delta_km,
        "before": {
            "distance_km": round(before_distance, 3),
            "risk_level": _risk_level(before_distance),
        },
        "after": {
            "distance_km": round(after_distance, 3),
            "risk_level": _risk_level(after_distance),
        },
    }


def find_conjunctions_naive(
    objects: list[dict], threshold_km: float = DEFAULT_THRESHOLD_KM
) -> list[dict]:
    """
    Compare every object against every other object (O(n^2)).

    Good for up to a few hundred/thousand objects. This is the "start simple"
    version from Week 4 of the plan - use it first, verify it's correct,
    then reach for find_conjunctions_kdtree() once you scale up.
    """
    conjunctions = []
    for a, b in itertools.combinations(objects, 2):
        distance = _distance_km(a, b)
        if distance < threshold_km:
            conjunctions.append(_make_conjunction(a, b, distance))

    conjunctions.sort(key=lambda c: c["distance_km"])
    return conjunctions


def find_conjunctions_kdtree(
    objects: list[dict], threshold_km: float = DEFAULT_THRESHOLD_KM
) -> list[dict]:
    """
    Same result as find_conjunctions_naive, but uses a KDTree to avoid
    comparing every pair - only objects already spatially near each other
    get checked. Much faster once you're tracking thousands of objects.

    Requires scipy (already in requirements.txt).
    """
    from scipy.spatial import KDTree

    if len(objects) < 2:
        return []

    points = [
        (o["position_km"]["x"], o["position_km"]["y"], o["position_km"]["z"])
        for o in objects
    ]
    tree = KDTree(points)

    # query_pairs returns index pairs (i, j) whose points are within
    # threshold_km of each other - this is the "spatial filtering" step
    # from the plan's architecture diagram.
    pairs = tree.query_pairs(r=threshold_km)

    conjunctions = []
    for i, j in pairs:
        a, b = objects[i], objects[j]
        distance = _distance_km(a, b)
        conjunctions.append(_make_conjunction(a, b, distance))

    conjunctions.sort(key=lambda c: c["distance_km"])
    return conjunctions
