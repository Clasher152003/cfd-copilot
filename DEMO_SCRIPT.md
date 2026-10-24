# CFD Copilot Live Demo Script

**Total time: ~7 minutes**

This script walks through three cases: a fully-converged duct flow (flagship result), an airfoil case (parametric geometry with known limitations), and a compressible nozzle (density-based transient solver). Each step includes what to say out loud while it runs.

---

## Part 1: Duct Flow (Fully Converged) -- Steps 1-6

### Step 1: Generate Duct Geometry

**What to say:** "Let's start with a simple 2D duct. I'll describe it in plain language and the AI will generate the OpenFOAM blockMeshDict file."

**Prompt:**
```
Generate geometry for a 2D square duct case:
- 1 meter x 1 meter cross-section
- Call it duct_demo
```

**What happens:** The `generate_geometry` tool creates `cases/duct_demo/system/blockMeshDict` with a 20x20x1 structured hex mesh.

---

### Step 2: Generate Mesh

**What to say:** "Now we'll run blockMesh in WSL to generate the actual mesh from that geometry definition."

**Prompt:**
```
Generate the mesh for duct_demo
```

**What happens:** The `generate_mesh` tool runs `blockMesh` via WSL and reports mesh statistics (400 cells, orthogonality, skewness all within OpenFOAM tolerance).

---

### Step 3: Set Up Boundary Conditions

**What to say:** "Next, we need to set up the physics: inlet velocity, outlet pressure, and material properties for incompressible laminar flow."

**Prompt:**
```
Set up the duct_demo case for incompressible laminar flow:
- Inlet velocity 5 m/s
- Outlet pressure 0 Pa
- Use simpleFoam solver
```

**What happens:** The `setup_case` tool creates `0/U`, `0/p`, and `constant/transportProperties` with appropriate boundary conditions (fixedValue inlet, zeroGradient outlet, noSlip walls).

---

### Step 4: Run the Solver

**What to say:** "Now we'll run simpleFoam. This usually converges in under 200 iterations for a case this simple. The tool monitors residuals in real time."

**Prompt:**
```
Run the solver for duct_demo with a maximum of 500 iterations
```

**What happens:** The `run_solver` tool runs simpleFoam via WSL. For this case, it converges around iteration 126 with all residuals below 1e-4. Full solver output is saved to `cases/duct_demo/log.simpleFoam`.

**Expected output:** "Convergence status: CONVERGED" with final residuals for Ux, Uy, and p all below threshold.

---

### Step 5: Post-Process Results

**What to say:** "Finally, we'll extract the velocity and pressure fields and generate contour plots. This uses foamToVTK and PyVista under the hood."

**Prompt:**
```
Post-process the results for duct_demo
```

**What happens:** The `postprocess_results` tool runs foamToVTK, loads the VTK data with PyVista, and generates matplotlib plots saved as `cases/duct_demo/results_velocity.png` and `results_pressure.png`.

**Expected output:** Statistics showing min/max/average velocity and pressure, plus paths to the PNG files.

---

### Step 6: View the Results

**What to say:** "Let's look at the velocity field. You should see a smooth flow with zero velocity at the walls -- that's the no-slip boundary condition validated."

**Prompt:**
```
Show me the velocity plot at cases/duct_demo/results_velocity.png
```

**What happens:** Your MCP client displays the image. The plot shows a smooth velocity distribution with proper boundary layer behavior at the walls.

---

## Part 2: Airfoil Flow (Parametric Geometry) -- Steps 7-9

### Step 7: Generate Airfoil Geometry

**What to say:** "Now let's do something more complex: external flow around a NACA airfoil. The geometry generator supports NACA 4-digit parametric definitions with O-grid topology."

**Prompt:**
```
Generate geometry for a NACA 2412 airfoil case:
- 1 meter chord length
- 5 degree angle of attack
- 20 m/s freestream velocity
- Call it airfoil_demo
```

**What happens:** The `generate_geometry` tool generates NACA 2412 coordinates, creates an O-grid blockMeshDict with 4 blocks (100x50 cells total), includes spline edges for the airfoil surface, and applies radial grading factor of 10 to capture the boundary layer.

---

### Step 8: Generate Airfoil Mesh

**What to say:** "The O-grid wraps around the airfoil out to a far-field boundary. Let's mesh it."

**Prompt:**
```
Generate the mesh for airfoil_demo
```

**What happens:** The `generate_mesh` tool runs blockMesh and reports mesh statistics. You'll see ~5000 cells with acceptable but non-ideal skewness near the leading edge (this is the known mesh quality issue mentioned in the README).

---

### Step 9: Set Up Airfoil Case

**What to say:** "For external flow, we use freestream boundary conditions at the far field and no-slip on the airfoil surface."

**Prompt:**
```
Set up the airfoil_demo case for incompressible external flow:
- Freestream velocity 20 m/s at 5 degrees angle of attack
- Freestream pressure 0 Pa
- Use simpleFoam solver
```

**What happens:** The `setup_case` tool creates `0/U` and `0/p` with `freestreamVelocity` and `freestreamPressure` boundary conditions at the far field, and noSlip on the airfoil surface. Velocity components are automatically calculated for the 5-degree angle of attack.

