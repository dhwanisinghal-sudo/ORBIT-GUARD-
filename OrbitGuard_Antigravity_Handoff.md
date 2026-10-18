# OrbitGuard — Antigravity Handoff & Execution Brief

> **Project root:** `C:\Users\Windows\OneDrive\Desktop\ORBIT-GUARD-`  
> **GitHub repository:** `https://github.com/dhwanisinghal-sudo/ORBIT-GUARD-`  
> **Priority:** Implement the requested work efficiently. Inspect once, then act. Do not spend the session endlessly planning or re-inspecting.

## CRITICAL EXECUTION RULES — READ FIRST

**Your job is to IMPLEMENT, not endlessly inspect, plan, or explain.**

I want you to finish the actual work in my existing OrbitGuard project. Do not waste tokens repeatedly exploring files, generating long reports, asking unnecessary questions, or presenting plans without executing them.

### 1. Inspect once, then act

- Perform one focused initial inspection of the project structure, Git status, relevant source files, and available backend endpoints.
- Read only the files needed to understand the current implementation.
- Do not repeatedly inspect files you have already examined unless debugging requires it.
- After the initial inspection, immediately begin implementing the fixes in the order specified below.
- Do not stop after presenting findings or a plan. Continue making code changes.

### 2. Work efficiently

- Prioritize actual code changes over lengthy explanations.
- Avoid repeated searches, repeated file reads, redundant terminal commands, and unnecessary dependency installations.
- Reuse existing components, APIs, styles, libraries, and authentication utilities wherever possible.
- Make logically related changes together rather than editing the same files repeatedly.
- Do not rewrite working code or redesign the entire application unnecessarily.
- Avoid creating extra files, abstractions, dependencies, or features that do not directly support the requirements.
- Do not ask me to approve every small implementation decision. Use sensible defaults and proceed.
- Ask a question only when a genuinely blocking ambiguity cannot be resolved safely from the codebase.

### 3. Execute in focused phases

Complete these phases without stopping between them to request approval:

1. Fix orbital trajectory calculations, coordinate handling, rendering, Earth occlusion, and unnecessary API requests.
2. Make existing navigation, time controls, search, notifications, and other visible controls functional.
3. Complete registration, login, session restoration, protected routes, and logout.
4. Implement the educational landing page and a cohesive Academy/Learn section with structured lessons, quizzes, interactive activities, and credible learning resources.
5. Connect dashboard metrics to real data where available and clearly label simulated or unavailable data.
6. Run the production build, fix errors introduced by changes, and test critical flows.

Keep implementation coherent, but do not spend excessive time polishing one component while other required features remain unfinished.

### 4. Be honest and protect the project

- Preserve current local changes and existing UI.
- Never reset, discard, or overwrite existing work just to simplify implementation.
- Do not push, merge, deploy, or modify the `main` branch without my explicit permission.
- Do not invent backend functionality, live data, test results, or AI capabilities.
- If a feature is blocked, implement everything else that can be completed and explain the specific blocker.
- Do not claim completion unless you have run the relevant checks.

### 5. Minimize unnecessary output

- Do not give long progress updates or repeat the task requirements back to me.
- Keep investigation and explanations concise.
- Use tools and terminal commands to make real changes directly.
- At the end, give me only a concise summary of files changed, features implemented, tests actually run, remaining blockers, and exact commands to start the application.

**Definition of success:** The existing project has been modified, the requested features are implemented as far as the available backend supports, the production build is checked, and I receive a working result—not another plan or list of suggestions.

**Start now. Inspect once, implement continuously, verify, and report briefly.**

---

## 1. Project context

**Project:** OrbitGuard — Satellite Collision Risk Monitoring  
**Course context:** K. J. Somaiya College of Engineering, TY B.Tech, Semester V, WPL/FSDL Mini Project, July–December 2026 term.

The project is a React/Vite frontend with a Python FastAPI backend and a 3D Earth/orbit visualization. The goal is to evolve it into an educational space-science and orbital-awareness learning platform while retaining its satellite-tracking and conjunction-analysis features.

### Current project and Git state

- The local project root is `C:\Users\Windows\OneDrive\Desktop\ORBIT-GUARD-`.
- The GitHub repository may not include the latest local edits. Work on the actual local project opened in Antigravity; do not assume the remote is current.
- Before changes, check `git status` and the current branch once. Preserve uncommitted work.
- Do not push, merge, deploy, or modify `main` without permission.

## 2. Existing progress and known issues

The following reflects the last reported state; verify only what is needed to implement safely.

