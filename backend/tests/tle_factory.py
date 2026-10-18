"""Build synthetic-but-valid TLEs (with correct checksums) for conjunction tests."""

ISS_LINE1 = "1 25544U 98067A   24235.16000531  .00028314  00000+0  49252-3 0  9994"


def _checksum(line: str) -> int:
    return sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line[:68]) % 10


def make_tle(norad: int, name: str, inc: float, raan: float, ma: float,
             mean_motion: float = 15.50549723, ecc: int = 4893, argp: float = 236.4095) -> dict:
    """Same epoch/drag terms as the ISS TLE; orbit shape and phase are up to the caller."""
    l1 = f"1 {norad:05d}" + ISS_LINE1[7:68]
    l1 += str(_checksum(l1))
    l2 = f"2 {norad:05d} {inc:8.4f} {raan:8.4f} {ecc:07d} {argp:8.4f} {ma:8.4f} {mean_motion:11.8f}{46878:5d}"
    l2 += str(_checksum(l2))
    assert len(l1) == 69 and len(l2) == 69, (len(l1), len(l2))
    return {"name": name, "line1": l1, "line2": l2}


def random_leo_tles(n: int, seed: int = 7) -> list[dict]:
    """Seeded random LEO satellites - for brute-force comparison, not realism."""
    import numpy as np
    rng = np.random.default_rng(seed)
    return [
        make_tle(10000 + i, f"R{i}", rng.uniform(0, 100), rng.uniform(0, 360), rng.uniform(0, 360),
                 mean_motion=rng.uniform(13.0, 15.9), ecc=int(rng.integers(0, 3000)),
                 argp=rng.uniform(0, 360))
        for i in range(n)
    ]
