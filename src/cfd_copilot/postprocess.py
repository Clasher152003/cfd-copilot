import subprocess
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from typing import Optional

try:
    from .mcp_instance import mcp
except ImportError:
    from mcp_instance import mcp

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _to_wsl_path(win_path: Path) -> str:
    p = win_path.resolve()
    return f"/mnt/{p.drive[0].lower()}{p.as_posix()[len(p.drive):]}"

# Set matplotlib to use non-interactive backend
plt.switch_backend('Agg')


def run_foamtovtk_wsl(case_name: str, timeout: int = 60) -> tuple[int, str, str]:
    """Run foamToVTK via WSL to convert OpenFOAM case to VTK format.

    Args:
        case_name: Name of the case to convert
        timeout: Maximum time in seconds to wait (default 60s)

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    wsl_path = _to_wsl_path(PROJECT_ROOT)

    cmd = [
        "wsl",
        "bash",
        "-c",
        f'source /usr/lib/openfoam/openfoam2406/etc/bashrc && cd {wsl_path} && foamToVTK -case cases/{case_name} -latestTime'
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout
    )

    return result.returncode, result.stdout, result.stderr


def find_vtk_file(case_path: Path) -> Optional[Path]:
    """Find the VTK file in the case directory.

    foamToVTK creates a VTK directory with timestep subdirectories.
    Structure: VTK/<case_name>_<timestep>/internal.vtu

    Args:
        case_path: Path to the case directory

    Returns:
        Path to the VTK file, or None if not found
    """
    vtk_dir = case_path / "VTK"
    if not vtk_dir.exists():
        return None

    timestep_dirs = sorted([d for d in vtk_dir.iterdir() if d.is_dir()])
    if not timestep_dirs:
        return None

    latest_timestep_dir = timestep_dirs[-1]

    internal_file = latest_timestep_dir / "internal.vtu"
    if internal_file.exists():
        return internal_file

    # Fallback: find any .vtu or .vtk file
    vtk_files = list(latest_timestep_dir.glob("*.vtu")) + list(latest_timestep_dir.glob("*.vtk"))
    if vtk_files:
        return vtk_files[0]

    return None


@mcp.tool()
def postprocess_results(case_name: str) -> str:
    """Extract and visualize results from a solved OpenFOAM case.

    Reads velocity and pressure fields from the latest timestep, computes
    statistics, and generates contour plots using matplotlib.

    Args:
        case_name: Name of the solved case (must have been run with run_solver)

    Returns:
        Summary with statistics and paths to generated visualization files
    """
    base_path = Path("cases") / case_name

    if not base_path.exists():
        return f"Error: Case directory not found: {base_path}"

    try:
        returncode, stdout, stderr = run_foamtovtk_wsl(case_name)
        if returncode != 0:
            error_msg = f"Error: foamToVTK failed with return code {returncode}\n"
            if stderr:
                error_msg += f"stderr: {stderr}\n"
            if stdout:
                error_msg += f"stdout: {stdout}\n"
            return error_msg
    except subprocess.TimeoutExpired:
        return "Error: foamToVTK timed out"
    except Exception as e:
        return f"Error running foamToVTK: {e}"

    vtk_file = find_vtk_file(base_path)
    if vtk_file is None:
        return f"Error: Could not find VTK file in {base_path / 'VTK'}"

    try:
        import pyvista as pv
        mesh = pv.read(str(vtk_file))
    except Exception as e:
        return f"Error reading VTK file {vtk_file}: {e}"

    if 'U' not in mesh.array_names:
        return f"Error: Velocity field 'U' not found in VTK file. Available fields: {mesh.array_names}"

    if 'p' not in mesh.array_names:
        return f"Error: Pressure field 'p' not found in VTK file. Available fields: {mesh.array_names}"

    velocity = mesh['U']
    pressure = mesh['p']

    if velocity.ndim == 2 and velocity.shape[1] >= 2:
        u_mag = np.sqrt(velocity[:, 0]**2 + velocity[:, 1]**2)
    else:
        u_mag = np.abs(velocity.flatten())

    cell_centers = mesh.cell_centers()
    x = cell_centers.points[:, 0]
    y = cell_centers.points[:, 1]

    u_min, u_max, u_avg = u_mag.min(), u_mag.max(), u_mag.mean()
    p_min, p_max, p_avg = pressure.min(), pressure.max(), pressure.mean()

    fig, ax = plt.subplots(figsize=(10, 6))
    scatter = ax.tricontourf(x, y, u_mag, levels=20, cmap='viridis')
    cbar = plt.colorbar(scatter, ax=ax, label='Velocity Magnitude (m/s)')
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_title(f'Velocity Magnitude - {case_name}')
    ax.set_aspect('equal')
    plt.tight_layout()

    velocity_png = base_path / "results_velocity.png"
    plt.savefig(velocity_png, dpi=150, bbox_inches='tight')
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 6))
    scatter = ax.tricontourf(x, y, pressure, levels=20, cmap='RdBu_r')
    cbar = plt.colorbar(scatter, ax=ax, label='Pressure (Pa)')
    ax.set_xlabel('X (m)')
    ax.set_ylabel('Y (m)')
    ax.set_title(f'Pressure Distribution - {case_name}')
    ax.set_aspect('equal')
    plt.tight_layout()

    pressure_png = base_path / "results_pressure.png"
    plt.savefig(pressure_png, dpi=150, bbox_inches='tight')
    plt.close(fig)

    summary = f"Postprocessing completed for case: {case_name}\n"
    summary += f"Number of cells: {len(cell_centers.points)}\n\n"

    summary += "Velocity Statistics:\n"
    summary += f"  Min magnitude: {u_min:.6e} m/s\n"
    summary += f"  Max magnitude: {u_max:.6e} m/s\n"
    summary += f"  Avg magnitude: {u_avg:.6e} m/s\n\n"

    summary += "Pressure Statistics:\n"
    summary += f"  Min: {p_min:.6e} Pa\n"
    summary += f"  Max: {p_max:.6e} Pa\n"
    summary += f"  Avg: {p_avg:.6e} Pa\n\n"

    summary += "Generated visualizations:\n"
    summary += f"  Velocity: {velocity_png}\n"
    summary += f"  Pressure: {pressure_png}\n"

    return summary


@mcp.tool()
def get_force_coefficients(case_name: str) -> str:
    """Extract lift and drag coefficients from OpenFOAM forceCoeffs output.

    Reads the coefficient.dat file generated by the forceCoeffs function object
    during the solver run and returns the final (converged) Cl and Cd values.

    The forceCoeffs function object must be enabled in system/controlDict before
    running the solver. For external flow cases, this is automatically included
    when setup_case is called with flow_type="external".

    Args:
        case_name: Name of the case (must have been run with forceCoeffs enabled)

    Returns:
        Summary string with final lift coefficient (Cl), drag coefficient (Cd),
        and moment coefficient (Cm) values, or error message if data not available
    """
    case_path = Path("cases") / case_name
    if not case_path.exists():
        return f"Error: Case '{case_name}' does not exist."

    force_coeffs_path = case_path / "postProcessing" / "forceCoeffs1" / "0" / "coefficient.dat"

    if not force_coeffs_path.exists():
        error_msg = f"Error: Force coefficient data not found for case '{case_name}'.\n\n"
        error_msg += "The forceCoeffs function object must be enabled in system/controlDict\n"
        error_msg += "BEFORE running the solver. To generate force coefficient data:\n\n"
        error_msg += "1. Re-run setup_case with flow_type='external' and chord_length parameter\n"
        error_msg += "   (this adds the forceCoeffs function to controlDict)\n"
        error_msg += "2. Re-run the solver with run_solver\n"
        error_msg += "3. Then call get_force_coefficients again\n\n"
        error_msg += f"Expected file location: {force_coeffs_path}"
        return error_msg

    try:
        with open(force_coeffs_path, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        return f"Error reading coefficient file: {e}"

    data_lines = [line for line in lines if not line.strip().startswith('#') and line.strip()]

    if not data_lines:
        return f"Error: No data found in {force_coeffs_path}"

    last_line = data_lines[-1].strip()

    try:
        # Column format: Time Cd Cd(f) Cd(r) Cl Cl(f) Cl(r) CmPitch CmRoll CmYaw Cs Cs(f) Cs(r)
        parts = last_line.split()
        if len(parts) < 8:
            return f"Error: Invalid data format in coefficient file. Expected at least 8 columns, got {len(parts)}"

        time_val = float(parts[0])
        Cd = float(parts[1])
        Cl = float(parts[4])
        Cm = float(parts[7])  # CmPitch

        Cl_f = float(parts[5]) if len(parts) > 5 else None
        Cl_r = float(parts[6]) if len(parts) > 6 else None

    except (ValueError, IndexError) as e:
        return f"Error parsing coefficient data: {e}\nLast line: {last_line}"

    summary = f"Force coefficients for case: {case_name}\n"
    summary += f"Data source: {force_coeffs_path}\n\n"
    summary += f"Final values (iteration/time = {time_val}):\n"
    summary += f"  Lift coefficient (Cl):   {Cl:>10.6f}\n"
    summary += f"  Drag coefficient (Cd):   {Cd:>10.6f}\n"
    summary += f"  Moment coefficient (Cm): {Cm:>10.6f}\n"

    if Cl_f is not None and Cl_r is not None:
        summary += f"\n  Cl decomposition:\n"
        summary += f"    Front contribution: {Cl_f:>10.6f}\n"
        summary += f"    Rear contribution:  {Cl_r:>10.6f}\n"

    if abs(Cd) > 1e-10:
        lift_to_drag = Cl / Cd
        summary += f"\n  Lift-to-drag ratio (L/D): {lift_to_drag:>10.3f}\n"

    summary += f"\nTotal data points in file: {len(data_lines)}\n"
    summary += "\nNote: These coefficients are based on the reference values specified\n"
    summary += "in system/controlDict (rhoInf, magUInf, lRef, Aref)."

    return summary
