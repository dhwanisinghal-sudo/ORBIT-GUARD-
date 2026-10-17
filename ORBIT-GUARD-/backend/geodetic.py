"""
OrbitGuard - TEME position -> geodetic latitude / longitude / height
----------------------------------------------------------------------
SGP4 returns positions in the TEME inertial frame. A map needs Earth-fixed latitude and
longitude, so we rotate by the Greenwich Mean Sidereal Time (GMST) and then convert
the Earth-fixed vector to geodetic coordinates on the WGS-84 ellipsoid.

Accuracy notes (fine for a map, not for geodesy):
  * UT1 is taken as UTC (differs by < 0.9 s, i.e. < 0.4 km of longitude at the equator)
  * polar motion and the equation of the equinoxes are ignored (well under 100 m)
  * height is above the WGS-84 ellipsoid. It is NOT the same number as the
    `altitude_km` field elsewhere in the API, which is |r| - 6371 (spherical Earth)
    and can differ from it by up to ~21 km.
"""

import math

import numpy as np

WGS84_A_KM = 6378.137
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)


def gmst_rad(jd_ut: np.ndarray, fr_ut: np.ndarray) -> np.ndarray:
    """GMST in radians (same polynomial SGP4 itself uses), for Julian date jd + fr (arrays)."""
    t = ((np.asarray(jd_ut, float) - 2451545.0) + np.asarray(fr_ut, float)) / 36525.0
    seconds = (67310.54841 + (876600.0 * 3600.0 + 8640184.812866) * t
               + 0.093104 * t ** 2 - 6.2e-6 * t ** 3)
    return np.deg2rad((seconds % 86400.0) / 240.0) % (2.0 * np.pi)


def teme_to_geodetic(r_teme_km, jd_ut, fr_ut):
    """
    r_teme_km: (N, 3) TEME positions in km; jd_ut / fr_ut: (N,) or scalar Julian date parts.
    Returns (lat_deg, lon_deg, height_km), each shape (N,). Longitude is in [-180, 180).
    """
    r = np.atleast_2d(np.asarray(r_teme_km, float))
    theta = gmst_rad(np.broadcast_to(jd_ut, r.shape[0]), np.broadcast_to(fr_ut, r.shape[0]))
    c, s = np.cos(theta), np.sin(theta)
    x = c * r[:, 0] + s * r[:, 1]          # TEME -> Earth-fixed (rotation about z by GMST)
    y = -s * r[:, 0] + c * r[:, 1]
    z = r[:, 2]

    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1.0 - WGS84_E2))
    for _ in range(6):
        n, h = _radius_and_height(lat, p, z)
        lat = np.arctan2(z, p * (1.0 - WGS84_E2 * n / (n + h)))
    _, h = _radius_and_height(lat, p, z)
    return np.rad2deg(lat), np.rad2deg(lon), h


def _radius_and_height(lat, p, z):
    sin_lat = np.sin(lat)
    n = WGS84_A_KM / np.sqrt(1.0 - WGS84_E2 * sin_lat ** 2)
    safe_sin = np.where(np.abs(sin_lat) < 1e-12, 1.0, sin_lat)
    h = np.where(np.abs(lat) < np.pi / 4,
                 p / np.cos(lat) - n,
                 z / safe_sin - n * (1.0 - WGS84_E2))
    return n, h


def teme_to_geodetic_scalar(x: float, y: float, z: float, jd_ut: float, fr_ut: float):
    """Same maths for one point with plain floats (~10x faster than the array version for N=1)."""
    t = ((jd_ut - 2451545.0) + fr_ut) / 36525.0
    seconds = (67310.54841 + (876600.0 * 3600.0 + 8640184.812866) * t
               + 0.093104 * t ** 2 - 6.2e-6 * t ** 3)
    theta = math.radians((seconds % 86400.0) / 240.0) % (2.0 * math.pi)
    c, s = math.cos(theta), math.sin(theta)
    ex, ey = c * x + s * y, -s * x + c * y
    lon = math.atan2(ey, ex)
    p = math.hypot(ex, ey)
    lat = math.atan2(z, p * (1.0 - WGS84_E2))
    n = h = 0.0
    for _ in range(7):
        sin_lat = math.sin(lat)
        n = WGS84_A_KM / math.sqrt(1.0 - WGS84_E2 * sin_lat ** 2)
        if abs(lat) < math.pi / 4:
            h = p / math.cos(lat) - n
        else:
            h = z / sin_lat - n * (1.0 - WGS84_E2)
        lat = math.atan2(z, p * (1.0 - WGS84_E2 * n / (n + h)))
    return math.degrees(lat), math.degrees(lon), h