- The original dashboard styling in `frontend/src/App.css` was restored after it was accidentally replaced. Loading styles were appended to the restored stylesheet.
- `frontend/src/index.css` was reset to a minimal dark-theme-friendly CSS reset to remove Vite starter styling.
- Authentication work was started: `frontend/src/api.js` was updated with login/register/session helpers; `Login.jsx`, `Register.jsx`, and `Auth.css` were added; `App.jsx` was modified for session restoration and protected routes. These changes need testing against the actual current files.
- The dashboard's Earth visualization and existing pages should be preserved.
- The orbital paths still look physically wrong: paths form strange loops, overlap, or appear to cross the globe. Earlier curve-smoothing tweaks did not solve the issue.
- Dashboard navigation and controls appear not to work reliably. The header currently lacks a visible logout action.
- Backend live data may fail when the external CelesTrak provider cannot be reached.
- Build commands must be run from the correct subdirectory. The frontend build command is `npm.cmd run build` from `frontend`, not from the repository root.

Treat the above as clues, not proof of the current file contents. Do not revert existing work.

## 3. Main product goal: an educational learning platform

OrbitGuard should not be only a collision-monitoring dashboard. Make it a cohesive, student-friendly platform where users can explore orbital data and learn the science behind it.

The platform should teach:

- Space situational awareness and why it matters.
- Earth-orbit basics, gravity, orbital period, velocity, altitude, and inclination.
- LEO, MEO, GEO, polar, and sun-synchronous orbits, their use cases, and limitations.
- Satellites, NORAD catalog identifiers, TLE data, and orbital elements.
- Orbital propagation and SGP4 at a beginner-friendly conceptual level.
- Orbital debris, sources of debris, and mitigation.
- Conjunctions, closest approach, relative velocity, collision risk, uncertainty, and model limitations.
- How to interpret OrbitGuard's map, risk categories, and dashboard metrics.

The result should feel like one product with a coherent design, not a separate generic LMS template.

## 4. Fix orbital trajectories at the source

### Current symptoms

The 3D globe displays satellite markers, but the orbit lines look wrong: some form huge loops, cross in confusing ways, or seem to pass over the visible surface of Earth. Changing curve smoothing alone did not fix the problem.

The frontend has previously used these assumptions:

- `SpaceScene.jsx` requests objects using `getObjects("stations", 100)`.
- Current position is `object.position_km` shaped like `{ x, y, z }`.
- Trajectory data is requested using `getTrajectory(object.norad_id)`.
- The response is expected to contain `data.trajectory` or `data.points`.
- Each sample is expected to have `sample.position_km` shaped like `{ x, y, z }`.
- Positions are scaled with `SCENE_RADIUS / EARTH_RADIUS`, with `EARTH_RADIUS = 6371` and `SCENE_RADIUS = 2`.
- `THREE.CatmullRomCurve3` smoothing was tried and removed; the visual problem persisted.

These are assumptions to verify, not facts about the current backend response.

### Required implementation

1. Inspect the `/trajectory/{norad_id}` endpoint and trace the propagation function it calls.
2. Verify a real trajectory response shape. Confirm property names, units, sample count, time ordering, and error behavior.
3. Confirm that current positions and trajectory samples use the same coordinate frame, axis convention, origin, and units. If not, transform them correctly.
4. Verify propagation success and filter invalid values without silently connecting across missing or discontinuous segments.
5. Ensure samples are in chronological order and represent distinct times.
6. Confirm the trajectory interval and sample density are appropriate for the intended orbit display.
7. Do not use a smoothing spline that invents loops or overshoots physical samples.
8. Ensure Earth correctly occludes paths passing behind the globe. Do not draw orbital lines visibly across Earth's front surface.
9. Make paths subtle and thin by default, with a clear highlight for the selected object.
10. Keep satellite markers selectable and show at least name and NORAD ID in a label or detail panel.
11. Preserve camera controls and the Earth texture.
12. Explain the actual root cause in the final report; do not claim it was fixed by merely changing colours.

### Performance

The frontend previously tried to fetch trajectories for as many as 100 objects simultaneously. Avoid excessive requests.

- Load current object positions first.
- Fetch a trajectory lazily for the selected satellite or use a small controlled subset when needed.
- Reuse and cache existing data where practical.
- Do not overwhelm the backend or external provider.
- A failed trajectory fetch must not prevent the rest of the dashboard from rendering.

## 5. Make existing controls functional

Inspect the existing header and pages, then wire controls to real behavior.

### Main navigation

Make these routes work through the existing React Router setup:

- **Overview** — dashboard.
- **Orbital Map** — 3D orbital visualization.
- **Conjunctions** — conjunction results and analysis.
- **Objects** — tracked object list.
- **Learn / Academy** — educational area.

