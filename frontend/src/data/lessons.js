/**
 * OrbitGuard Academy — lesson content.
 * All scientific values are factual; interpretations are educational approximations.
 */

export const LESSONS = [
  {
    id: "ssa",
    title: "Space Situational Awareness",
    module: 1,
    emoji: "🛰️",
    summary: "What SSA is, why satellites and debris are tracked, and what can and cannot be predicted.",
    objectives: [
      "Define Space Situational Awareness (SSA).",
      "Explain why tracking is needed.",
      "Distinguish predictable from uncertain orbital events.",
    ],
    content: `
## What is Space Situational Awareness?

Space Situational Awareness (SSA) is the ability to know **where every significant human-made object in orbit is, where it is headed, and what risk it poses** to other spacecraft.

As of 2024, the U.S. Space Surveillance Network (SSN) tracks more than **27,000 objects** — active satellites, spent rocket stages, and fragmentation debris — all orbiting at 7–8 km/s. A collision between even a 10 cm fragment and an active satellite releases energy comparable to a hand grenade.

## Why does tracking matter?

- **Collision avoidance**: operators need hours of advance notice to plan a small burn that shifts the orbit enough to avoid a predicted close approach.
- **Debris environment**: the Kessler Syndrome — a cascade where collisions generate debris that causes more collisions — is a real long-term risk in crowded orbits like LEO.
- **Launch windows and reentry**: knowing what is up there lets ground controllers plan safe trajectories.

## What can and cannot be predicted?

| Predictable | Uncertain |
|---|---|
| Approximate position days ahead via SGP4 propagation | Exact position: errors grow over time |
| General orbital altitude and inclination | Atmospheric drag variations at LEO altitudes |
| Conjunction screening alerts | Precise collision probability (requires covariance data) |
| Reentry window (±hours or days) | Exact reentry footprint |

OrbitGuard provides **screening alerts** based on propagated SGP4 positions. These are not validated collision probabilities from a conjunction data message (CDM).
    `,
    keyTerms: [
      { term: "SSA", def: "Space Situational Awareness — knowing where objects in orbit are and where they are going." },
      { term: "SSN", def: "Space Surveillance Network — the U.S. sensor network that tracks orbital objects." },
      { term: "Kessler Syndrome", def: "A cascade of collisions generating debris that causes further collisions, potentially making certain orbits unusable." },
      { term: "CDM", def: "Conjunction Data Message — a formal document with covariance data used for validated collision probability calculations." },
    ],
    quiz: [
      {
        q: "Approximately how many objects does the U.S. Space Surveillance Network track as of 2024?",
        options: ["~500", "~2,700", "~27,000", "~270,000"],
        answer: 2,
        explanation: "The SSN tracks more than 27,000 objects including active satellites, rocket bodies, and debris fragments larger than about 10 cm in LEO.",
      },
      {
        q: "What is the Kessler Syndrome?",
        options: [
          "A type of orbital decay caused by atmospheric drag",
          "A cascade of collisions where debris generates more debris, threatening entire orbital shells",
          "A method for calculating collision probability",
          "The effect of solar radiation pressure on orbit shape",
        ],
        answer: 1,
        explanation: "Proposed by NASA scientist Donald Kessler in 1978, the Kessler Syndrome describes how a critical density of debris could trigger a self-sustaining chain reaction of collisions.",
      },
      {
        q: "OrbitGuard's conjunction alerts are best described as:",
        options: [
          "Validated collision probabilities from conjunction data messages",
          "Screening alerts based on propagated SGP4 positions",
          "Real-time radar measurements of close approaches",
          "Certified operational warnings from ESA or NASA",
        ],
        answer: 1,
        explanation: "OrbitGuard is an educational prototype. Its alerts are based on SGP4 position propagation and a distance threshold — not validated CDM-quality collision probabilities.",
      },
    ],
    resources: [
      { title: "NASA Orbital Debris Program Office", url: "https://www.nasa.gov/mission/space-debris/" },
      { title: "ESA Space Debris Office", url: "https://www.esa.int/Space_Safety/Space_Debris" },
      { title: "Space-Track.org (USSPACECOM)", url: "https://www.space-track.org" },
    ],
  },

  {
    id: "orbital-basics",
    title: "Earth and Orbital Basics",
    module: 2,
    emoji: "🌍",
    summary: "Earth radius, altitude, gravity, orbital velocity, period, and orbit shapes.",
    objectives: [
      "Describe how gravity provides centripetal force for orbital motion.",
      "Calculate approximate orbital velocity and period.",
      "Distinguish circular from elliptical orbits.",
    ],
    content: `
## Earth and Orbital Motion

Earth's mean radius is **6,371 km**. A satellite in orbit is in free fall — falling toward Earth while moving fast enough sideways that it continuously misses the surface.

## Orbital Velocity

For a circular orbit at altitude h (km) above Earth's surface, orbital speed is approximately:

> **v = √(GM / (R + h))**

where GM = 3.986 × 10⁵ km³/s² and R = 6,371 km.

| Orbit | Altitude | Approx. Velocity |
|---|---|---|
| LEO (ISS) | 400 km | ~7.7 km/s |
| MEO (GPS) | 20,200 km | ~3.9 km/s |
| GEO | 35,786 km | ~3.1 km/s |

## Orbital Period

For a circular orbit, the period (T) follows Kepler's Third Law:

> **T = 2π × √((R + h)³ / GM)**

The ISS at 400 km altitude completes one orbit in ~92 minutes. A GEO satellite takes exactly 24 hours — matching Earth's rotation, so it appears stationary from the ground.

## Orbit Shapes

- **Circular orbit**: constant altitude, constant speed.
- **Elliptical orbit**: altitude varies between perigee (closest) and apogee (furthest); speed is highest at perigee (Kepler's 2nd Law).
- **Eccentricity (e)**: 0 = perfect circle; 0.7 = highly elliptical (e.g., Molniya orbit).
    `,
    keyTerms: [
      { term: "Altitude", def: "Height above Earth's surface. Orbital altitude = orbital radius − 6,371 km." },
      { term: "Orbital velocity", def: "Speed required to maintain a circular orbit at a given altitude." },
      { term: "Orbital period", def: "Time to complete one full orbit." },
      { term: "Perigee / Apogee", def: "Closest / furthest point in an elliptical orbit from Earth's centre." },
      { term: "Eccentricity", def: "A measure of how non-circular an orbit is. 0 = circle; values closer to 1 = more elongated." },
    ],
    quiz: [
      {
        q: "Earth's mean radius is approximately:",
        options: ["3,471 km", "6,371 km", "12,742 km", "40,075 km"],
        answer: 1,
        explanation: "Earth's mean radius is 6,371 km. The 12,742 km value is the diameter; 40,075 km is the circumference.",
      },
      {
        q: "Why doesn't a satellite fall back to Earth?",
        options: [
          "There is no gravity in space",
          "It moves sideways so fast that it continuously 'misses' Earth as it falls",
          "Rocket engines keep pushing it forward",
          "Atmospheric drag lifts it",
        ],
        answer: 1,
        explanation: "A satellite is in continuous free fall. It moves horizontally fast enough that Earth's curved surface falls away at the same rate as the satellite falls — this is what an orbit is.",
      },
      {
        q: "A satellite at 35,786 km altitude has an orbital period of approximately:",
        options: ["92 minutes", "6 hours", "12 hours", "24 hours"],
        answer: 3,
        explanation: "At 35,786 km, the orbital period matches Earth's rotation (24 h) — this is the geostationary altitude. The satellite appears fixed above one point on the equator.",
      },
    ],
    resources: [
      { title: "NASA – Orbital Mechanics for Engineers (PDF)", url: "https://www.nasa.gov/pdf/140648main_human_orbmech.pdf" },
      { title: "Khan Academy – Circular motion and gravitation", url: "https://www.khanacademy.org/science/physics/centripetal-force-and-gravitation" },
    ],
  },

  {
    id: "orbit-types",
    title: "Types of Orbits",
    module: 3,
    emoji: "🔄",
    summary: "LEO, MEO, GEO, polar, and sun-synchronous orbits — uses, advantages, and limitations.",
    objectives: [
      "Describe LEO, MEO, GEO, polar, and sun-synchronous orbits.",
      "Match orbit types to their primary use cases.",
      "Explain trade-offs in altitude choice.",
    ],
    content: `
## Low Earth Orbit (LEO) — 160–2,000 km

LEO is the most densely populated orbital region. Low altitude means:
- **Short latency** (good for imaging, crewed missions, broadband mega-constellations like Starlink).
- **High drag**: orbit decays in years to decades; shorter natural debris lifetime.
- **Faster orbital period**: ~90–127 minutes.
- **Covers global ground tracks** (not continuously from one point).

## Medium Earth Orbit (MEO) — 2,000–35,786 km

Used primarily for **navigation constellations**:
- GPS: 20,200 km, 6 orbital planes, 12-hour period.
- Galileo: 23,222 km.
- GLONASS: 19,100 km.

MEO offers wide coverage with fewer satellites than LEO. Passes through the Van Allen radiation belt, so satellites need radiation-hardened electronics.

## Geostationary Orbit (GEO) — 35,786 km

GEO satellites appear **fixed above the equator** (period = 24 h). Used for:
- Weather (Meteosat, GOES).
- Broadcasting, TV, broadband.
- Military communications.

Limitation: high latency (~250 ms one-way), cannot cover polar regions.

## Polar Orbits — ~90° inclination

Passes over or near both poles, allowing **full global coverage** as Earth rotates beneath. Used for:
- Earth observation (Landsat).
- Weather satellites.

## Sun-Synchronous Orbit (SSO) — ~96–98° inclination

A special polar orbit where the precession rate matches Earth's revolution around the Sun, so the satellite crosses the equator at the **same local solar time** each day. Consistent lighting conditions make SSO ideal for:
- Multispectral and optical imaging (constant shadows for comparison).
- Indian Remote Sensing (IRS) satellites.
- ESA Sentinel series.
    `,
    keyTerms: [
      { term: "LEO", def: "Low Earth Orbit, 160–2,000 km altitude." },
      { term: "MEO", def: "Medium Earth Orbit, 2,000–35,786 km altitude, home to GPS/GNSS constellations." },
      { term: "GEO", def: "Geostationary Orbit at 35,786 km — satellite appears stationary above equator." },
      { term: "SSO", def: "Sun-Synchronous Orbit — polar orbit where local solar time at crossings stays constant." },
      { term: "Van Allen belts", def: "Zones of trapped radiation around Earth. Intense in MEO; poses risk to satellite electronics." },
    ],
    quiz: [
      {
        q: "Which orbit type provides the lowest communications latency?",
        options: ["GEO (35,786 km)", "MEO (20,200 km)", "LEO (400–1,200 km)", "HEO (highly elliptical)"],
        answer: 2,
        explanation: "LEO has the shortest signal travel time (~1–5 ms one-way vs ~250 ms for GEO). This is why Starlink and OneWeb target LEO for broadband.",
      },
      {
        q: "Why is sun-synchronous orbit particularly useful for optical imaging satellites?",
        options: [
          "They travel faster so capture more images",
          "They cross the equator at the same local solar time daily, giving consistent lighting",
          "They are immune to solar panel degradation",
          "They can hover above specific ground targets",
        ],
        answer: 1,
        explanation: "SSO's orbital precession (due to Earth's oblateness) is tuned to match Earth's revolution around the Sun, so the satellite sees the same solar angles on each pass — making multi-date image comparisons reliable.",
      },
      {
        q: "GPS satellites orbit at approximately:",
        options: ["400 km", "2,000 km", "20,200 km", "35,786 km"],
        answer: 2,
        explanation: "GPS satellites orbit at ~20,200 km (MEO) in 6 orbital planes. Their 12-hour period means each satellite is visible from the ground roughly twice per day.",
      },
    ],
    resources: [
      { title: "ESA – Types of orbits (eoPortal)", url: "https://www.esa.int/Enabling_Support/Space_Transportation/Types_of_orbits" },
      { title: "ISRO – Satellite orbits and applications", url: "https://www.isro.gov.in/applications.html" },
      { title: "GPS.gov – Space Segment", url: "https://www.gps.gov/systems/gps/space/" },
    ],
  },

  {
    id: "satellites-tle",
    title: "Satellites and Orbital Data",
    module: 4,
    emoji: "📡",
    summary: "NORAD catalog IDs, TLE format, orbital elements, and why data accuracy degrades.",
    objectives: [
      "Read the basic fields of a Two-Line Element (TLE) set.",
      "Explain why TLE accuracy degrades over time.",
      "Describe what NORAD catalog numbers represent.",
    ],
    content: `
## NORAD Catalog Numbers

Every tracked object in orbit is assigned a unique **NORAD Catalog Number** (also called the Satellite Catalog Number or SATCAT ID) by the 18th Space Defense Squadron (formerly 18th Space Control Squadron).

- ISS: **25544**
- Hubble Space Telescope: **20580**
- Numbers are assigned sequentially as objects are detected.

## Two-Line Element Sets (TLE)

A TLE is a standardized data format for representing an object's orbital parameters at a specific epoch (reference time).

\`\`\`
ISS (ZARYA)
1 25544U 98067A   24235.16000531  .00028314  00000+0  49252-3 0  9994
2 25544  51.6402 348.4828 0004893 236.4095 123.6428 15.50549723468780
\`\`\`

**Line 1 key fields:**
| Columns | Field | Value above |
|---|---|---|
| 1 | Line number | 1 |
| 3–7 | NORAD ID | 25544 |
| 10–17 | International designator | 98067A (1998 launch 67, object A) |
| 19–32 | Epoch | 24235.16 = day 235.16 of 2024 |
| 34–43 | First derivative of mean motion (drag) | .00028314 |
| 45–52 | B* drag term | 49252-3 |

**Line 2 key fields:**
| Columns | Field | Value above |
|---|---|---|
| 9–16 | Inclination (°) | 51.64 |
| 18–25 | RAAN (°) | 348.48 |
| 27–33 | Eccentricity | 0.0004893 |
| 35–42 | Argument of perigee (°) | 236.41 |
| 44–51 | Mean anomaly (°) | 123.64 |
| 53–63 | Mean motion (revolutions/day) | 15.505 |

## Why TLE Accuracy Degrades

SGP4 propagation using TLE data is accurate to **~1–3 km** immediately after the epoch but degrades over time:
- **Atmospheric drag** fluctuates with solar activity and is modelled approximately by B*.
- **Solar radiation pressure** causes perturbations not fully captured.
- **Manoeuvres** by active satellites are not in the TLE until a new set is published.
- **Observation gaps**: catalog updates depend on ground station coverage.

For conjunction analysis, data less than 24 hours old is preferred. After 7 days, positional errors can exceed 10–100 km.
    `,
    keyTerms: [
      { term: "NORAD ID", def: "Unique sequential catalog number assigned to every tracked orbital object." },
      { term: "TLE", def: "Two-Line Element set — standardized format encoding an object's orbital state at a given epoch." },
      { term: "Epoch", def: "The reference timestamp for a TLE. Propagation accuracy decreases as time from epoch grows." },
      { term: "B* drag term", def: "An atmospheric density coefficient in TLE format that approximates ballistic drag for SGP4." },
      { term: "RAAN", def: "Right Ascension of the Ascending Node — the angle defining where the orbit plane crosses the equator." },
      { term: "Mean anomaly", def: "Angular position of the satellite in its orbit at the epoch, measured from perigee." },
    ],
    quiz: [
      {
        q: "The NORAD ID of the International Space Station is:",
        options: ["98067A", "25544", "20580", "15.50"],
        answer: 1,
        explanation: "25544 is the ISS NORAD catalog number. 98067A is the international designator (1998, launch 67, object A). 20580 is the Hubble Space Telescope.",
      },
      {
        q: "Why does TLE-based position accuracy degrade over time?",
        options: [
          "The satellite naturally slows down in space",
          "Atmospheric drag, manoeuvres, and solar pressure cause real deviations from the modelled path",
          "TLE files expire automatically",
          "GPS satellite signals reach less far over time",
        ],
        answer: 1,
        explanation: "SGP4 is a simplified model. Unmodelled perturbations — especially drag variations and manoeuvres — cause the real trajectory to diverge from the prediction.",
      },
      {
        q: "The 'Mean motion' field in TLE Line 2 represents:",
        options: [
          "The satellite's speed in km/s",
          "The number of complete orbits per day",
          "The altitude above Earth's surface",
          "The date the TLE was generated",
        ],
        answer: 1,
        explanation: "Mean motion is measured in revolutions per day. The ISS value of 15.505 means it completes ~15.5 orbits per day, or one orbit every ~92 minutes.",
      },
    ],
    resources: [
      { title: "CelesTrak – TLE format documentation", url: "https://celestrak.org/NORAD/documentation/tle-fmt.php" },
      { title: "Space-Track.org – Satellite catalog", url: "https://www.space-track.org/basicspacedata/query/class/gp_history/" },
      { title: "Dr. T.S. Kelso – Frequently Asked Questions: Two-Line Element Sets", url: "https://celestrak.org/columns/v04n03/" },
    ],
  },

  {
    id: "propagation",
    title: "Orbital Propagation",
    module: 5,
    emoji: "📐",
    summary: "What SGP4 does, how positions are estimated, and what modelled trajectories mean.",
    objectives: [
      "Explain what orbital propagation means conceptually.",
      "Describe what SGP4 models and what it approximates.",
      "Distinguish modelled trajectories from observed positions.",
    ],
    content: `
## What is Orbital Propagation?

Orbital propagation is the process of **computing where a satellite will be at any future (or past) time** using its known orbital elements and a mathematical model.

Given a TLE valid at epoch t₀, a propagator estimates position (x, y, z) and velocity (vx, vy, vz) at time t₀ + Δt.

## SGP4 — Simplified General Perturbations 4

SGP4 is the standard propagator used with TLE data. It models:
- **Keplerian motion** (two-body problem, idealized ellipse).
- **Earth's oblateness** (J₂ and higher zonal harmonics) — Earth is not a perfect sphere.
- **Atmospheric drag** using the B* drag term from the TLE.
- **Solar and lunar gravitational perturbations** (simplified).
- **Solar radiation pressure** (limited).

SGP4 does **not** model:
- Actual real-time atmospheric density (uses a simplified model).
- Thruster manoeuvres by the satellite.
- High-accuracy solar/lunar perturbations beyond the simplifications in the model.
- Post-epoch debris fragmentation events.

## The TEME Coordinate Frame

SGP4 outputs positions in the **TEME** (True Equator, Mean Equinox) frame, a rotating Earth-centred frame. OrbitGuard visualizes these directly as ECI-like coordinates mapped onto the 3D globe.

## From TLE to 3D Position

1. Parse TLE → orbital elements.
2. Compute Julian date for target time.
3. SGP4 integrates the equations of motion → (x, y, z) in km, TEME frame.
4. Scale to scene units and render.

OrbitGuard's backend uses the **sgp4 Python library** (David Vallado's implementation) to do this.

## Trajectory vs. Observation

An SGP4 trajectory is a **model prediction**, not a radar measurement. For a fresh TLE (< 24 h old), positional accuracy is typically 1–3 km. For a week-old TLE, errors can be tens to hundreds of kilometers.
    `,
    keyTerms: [
      { term: "SGP4", def: "Simplified General Perturbations 4 — the standard propagator for TLE data." },
      { term: "TEME", def: "True Equator, Mean Equinox — the coordinate frame SGP4 outputs positions in." },
      { term: "Perturbation", def: "A force that deviates an orbit from a perfect Keplerian ellipse (drag, J₂, solar pressure, etc.)." },
      { term: "J₂", def: "The dominant Earth oblateness term — the equatorial bulge causes orbital plane precession." },
      { term: "Propagation error", def: "Growing difference between predicted and actual position, caused by unmodelled forces." },
    ],
    quiz: [
      {
        q: "SGP4 propagation is accurate to roughly ___ immediately after the TLE epoch:",
        options: ["< 1 metre", "1–3 km", "50–100 km", "Hundreds of km"],
        answer: 1,
        explanation: "With a fresh TLE (same day), SGP4 typically achieves 1–3 km accuracy. Accuracy degrades quickly with TLE age.",
      },
      {
        q: "SGP4 models which of the following?",
        options: [
          "Real-time atmospheric density from weather models",
          "Satellite manoeuvres planned by operators",
          "Earth's oblateness (J₂ term) and simplified drag",
          "Radar position measurements",
        ],
        answer: 2,
        explanation: "SGP4 models Keplerian motion + simplified perturbations including J₂ and drag (via B*). It does not know about actual manoeuvres or precise atmospheric density.",
      },
      {
        q: "What does 'modelled trajectory' mean in OrbitGuard?",
        options: [
          "A confirmed radar track of the satellite's actual path",
          "An SGP4-computed prediction based on TLE orbital elements",
          "A GPS track from the satellite's onboard navigation",
          "A hand-drawn orbital estimate by an astronomer",
        ],
        answer: 1,
        explanation: "OrbitGuard computes trajectories using SGP4 on TLE data — these are predictions, not direct observations.",
      },
    ],
    resources: [
      { title: "CelesTrak – SGP4 documentation and source code", url: "https://celestrak.org/software/vallado-sw.php" },
      { title: "Vallado & Crawford – SGP4 Revisited (technical paper)", url: "https://celestrak.org/publications/AIAA/2006-6753/" },
    ],
  },

  {
    id: "debris",
    title: "Space Debris",
    module: 6,
    emoji: "💥",
    summary: "Sources of debris, impact risk, crowded orbital regions, and mitigation strategies.",
    objectives: [
      "Identify the main sources of orbital debris.",
      "Explain why debris at LEO velocities is dangerous.",
      "Describe debris mitigation guidelines.",
    ],
    content: `
## What is Space Debris?

Space debris (also called space junk or orbital debris) encompasses any human-made object in Earth orbit that no longer serves a useful function:

- **Defunct satellites** — end-of-life spacecraft no longer operated.
- **Spent rocket upper stages** — boosters that delivered payloads and were left in orbit.
- **Mission-related fragments** — lens caps, explosive bolts, separation mechanisms.
- **Fragmentation debris** — from in-orbit explosions (propellant leaks, battery failures) and anti-satellite (ASAT) missile tests.
- **Paint flakes and small particles** — even sub-millimetre fragments can damage solar panels.

## Collision Energy at LEO Velocities

At 7.7 km/s (typical LEO velocity), a **1 cm aluminium sphere** has the same kinetic energy as a hand grenade. A 10 cm fragment can catastrophically destroy an operational satellite. This is why the debris population is tracked so carefully.

## Major Debris-Generating Events

| Event | Year | Objects generated |
|---|---|---|
| Fengyun-1C ASAT test (China) | 2007 | ~3,500+ trackable fragments |
| Cosmos 2251 / Iridium 33 collision | 2009 | ~2,300+ trackable fragments |
| ASAT test debris (various) | Ongoing | 1,000s of fragments |

## Crowded Orbital Regions

- **LEO 400–1,200 km**: highest debris density; ISS regularly manoeuvres.
- **800–1,000 km SSO shells**: Iridium, Planet Labs, future mega-constellations.
- **GEO belt (35,786 km)**: retired GEO satellites are moved to a "graveyard orbit" ~300 km higher.

## Debris Mitigation Guidelines

The **IADC (Inter-Agency Space Debris Coordination Committee)** and **UN COPUOS** guidelines recommend:
- **25-year LEO deorbit rule**: satellites in LEO should reenter within 25 years after end of mission.
- **GEO graveyard**: retired GEO satellites should be boosted at least 300 km above GEO.
- **Passivation**: venting remaining propellant and discharging batteries to prevent explosions.
- **Collision avoidance**: operators perform manoeuvres when conjunction probability exceeds thresholds.
    `,
    keyTerms: [
      { term: "Orbital debris", def: "Human-made objects in orbit that no longer serve a useful purpose." },
      { term: "ASAT", def: "Anti-Satellite weapon. Tests deliberately destroy satellites, creating debris fields." },
      { term: "Fragmentation event", def: "An explosion or collision that breaks an object into many pieces." },
      { term: "Passivation", def: "Depletion of stored energy (propellant, batteries) in a spacecraft at end of life to prevent explosions." },
      { term: "IADC", def: "Inter-Agency Space Debris Coordination Committee — international body that coordinates debris mitigation guidelines." },
      { term: "Graveyard orbit", def: "A disposal orbit above GEO where retired geostationary satellites are moved." },
    ],
    quiz: [
      {
        q: "The 2007 Fengyun-1C ASAT test was significant because:",
        options: [
          "It was the first satellite launch by China",
          "It generated roughly 3,500+ trackable debris fragments, greatly worsening the debris environment",
          "It demonstrated a debris removal technology",
          "It caused a collision with the ISS",
        ],
        answer: 1,
        explanation: "China's Fengyun-1C ASAT test is one of the most debris-generating events in history, adding thousands of fragments to the already-crowded 800 km orbital shell.",
      },
      {
        q: "The IADC 25-year rule states:",
        options: [
          "Satellites must operate for at least 25 years",
          "LEO spacecraft should reenter within 25 years after end of mission",
          "No more than 25 satellites may be launched per year",
          "Collision avoidance manoeuvres must be completed 25 hours in advance",
        ],
        answer: 1,
        explanation: "The 25-year deorbit guideline aims to limit debris accumulation in LEO. Objects that reenter sooner leave less time to collide with other satellites.",
      },
      {
        q: "Where are retired geostationary satellites typically disposed of?",
        options: [
          "They fall back to Earth via atmospheric drag",
          "They are moved to the Moon's orbit",
          "They are boosted ~300+ km above GEO to a graveyard orbit",
          "They are guided to reenter over the Pacific",
        ],
        answer: 2,
        explanation: "GEO is too high for atmospheric drag to remove debris in a reasonable time. Retired GEO satellites are instead boosted into a higher graveyard orbit clear of operational GEO slots.",
      },
    ],
    resources: [
      { title: "NASA Orbital Debris Quarterly News", url: "https://orbitaldebris.jsc.nasa.gov/quarterly-news/" },
      { title: "ESA – Space Debris by the Numbers", url: "https://www.esa.int/Space_Safety/Space_Debris/Space_debris_by_the_numbers" },
      { title: "IADC – Mitigation Guidelines (PDF)", url: "https://www.iadc-home.org/documents/public/debris_mitigation/iadc-2002-01-mitigation-guidelines-rev1.pdf" },
    ],
  },

  {
    id: "conjunction",
    title: "Conjunction Analysis and Collision Risk",
    module: 7,
    emoji: "⚠️",
    summary: "Conjunctions, closest approach, relative velocity, uncertainty, and risk assessment.",
    objectives: [
      "Define a conjunction and closest approach.",
      "Explain why relative velocity matters for collision risk.",
      "Distinguish a screening alert from a validated collision probability.",
    ],
    content: `
## What is a Conjunction?

A **conjunction** is an event where two tracked objects come within a defined distance threshold of each other — typically a few km — based on propagated orbital positions.

## Closest Approach Distance

The **distance at closest approach (DCA)** is the minimum predicted separation between the two objects during the conjunction. Typical screening thresholds used by operators are 1–5 km in LEO.

However, DCA alone does not determine risk. A 1 km miss at 0.1 km/s relative velocity is far less dangerous than the same miss at 14 km/s.

## Relative Velocity

In LEO, objects in similar orbits have low relative velocities (~0.1–1 km/s). Objects in crossing or counter-rotating orbits can have relative velocities up to ~14 km/s. Higher relative velocity means:
- More kinetic energy in a collision.
- Less time to identify and avoid the conjunction.
- Smaller positional error ellipsoids (the crossing happens fast).

## Uncertainty and Probability of Collision (Pc)

Spacecraft positions are not perfectly known. Each object has a **covariance** — an uncertainty volume. Collision probability is estimated as the overlap of the two uncertainty volumes during closest approach.

\`\`\`
Pc = ∫∫ f_combined(r) dA   (over the combined cross-section)
\`\`\`

True Pc requires a **Conjunction Data Message (CDM)** with covariance from the SSN. OrbitGuard does not have this data — it only uses point-position SGP4 predictions.

## Screening vs. Validated Risk

| | OrbitGuard | Operational SSA (e.g., LeoLabs, 18 SDS) |
|---|---|---|
| Data | SGP4 positions from TLE | Radar measurements + covariance |
| Output | Distance-based screening alert | Conjunction Data Message with Pc |
| Decision support | Educational only | Manoeuvre decision support |

## Risk Categories in OrbitGuard

OrbitGuard uses a simple heuristic based on miss distance:
- **Critical**: < 1 km
- **High**: 1–2 km
- **Medium**: 2–5 km
- **Low**: > 5 km

These are **not validated collision probabilities**. They are distance-based screening categories for educational purposes.
    `,
    keyTerms: [
      { term: "Conjunction", def: "An event where two objects come within a distance threshold based on propagated positions." },
      { term: "DCA", def: "Distance at Closest Approach — predicted minimum separation." },
      { term: "Relative velocity", def: "Speed of one object relative to another at conjunction; determines collision energy." },
      { term: "Covariance", def: "A statistical uncertainty volume around a predicted position." },
      { term: "Probability of Collision (Pc)", def: "Statistical probability that two objects actually collide, computed from covariance data." },
      { term: "CDM", def: "Conjunction Data Message — formal document with covariance data issued by SSN operators." },
    ],
    quiz: [
      {
        q: "Why is relative velocity important in conjunction risk assessment?",
        options: [
          "Higher velocity means objects are harder to track",
          "Higher relative velocity means more collision energy and less avoidance time",
          "Objects moving at the same speed cannot collide",
          "Velocity determines the satellite's NORAD ID",
        ],
        answer: 1,
        explanation: "Relative velocity directly determines how much kinetic energy would be released in a collision. It also affects the geometry of the encounter and how quickly operators must act.",
      },
      {
        q: "OrbitGuard's conjunction risk categories (Critical/High/Medium/Low) are:",
        options: [
          "Validated collision probabilities computed from radar covariance data",
          "Heuristic distance-based screening categories for educational purposes",
          "Official risk ratings issued by the 18th Space Defense Squadron",
          "Real-time manoeuvre recommendations",
        ],
        answer: 1,
        explanation: "OrbitGuard uses a simple distance threshold heuristic. It is an educational prototype, not an operational conjunction data service.",
      },
      {
        q: "A Conjunction Data Message (CDM) differs from OrbitGuard's output because it:",
        options: [
          "Is produced by a smartphone app",
          "Contains covariance data enabling a computed Probability of Collision",
          "Only covers GEO satellites",
          "Uses a different NORAD ID numbering system",
        ],
        answer: 1,
        explanation: "CDMs contain covariance matrices from radar observations, enabling statistical computation of Probability of Collision — something not possible with TLE point-position data alone.",
      },
    ],
    resources: [
      { title: "NASA CARA – Conjunction Assessment Risk Analysis", url: "https://www.nasa.gov/missions/station/conjuction-assessment-risk-analysis-cara/" },
      { title: "ESA – Conjunction analysis and avoidance", url: "https://www.esa.int/Space_Safety/Space_Debris/Conjunction_analysis_and_avoidance" },
      { title: "18 SDS Conjunction Screening Service", url: "https://www.space-track.org/documentation#/faq" },
    ],
  },

  {
    id: "orbitguard",
    title: "Understanding OrbitGuard",
    module: 8,
    emoji: "🖥️",
    summary: "How to interpret OrbitGuard's dashboard, risk categories, data sources, and limitations.",
    objectives: [
      "Interpret the OrbitGuard dashboard and its data sources.",
      "Understand the difference between simulated and live data.",
      "Identify the limitations of the application.",
    ],
    content: `
## What OrbitGuard Is

OrbitGuard is an **educational prototype** built at K.J. Somaiya College of Engineering as a semester mini-project in the July–December 2026 term. It fetches real TLE data from CelesTrak, propagates positions using SGP4, and provides conjunction screening — but it is not an operational collision-avoidance authority.

## Data Sources

| Data | Source | How it is used |
|---|---|---|
| TLE data | CelesTrak (celestrak.org) | Fetched and cached; used for all position computations |
| Object positions | SGP4 via Python sgp4 library | Computed on-demand; valid near the TLE epoch |
| Trajectories | SGP4 prediction (dense sampling) | Shown for selected satellites; not radar observations |
| Conjunction alerts | Distance-based heuristic | Shown in sidebar; not CDM-quality data |
| Risk levels | Simple distance threshold | Educational categories only |
| ML risk scores | Random Forest on synthetic features | Demonstration only; not validated against real events |

## The 3D Globe

- **Satellite dots**: current SGP4 position of each tracked object (stations group by default).
- **Orbit path** (shown on selection): 60-point SGP4 trajectory over ~100 minutes (approximately one orbit for LEO objects). This is a prediction, not a recorded track.
- **Earth occlusion**: objects behind the globe are naturally occluded by Three.js depth rendering.
- **Camera controls**: drag to rotate, scroll to zoom, right-drag to pan.

## Risk Categories

| Label | Distance threshold |
|---|---|
| Critical | < 1 km |
| High | 1–2 km |
| Medium | 2–5 km |
| Low | > 5 km |

These use current propagated positions only — no covariance, no validated Pc.

## What OrbitGuard Cannot Do

- Issue operational manoeuvre recommendations.
- Compute validated Probability of Collision.
- Show historical observations (only SGP4 predictions).
- Provide real-time positional accuracy (limited by TLE age).
- Replace professional SSA services like LeoLabs, ExoAnalytic, or 18 SDS.

## How to Use the Dashboard

1. **Overview**: see the live 3D map and top conjunction alerts.
2. **Click a satellite** in the 3D view to see its name, NORAD ID, altitude, and speed, and load its predicted orbit path.
3. **Conjunctions page**: browse detected close approaches with analysis links.
4. **Objects page**: list all tracked objects with altitude and velocity.
5. **Academy**: structured lessons explaining the science.
6. **Time controls** (LIVE / 1H / 6H / 24H / 48H): change the predicted offset — these show SGP4 position predictions, not historical observations.
    `,
    keyTerms: [
      { term: "Educational prototype", def: "A project built for learning purposes, not for operational or safety-critical use." },
      { term: "CelesTrak", def: "A public service providing TLE data from the USSPACECOM catalog." },
      { term: "Random Forest", def: "A machine-learning ensemble model. OrbitGuard uses one for demonstration risk scoring — it is not validated against real collision events." },
    ],
    quiz: [
      {
        q: "When OrbitGuard shows a 'Critical' conjunction alert, this means:",
        options: [
          "A collision has been confirmed by radar",
          "Two objects are predicted within 1 km based on SGP4 positions — an educational screening alert",
          "NASA has issued an emergency manoeuvre recommendation",
          "The objects have already collided",
        ],
        answer: 1,
        explanation: "OrbitGuard's critical label means the SGP4-predicted separation is < 1 km. This is an educational screening category, not an operational conjunction data message with validated Pc.",
      },
      {
        q: "Where does OrbitGuard get its TLE data?",
        options: [
          "GPS satellites transmit TLEs directly",
          "OrbitGuard's own radar network",
          "CelesTrak, a public service distributing USSPACECOM catalog data",
          "ESA's ESOC operations centre",
        ],
        answer: 2,
        explanation: "CelesTrak (run by Dr. T.S. Kelso) distributes orbital element data from the 18th Space Defense Squadron. OrbitGuard fetches from CelesTrak and caches locally.",
      },
      {
        q: "The orbit path shown for a selected satellite in OrbitGuard is:",
        options: [
          "A recorded GPS track from the satellite itself",
          "A radar-measured trajectory from the Space Surveillance Network",
          "A 60-point SGP4 prediction over approximately one orbital period",
          "A simulation drawn by the educational team for illustration",
        ],
        answer: 2,
        explanation: "OrbitGuard requests 60 evenly-spaced SGP4 time steps spanning ~100 minutes (roughly one LEO orbit) for the selected satellite. This is a model prediction, not an observation.",
      },
    ],
    resources: [
      { title: "CelesTrak – Real data used by OrbitGuard", url: "https://celestrak.org" },
      { title: "USSPACECOM – Space object catalog", url: "https://www.space-track.org" },
      { title: "ESA Space Debris Office", url: "https://www.esa.int/Space_Safety/Space_Debris" },
    ],
  },
];

export function getLessonById(id) {
  return LESSONS.find((l) => l.id === id) || null;
}

