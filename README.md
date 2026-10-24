# CFD Copilot

**An MCP server for natural-language OpenFOAM workflows**

CFD Copilot is a [Model Context Protocol](https://modelcontextprotocol.io) server that lets CFD engineers describe simulations in plain language and get OpenFOAM geometry generation, meshing, case setup, solving, and post-processing automated end-to-end. Instead of manually writing blockMeshDict files and boundary condition dictionaries, you describe what you want ("simulate flow through a 2D duct", "NACA airfoil at 5 deg angle of attack", "supersonic nozzle") and the MCP client handles the OpenFOAM workflow.

This is a **working prototype** with validated results on internal flows (ducts), external aerodynamics (airfoils), and compressible flows (supersonic nozzles).

---

## What This Does

CFD Copilot provides seven MCP tools that chain together to automate a complete OpenFOAM workflow:

1. **`ping`** -- Health check to verify the MCP server is connected and responsive
2. **`generate_geometry`** -- Creates blockMeshDict files from natural language descriptions (ducts, airfoils with O-grids, nozzles with grading)
3. **`generate_mesh`** -- Runs blockMesh via WSL to produce the actual mesh
4. **`setup_case`** -- Generates boundary condition files (U, p, thermophysical properties) based on flow regime
5. **`run_solver`** -- Executes OpenFOAM solvers (simpleFoam, rhoSimpleFoam, rhoCentralFoam) and monitors convergence
6. **`postprocess_results`** -- Runs foamToVTK to convert results, loads them with PyVista, and generates matplotlib contour plots
7. **`get_force_coefficients`** -- Extracts lift, drag, and moment coefficients (Cl, Cd, Cm) from OpenFOAM's forceCoeffs output for aerodynamic analysis

These tools work with any MCP-compatible AI client.

---

## Architecture

The server is built on the Python `mcp` library and exposes each tool as a typed function with clear docstrings. When you describe a simulation in natural language, the AI:

1. Calls `generate_geometry` to create parametric blockMeshDict (handles rectangular ducts, NACA airfoils with O-grids, converging-diverging nozzles)
2. Calls `generate_mesh` to run blockMesh in WSL and verify mesh statistics
3. Calls `setup_case` to write boundary condition dictionaries (0/U, 0/p, constant/transportProperties or thermophysicalProperties)
4. Calls `run_solver` to execute the appropriate OpenFOAM solver, parse residuals, and check convergence
5. Calls `postprocess_results` to run foamToVTK, load fields with PyVista, and generate matplotlib contour plots as PNG files

Each tool validates inputs, reports errors clearly, and logs full OpenFOAM output to `cases/<case_name>/log.<solver_name>` for debugging.

---

## Working Demo: 2D Duct Flow

A 1m x 1m square duct with laminar incompressible flow converges cleanly and produces physically correct results:

- **Geometry**: Structured hex mesh, 20x20x1 cells (2D case with one cell in z-direction)
- **Mesh quality**: All metrics within OpenFOAM tolerance (orthogonality, skewness, aspect ratio)
- **Solver**: simpleFoam (SIMPLE pressure-velocity coupling)
- **Inlet velocity**: 5.0 m/s
- **Convergence**: 126 iterations (stopped early from max 500 iterations when residuals converged)
- **Physics validation**: Velocity and pressure fields show physically correct behavior with no-slip walls and proper pressure distribution

### Reproducing the duct case

With the MCP server connected:

```
Create a 2D duct flow simulation:
- Square duct 1m x 1m
- Inlet velocity 5 m/s
- Laminar incompressible flow
- Run simpleFoam for 500 iterations max
- Generate velocity and pressure contour plots
```

The AI will call the tools in sequence, and you'll get converged results and plots in `cases/<case_name>/results_velocity.png` and `results_pressure.png`.

---

## Second Demo: NACA Airfoil External Flow

A NACA 2412 airfoil at 5° angle of attack with external flow boundary conditions runs successfully but has mesh-related convergence limitations:

- **Geometry**: NACA 4-digit parametric airfoil with O-grid topology (structured mesh wrapping the airfoil)
- **Mesh**: 100x50x1 cells (4 blocks of 25x50 each), radial grading factor 10 to capture boundary layer
- **Boundary conditions**: `freestreamVelocity` and `freestreamPressure` at far-field boundary, no-slip wall on airfoil surface
- **Inlet velocity**: 20 m/s at 5° angle of attack
- **Solver**: simpleFoam
- **Convergence**: Velocity residuals (Ux, Uy) converge to ~2-6×10⁻⁵, but **pressure stalls at ~1×10⁻³** instead of reaching the typical 1×10⁻⁴ threshold

**Known issue**: The mesh has borderline skewness near the leading edge where the O-grid wraps the curved nose. This prevents full pressure convergence in simpleFoam's SIMPLE algorithm, which is sensitive to mesh non-orthogonality. After 2000 iterations, velocity fields are well-converged but pressure residuals plateau.

**Fix path**: Refine the near-body grading (increase radial cell count) and adjust the O-grid stretching ratio to reduce skewness below 0.5. Standard mesh quality improvement, not a fundamental flaw -- the geometry generator already has the necessary grading parameters.

### Reproducing the airfoil case

```
Create a NACA 2412 airfoil simulation:
- 2D external flow around airfoil
- 5 degree angle of attack
- Freestream velocity 20 m/s
- Run simpleFoam for 2000 iterations
- Plot velocity and pressure fields
```

You'll get physically reasonable results (flow accelerates over the upper surface, stagnation point at the nose, wake behind the trailing edge), but pressure residuals stall around 1e-3. Good enough for qualitative flow visualization, not production aerodynamics.

---

## Third Demo: Compressible Converging-Diverging Nozzle

A converging-diverging nozzle with compressible flow runs successfully with the transient density-based rhoCentralFoam solver:

- **Geometry**: 0.5m length, inlet radius 0.075m, throat radius 0.05m (at x=0.2m), outlet radius 0.1m, axisymmetric wedge mesh
- **Mesh**: 50x30x1 cells (1500 cells total) with uniform grading
- **Boundary conditions**: Total pressure inlet (200,000 Pa, 350 K), static pressure outlet (120,000 Pa), noSlip walls, wedge patches for axisymmetry, symmetry centerline
- **Solver**: rhoCentralFoam (transient density-based compressible solver with Kurganov-Tadmor scheme)
- **Time integration**: Adaptive time-stepping with max Co 0.5, deltaT ~2.4e-7s, simulated to ~0.0084s
- **Physics validation**: 
  - Velocity accelerates from 6.7 m/s at inlet to **497 m/s maximum** at throat
  - Pressure drops from 191.5 kPa to **49.8 kPa minimum** at throat, then partially recovers
  - Flow exhibits correct compressible nozzle behavior with shock structures visible in pressure field
  - All residuals converge to excellent levels (velocity O(10⁻⁸), enthalpy O(10⁻⁹))

rhoCentralFoam with adaptive time-stepping and the Kurganov-Tadmor flux scheme produces stable, physically correct compressible flow. The transient density-based approach naturally handles strong pressure gradients and shock discontinuities that steady-state solvers (rhoSimpleFoam) struggle with.

### Reproducing the nozzle case

```
Create a compressible nozzle simulation:
- Converging-diverging nozzle 0.5m length
- Inlet radius 0.075m, throat 0.05m, outlet 0.1m
- Total pressure inlet 200 kPa at 350K
- Static pressure outlet 120 kPa
- Use rhoCentralFoam for compressible flow
- Plot velocity and pressure fields
```

The AI will set up the case with proper compressible boundary conditions and run rhoCentralFoam until the flow reaches quasi-steady state.

---

## Current Limitations

- **Geometry**: Only blockMesh-based structured grids. No snappyHexMesh for arbitrary CAD geometries.
- **Turbulence**: Only laminar flow. No RANS models (k-epsilon, k-omega SST) implemented yet.
- **Meshing**: No adaptive mesh refinement. Fixed cell count specified upfront.
- **Post-processing**: VTK files are generated (via foamToVTK) but only used to produce PNG contour plots. Force coefficients (Cl/Cd/Cm) are supported for external flow cases, but no streamlines or interactive ParaView workflows yet.
- **Validation**: No automated mesh convergence studies or comparison to analytical solutions.

---

## Setup

### Prerequisites

- **OpenFOAM v2406** installed in WSL (Ubuntu recommended)
- **Python 3.8+** with venv
- An MCP-compatible AI client (e.g., Cursor, or any tool supporting the protocol)

### Installation

1. **Install OpenFOAM in WSL**:
   ```bash
   # In WSL Ubuntu
   curl https://dl.openfoam.com/add-debian-repo.sh | sudo bash
   sudo apt-get update
   sudo apt-get install openfoam2406-default
   ```

2. **Clone and set up Python environment**:
   ```bash
   git clone <repository-url>
   cd cfd-copilot
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   pip install mcp numpy matplotlib pyvista
   ```

3. **Register the MCP server**:
   
   Register the server with your MCP client using transport `stdio` and command:
   ```bash
   python src/cfd_copilot/server.py
   ```
   
   Consult your client's documentation for exact registration steps.

4. **Verify the connection**:
   
   In your MCP client, run:
   ```
   Call the cfd-copilot ping tool to verify the connection
   ```
   
   You should see a response like `"cfd-copilot server received: hello"`.

### Troubleshooting

- **"blockMesh: command not found"**: Ensure OpenFOAM is sourced in your WSL shell. The server sources it automatically via `/usr/lib/openfoam/openfoam2406/etc/bashrc`.
- **WSL path issues**: The code assumes cases are stored at `/mnt/c/Users/<username>/cfd-copilot/cases`. Adjust paths in the source files if your setup differs.
- **Permission errors**: Ensure the Python script has execute permissions and the cases directory is writable.

---

## Usage Example

Once connected, describe your simulation in natural language:

```
I need to simulate laminar flow through a 2D square duct:
- 1 meter × 1 meter cross-section
- Inlet velocity 5 m/s
- Outlet pressure 0 Pa
- Run simpleFoam for up to 500 iterations
- Generate velocity magnitude and pressure contour plots
```

The AI will:
1. Generate blockMeshDict for a 1m×1m duct with appropriate cell count (typically 20×20×1)
2. Run blockMesh and verify mesh quality
3. Create 0/U (velocity) and 0/p (pressure) boundary condition files with proper boundary types
4. Run simpleFoam, monitoring residuals every iteration
5. Report convergence status (iterations, final residuals)
6. Run foamToVTK to convert results to VTK format
7. Load VTK data with PyVista and generate matplotlib plots
8. Save results as `cases/<case_name>/results_velocity.png` and `results_pressure.png`

All OpenFOAM output is logged to `cases/<case_name>/log.<solver_name>` for verification.

---

## Project Structure

```
cfd-copilot/
├── src/cfd_copilot/
│   ├── server.py          # MCP server entry point, imports all tools
│   ├── mcp_instance.py    # Shared MCP instance
│   ├── geometry.py        # generate_geometry tool (blockMeshDict generation)
│   ├── meshing.py         # generate_mesh tool (blockMesh execution)
│   ├── case_setup.py      # setup_case tool (boundary conditions)
│   ├── solver_run.py      # run_solver tool (simpleFoam/rhoSimpleFoam/rhoCentralFoam)
│   └── postprocess.py     # postprocess_results tool (foamToVTK, PyVista, matplotlib)
└── cases/                 # Generated OpenFOAM case directories
    ├── geometry/          # Generated geometry CSV files (airfoil coordinates, etc.)
    ├── duct_test_3/       # Converged duct case (126 iterations, 20×20×1 mesh)
    ├── airfoil_test/      # NACA 2412 airfoil case (pressure convergence limited by mesh quality)
    └── nozzle_rhocentral/ # Supersonic nozzle case (rhoCentralFoam, max velocity 497 m/s at throat)
```

---

## Roadmap

If this prototype proves useful, a **v2** would address:

1. **snappyHexMesh integration**: Support for arbitrary STL geometries (import a CAD model, mesh it automatically)
2. **Turbulence modeling**: RANS models (k-epsilon, k-omega SST) for high Reynolds number flows
3. **Mesh convergence studies**: Automatically run the same case at multiple mesh resolutions and report sensitivity
4. **Interactive ParaView workflow**: Keep VTK files accessible and provide ParaView state files for 3D interactive visualization
5. **Streamline visualization**: Add streamline/pathline plotting for better flow field visualization
6. **GUI/reporting layer**: A web dashboard showing residual plots, mesh statistics, and results in one place (instead of raw PNG files)
7. **Validation library**: Automated comparison to analytical solutions (Poiseuille flow, potential flow over a cylinder, oblique shock theory for nozzles, etc.)
8. **3D cases**: Extend beyond 2D (single-cell-thickness) to full 3D meshes with proper boundary conditions

---

## Technical Details

### Why blockMesh?

blockMesh is OpenFOAM's structured mesh generator. It's verbose and manual, which is why most engineers hate writing blockMeshDict files by hand. But it's also:
- **Parametric**: Every vertex, cell count, and grading ratio is explicit and scriptable
- **High quality**: Produces structured hex meshes with excellent orthogonality (critical for pressure convergence)
- **Robust**: If the input is valid, the mesh is guaranteed to be topologically sound

For a natural-language workflow, this is ideal. The AI can generate blockMeshDict from geometry descriptions without worrying about mesh topology failures. snappyHexMesh (for arbitrary geometries) is more powerful but also more brittle; it's a v2 feature.

### Why MCP?

The Model Context Protocol decouples the AI from the tools. This server works with any MCP-compatible client without modification. Tools are versioned, typed (via function signatures), and self-documenting (docstrings are sent to the AI as context). It's a cleaner architecture than hardcoding commands into a single AI assistant.

The server is implemented using the Python `mcp` library and exposes tools via the `@mcp.tool()` decorator. Each tool's function signature and docstring automatically become the MCP tool schema.

### Solver Selection

- **simpleFoam**: Steady-state incompressible flow (pressure-based SIMPLE algorithm). Used for the duct and airfoil cases.
- **rhoSimpleFoam**: Steady-state compressible flow (density-based SIMPLE). Suitable for subsonic compressible cases.
- **rhoCentralFoam**: Transient compressible flow (density-based Kurganov-Tadmor). Successfully used for the supersonic nozzle case with adaptive time-stepping and Courant number control.

The `run_solver` tool reads the `application` entry in `system/controlDict` to determine which solver to run, no hardcoding required. Full solver output (stdout and stderr) is logged to `cases/<case_name>/log.<solver_name>` for debugging and residual verification. For rhoCentralFoam, the solver runs until reaching the specified `endTime` with automatic time-step adjustment to maintain stability (max Courant number 0.5).

### Convergence Criteria

The `run_solver` tool parses residual output from OpenFOAM and checks convergence against a default threshold of 1×10⁻⁴ for steady-state solvers (simpleFoam, rhoSimpleFoam). For transient solvers (rhoCentralFoam), convergence is determined by successful completion without divergence. The convergence checking logic is in `src/cfd_copilot/solver_run.py:check_convergence()`.

---

## Contributing

This is a prototype. If you're a CFD engineer interested in improving it:

- **Airfoil mesh quality**: The O-grid generator in `geometry.py` works and includes radial grading (factor of 10), but the leading-edge cell distribution could be improved to reduce skewness below 0.5. If you can tune the grading or add more sophisticated cell clustering to improve pressure convergence, please contribute.
- **New geometries**: The `generate_geometry` tool currently supports ducts, NACA airfoils, and nozzles. Adding cylinders, backward-facing steps, diffusers, or other canonical CFD cases would make this more useful.
- **Turbulence models**: Extending `case_setup.py` to support RANS models (k-epsilon, k-omega SST) would enable high Reynolds number flows and more realistic engineering simulations.

---

## License

MIT License. See LICENSE file for details.

---

## Acknowledgments

- **OpenFOAM Foundation**: For OpenFOAM, the open-source CFD toolbox
- **Anthropic**: For Claude and the Model Context Protocol specification
- **CFD community**: For decades of documentation, forum posts, and validated test cases that made this possible

---

## Disclaimer

This is a **demonstration project**, not production-ready CFD software. Results should be validated against known solutions, mesh convergence studies should be performed, and physical intuition should always override what the AI generates. The authors are not responsible for incorrect simulations, mesh quality issues, or any decisions made based on outputs from this tool.

If you're doing safety-critical or published research CFD work, use this as a workflow accelerator, not a replacement for CFD expertise.