---

### Optional Step 10: Run Airfoil Solver (with honest disclaimer)

**What to say:** "We can run the solver, but I'll be honest -- this mesh has borderline skewness that limits pressure convergence. Velocity fields converge nicely, but pressure plateaus around 1e-3 instead of reaching the full 1e-4 threshold. It's good enough for qualitative flow visualization but would need mesh refinement for production aerodynamics."

**Prompt:**
```
Run the solver for airfoil_demo with a maximum of 2000 iterations
```

**What happens:** simpleFoam runs and velocity residuals drop to ~2-6e-5, but pressure stalls at ~1e-3. The tool reports "NOT CONVERGED" but the results are still physically reasonable for visualization.

---

## Part 3: Compressible Nozzle Flow (rhoCentralFoam) -- Steps 11-14

### Step 11: Generate Nozzle Geometry

**What to say:** "Now for the most challenging case: compressible flow through a converging-diverging nozzle. This requires a completely different solver -- rhoCentralFoam, which is a transient density-based scheme that can capture shock waves and supersonic flow."

**Prompt:**
```
Generate geometry for a converging-diverging nozzle:
- 0.5m total length
- Throat radius 0.05m, exit radius 0.1m
- Axisymmetric (wedge mesh)
- Call it nozzle_demo
```

**What happens:** The `generate_geometry` tool creates a nozzle profile CSV with smooth converging and diverging sections.

---

### Step 12: Generate Nozzle Mesh and Set Up Case

**What to say:** "We'll mesh this as a 2.5-degree wedge -- that's OpenFOAM's standard approach for axisymmetric cases. Then we'll set up compressible boundary conditions with total pressure and temperature at the inlet."

**Prompt:**
```
Generate a nozzle_wedge mesh for nozzle_demo using the nozzle geometry, then set up the case for compressible flow:
- Total pressure inlet 200 kPa at 350 K
- Static pressure outlet 120 kPa
- Use rhoCentralFoam (transient density-based solver)
```

**What happens:** The `generate_mesh` tool creates a 50x30x1 wedge mesh (1500 cells). Then `setup_case` writes rhoCentralFoam-specific controlDict (adaptive time-stepping, maxCo=0.5), fvSchemes (Kurganov flux scheme with vanLeer reconstruction), boundary conditions (totalPressure inlet, fixedValue outlet, noSlip walls, wedge patches), and thermophysical properties (air as perfect gas with Sutherland viscosity).

---

### Step 13: Run rhoCentralFoam

**What to say:** "rhoCentralFoam is a transient solver, so instead of iterating to steady state like simpleFoam, it marches forward in physical time with adaptive time-stepping. The Courant number is capped at 0.5 for stability. This takes longer than the duct case but captures physics that steady-state solvers can't handle."

**Prompt:**
```
Run the solver for nozzle_demo
```

**What happens:** The `run_solver` tool detects rhoCentralFoam as a transient solver and preserves the endTime from controlDict (0.01s) instead of overwriting it. The solver runs with adaptive deltaT (~2.4e-7s), reporting physical time reached and final residuals. Velocity residuals reach O(10^-8) and enthalpy O(10^-9).

**Expected output:** "Convergence status: CONVERGED" with physical time reached and excellent residual levels.

---

### Step 14: Post-Process and View Nozzle Results

**What to say:** "Let's look at the results. You should see the classic nozzle physics: flow accelerates through the converging section, reaches maximum velocity at the throat, and you can see the pressure drop and shock structures in the diverging section."

**Prompt:**
```
Post-process the results for nozzle_demo and show me the velocity and pressure plots
```

**What happens:** The velocity contour shows acceleration from ~7 m/s at inlet to ~497 m/s at the throat. The pressure contour shows the drop from ~192 kPa to ~50 kPa with visible shock structures. These are physically correct compressible flow results.

---

## Demo Summary

**What to say:** "So that's the CFD Copilot workflow across three flow regimes. The duct case demonstrates clean convergence for incompressible internal flow. The airfoil case shows parametric geometry generation with O-grids for external aerodynamics. And the nozzle case proves we can handle compressible flow with shock capturing using rhoCentralFoam's density-based transient approach. All of this was driven by natural language descriptions through the Model Context Protocol -- no manual OpenFOAM dictionary editing required."

---

## Notes for Presenter

- **Timing:** Duct case (Steps 1-6) takes ~3 minutes. Airfoil case (Steps 7-9) takes ~2 minutes. Nozzle case (Steps 11-14) takes ~2 minutes if using pre-run results, longer if running live.
- **What to skip if short on time:** Skip Step 10 (airfoil solver) and go straight to Part 3. The nozzle is the most impressive result.
- **What NOT to claim:** Don't claim the airfoil case "fully converges" or is "production-ready." The README is honest about the mesh limitation, and the demo should be too.
- **Pre-run option:** The nozzle solver takes ~57 minutes of wall-clock time for a full run. For a live demo, use the pre-computed results in `cases/nozzle_rhocentral/` and just run the post-processing step.
- **Live vs. recorded:** If doing this live, practice the exact prompts beforehand so you can copy-paste them quickly. If recording, edit out any permission prompts or long pauses.