Indicate the active route and fix unstyled purple underlined links. Preserve the existing OrbitGuard visual identity.

### Time-range controls

The dashboard has **LIVE, 1H, 6H, 24H, and 48H** options.

- Make controls clickable and show the active selection.
- Inspect backend capabilities before connecting them.
- If actual historical playback/propagation exists, connect the range to it.
- If the app only supports current data, either implement an honest view/simulation setting or visibly disable unsupported ranges with an explanation.
- Never claim historical observations exist if they are not stored.

### Search

- Open a search input or panel when the search icon is clicked.
- Search real loaded objects or use an existing search API.
- Show results and allow a result to navigate to the object's detail page or select it on the map.
- Support no-results, loading, close, and basic keyboard interactions.

### Notifications

- Open/close a notification panel from the existing icon.
- Show actual available conjunction alerts or other relevant backend information.
- Do not fabricate notification history or read/unread status if no such functionality exists.

### Audit all visible controls

Every visible button, icon, tab, menu, and clickable card must do what it promises or be clearly disabled with an explanation. Do not leave decorative controls that appear functional.

## 6. Complete login, registration, session handling, and logout

Inspect existing auth code and use it rather than creating a second system.

Backend routes previously found in `backend/auth.py`:

- `POST /auth/register` with `{ name, email, password }`.
- `POST /auth/login` with `{ email, password }`.
- `GET /auth/me` with a Bearer token.

Confirm the actual endpoint definitions and response formats before integration.

### Required flow

- Create a polished, responsive login page matching the existing dark space theme.
- Create a matching registration page with name, email, password, and password confirmation.
- Validate required fields and password confirmation.
- Show useful messages for invalid credentials, duplicate email, network failures, and server errors.
- Store only the returned token and required user information using the existing session helpers. Never store a password.
- Restore valid sessions after refresh and handle expired tokens.
- Protect dashboard/learning routes where appropriate.
- Redirect authenticated users away from login/register when suitable.
- Add a clearly visible **Logout** button/menu item. It must clear the session and redirect to `/login`.
- Do not bypass backend authentication or hardcode a production secret.

## 7. Educational landing page

Create or improve a landing/intro page so a visitor understands OrbitGuard before entering the dashboard.

Include:

- What OrbitGuard is.
- The problem of orbital debris and satellite conjunctions.
- How the platform works at a high level.
- What students can learn.
- Separate, clear calls to action: **Explore the Orbital Map**, **Start Learning**, **Create Account**.
- A short flow such as orbital data → propagation → visualization → conjunction/risk analysis.
- A clear limitation notice: this is an educational prototype, not an operational collision-avoidance authority.

Avoid fake testimonials, fabricated accuracy claims, invented partnerships, and unsupported AI claims.

## 8. Academy / Learn area

Add a clear Learn/Academy section to the navigation and integrate it with the existing design.

### Learning home

Include:
- A short welcome and explanation of the platform.
- Learning paths/modules.
- A suggested next lesson where appropriate.
- Links to related orbital visualizations.
- Progress only if it is genuinely tracked and stored.
- A concise explanation of why space situational awareness matters.

Do not show fake learner statistics, streaks, certificates, or progress.

### Lessons

Create concise, structured lessons for these modules:

1. **Introduction to Space Situational Awareness**
   - What it is, why satellites/debris are tracked, what can and cannot be predicted.

2. **Earth and Orbital Basics**
   - Earth radius and altitude, gravity, orbital motion, velocity, orbital period, circular and elliptical orbits.

3. **Types of Orbits**
   - LEO, MEO, GEO, polar, and sun-synchronous orbits, use cases, advantages, and limitations.

4. **Satellites and Orbital Data**
   - NORAD catalog IDs, TLE fields, basic orbital elements, and why data accuracy degrades over time.

5. **Orbital Propagation**
   - SGP4 conceptually, estimating positions from orbital data, modelled trajectories versus observations.

6. **Space Debris**
   - Sources, high-speed impact risk, crowded regions, and mitigation.

7. **Conjunction Analysis and Collision Risk**
   - Conjunctions, closest approach, relative velocity, uncertainty, and the difference between a screening alert and a validated collision probability.

8. **Understanding OrbitGuard**
   - Explain dashboard fields, risk categories, data sources, selected-object paths, and simulated versus live information.

Each lesson should include:
- Learning objectives.
- Short, readable explanations.
- Key terms.
- A few knowledge-check questions with explanations.
- Links to relevant parts of the application.
- Diagrams or existing visualizations where they add value.

Do not put all lessons into one enormous wall of text. Use a consistent lesson layout and reusable components where sensible.

### Interactive learning

Implement a few polished, working interactions rather than many incomplete ones. Suitable examples:

- Orbit-type comparison cards.
- An altitude/orbit explainer.
- A TLE-field explainer.
- A satellite identification exercise.
- Multiple-choice quizzes with immediate feedback and explanations.
- A simple conjunction scenario illustrating why distance and relative velocity matter.

Clearly label simplified demonstrations. Do not present them as validated orbital simulations.

### Progress

If lesson progress is implemented:
- Persist it using an appropriate real API or simple existing storage mechanism.
- Explain whether progress is browser-local or tied to the account.
- Do not invent an LMS backend.

### Learning resources

Provide verified links to credible primary sources, including official space-agency education pages and technical documentation. Verify links before adding them. If using ISRO resources, use real official resources and do not imply ISRO affiliation or endorsement.

## 9. Data accuracy and API behavior

- Inspect real backend response formats before connecting UI.
- Use real data where available.
- Replace hardcoded metrics only if a real source exists.
- Label simulated data explicitly.
- Do not fabricate conjunction alerts, collision probabilities, historical observations, or model accuracy.
- Do not call a heuristic risk category a validated collision probability.
- Provide loading, empty, and error states.
- Handle external TLE provider failure gracefully.
- Keep partial dashboard functionality available when one endpoint fails.
- Avoid excessive concurrent requests.

## 10. Design requirements

Preserve the current OrbitGuard visual identity:

- Dark navy/black space theme.
- Blue/cyan highlights.
- Existing Earth texture and 3D globe.
- Clean cards, readable typography, and consistent spacing.
- Responsive desktop/mobile layout.
- Consistent hover, focus, selected, loading, empty, and error states.
- Accessible labels for icon-only controls and keyboard-accessible forms/menus where practical.

Do not replace the existing app with a generic admin dashboard template.

## 11. Implementation order

Follow this order, but do not pause for approval between phases:

1. Focused initial inspection of Git status, frontend structure, backend trajectory endpoint, auth endpoints, and run commands.
2. Fix the root cause of orbital paths, including coordinate correctness, Earth occlusion, and performance.
3. Make navigation and header controls functional.
4. Complete login/register, session restore, protected routes, and logout.
5. Add the educational landing page and Learn/Academy navigation.
6. Implement structured learning modules, quizzes, interactive activities, and verified resources.
7. Connect dashboard statistics to real data where available.
8. Run the frontend production build, fix errors introduced by the work, and test key flows.
9. Provide a concise final report.

Do not stop after the initial inspection or give me only a plan. Implement the work.

## 12. Verification checklist

### Application
- [ ] Frontend production build succeeds.
- [ ] No broken imports or routes.
- [ ] Existing dashboard and Earth visualization still render.
- [ ] Camera controls still work.
- [ ] No obvious new console errors.

### Orbital visualization
- [ ] Backend trajectory response shape verified.
- [ ] Coordinate frame, units, sample order, and time range checked.
- [ ] No artificial loops introduced by smoothing.
- [ ] Earth correctly occludes paths passing behind it.
- [ ] Satellite markers are selectable.
- [ ] Trajectory requests do not overload the backend.

### Controls
- [ ] Navigation works and active route is styled.
- [ ] Time controls respond and reflect actual supported behavior.
- [ ] Search returns real objects and selection/navigation works.
- [ ] Notifications show available real alerts.
- [ ] All visible controls work or are clearly disabled.

### Authentication
- [ ] Registration tested against backend where available.
- [ ] Login tested against backend where available.
- [ ] Validation and error states work.
- [ ] Session restoration works.
- [ ] Protected routes work.
- [ ] Logout clears session and redirects.

### Learning platform
- [ ] Landing page explains the product.
- [ ] Academy navigation and lesson pages work.
- [ ] Quizzes show feedback and explanations.
- [ ] External resource links are verified.
- [ ] Simulated data is clearly labelled.
- [ ] No fake progress or unsupported AI claims.

## 13. Final report

At completion, provide only a concise report containing:

1. Main problems found and the root cause of the orbit issue.
2. Files changed and what was implemented.
3. Tests actually run and their results.
4. Remaining blockers or incomplete features.
5. Exact Windows PowerShell commands to start backend and frontend.
6. Required environment variables or setup steps.
7. Confirmation that no changes were pushed to GitHub unless I explicitly authorized it.

**Start now. Inspect once, implement continuously, verify, and report briefly. Do the actual work rather than spending the session planning.**
