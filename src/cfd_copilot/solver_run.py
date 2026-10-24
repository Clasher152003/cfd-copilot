import re
import subprocess
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


def read_solver_from_controldict(case_name: str) -> str:
    """Read the application entry from system/controlDict.

    Args:
        case_name: Name of the case

    Returns:
        Solver name (e.g., "simpleFoam", "rhoSimpleFoam")

    Raises:
        FileNotFoundError: If controlDict doesn't exist
        ValueError: If application entry not found
    """
    controldict_path = PROJECT_ROOT / "cases" / case_name / "system" / "controlDict"

    if not controldict_path.exists():
        raise FileNotFoundError(f"controlDict not found at {controldict_path}")

    with open(controldict_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('application'):
                parts = line.split()
                if len(parts) >= 2:
                    solver = parts[1].rstrip(';')
                    return solver

    raise ValueError(f"Could not find 'application' entry in {controldict_path}")


def run_solver_wsl(case_name: str, solver_name: str, timeout: int = 300) -> tuple[int, str, str]:
    """Run OpenFOAM solver via WSL.

    Args:
        case_name: Name of the case to run
        solver_name: Name of the solver (e.g., "simpleFoam", "rhoSimpleFoam")
        timeout: Maximum time in seconds to wait for solver (default 300s = 5 min)

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    wsl_path = _to_wsl_path(PROJECT_ROOT)

    cmd = [
        "wsl",
        "bash",
        "-c",
        f'source /usr/lib/openfoam/openfoam2406/etc/bashrc && cd {wsl_path} && {solver_name} -case cases/{case_name}'
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout
    )

    return result.returncode, result.stdout, result.stderr


def parse_solver_output(stdout: str) -> dict[str, any]:
    """Parse OpenFOAM solver output to extract residuals and iteration count.

    OpenFOAM prints lines like:
    smoothSolver:  Solving for Ux, Initial residual = 1, Final residual = 0.001, No Iterations 10
    GAMG:  Solving for p, Initial residual = 1, Final residual = 0.0005, No Iterations 5

    For compressible solvers (rhoSimpleFoam), additional fields like T, e, rho may be present.

    And iteration markers like:
    Time = 1
    Time = 2

    We want the LAST occurrence of each field's final residual.

    Returns:
        Dict with keys: iterations, residuals (dict with field names as keys), converged
    """
    residuals = {}
    iterations = 0

    # Pattern to match solver output lines
    # Example: "smoothSolver:  Solving for Ux, Initial residual = 0.1, Final residual = 0.001, No Iterations 5"
    solver_pattern = re.compile(
        r'Solving for (\w+),.*Final residual = ([\d.eE+-]+)'
    )

    # Pattern to match iteration counter (integer for steady, float for transient)
    # Examples: "Time = 123" or "Time = 0.00842766"
    time_pattern = re.compile(r'^Time = ([\d.eE+-]+)', re.MULTILINE)

    time_matches = time_pattern.findall(stdout)
    if time_matches:
        iterations = float(time_matches[-1])

    for line in stdout.split('\n'):
        match = solver_pattern.search(line)
        if match:
            field_name = match.group(1)
            final_residual = float(match.group(2))
            residuals[field_name] = final_residual

    if iterations == int(iterations) and iterations < 1e9:
        iterations = int(iterations)

    return {
        'iterations': iterations,
        'residuals': residuals,
    }


def check_convergence(residuals: dict[str, float], solver_name: str, threshold: float = 1e-4) -> tuple[bool, str]:
    """Check if solver has converged based on residuals.

    For transient solvers like rhoCentralFoam, convergence means reaching a steady
    flow pattern (completion without crash), not residual thresholds.
    For steady solvers like simpleFoam/rhoSimpleFoam, check residual thresholds.

    Args:
        residuals: Dict mapping field names to final residuals
        solver_name: Name of the solver (e.g., "rhoCentralFoam", "rhoSimpleFoam")
        threshold: Convergence threshold for steady solvers (default 1e-4 for demo quality)

    Returns:
        Tuple of (converged: bool, message: str)
    """
    if not residuals:
        return False, "No residual data found"

    # For transient density-based solvers, don't check residuals against a threshold
    # (they're explicit and don't iterate to convergence like SIMPLE)
    if solver_name == "rhoCentralFoam":
        # If we got residuals and the solver completed, it's converged to a steady flow pattern
        return True, f"Transient simulation completed. Final residuals: {', '.join(f'{k}: {v:.2e}' for k, v in residuals.items())}"

    # For steady-state solvers, check residual thresholds
    converged_fields = []
    unconverged_fields = []

    for field, residual in residuals.items():
        if residual <= threshold:
            converged_fields.append(f"{field}: {residual:.2e}")
        else:
            unconverged_fields.append(f"{field}: {residual:.2e}")

    if not unconverged_fields:
        return True, f"All fields converged (< {threshold:.0e}): {', '.join(converged_fields)}"
    else:
        return False, f"Not fully converged. Unconverged: {', '.join(unconverged_fields)}. Converged: {', '.join(converged_fields) if converged_fields else 'none'}"


def get_last_n_lines(text: str, n: int = 20) -> str:
    """Get the last N lines of text."""
    lines = text.strip().split('\n')
    return '\n'.join(lines[-n:])


def get_latest_time(case_path: Path) -> float:
    """Get the latest time directory value in a case.

    Args:
        case_path: Path to the case directory

    Returns:
        Latest time as a float, or 0.0 if no time directories exist
    """
    time_dirs = []
    for d in case_path.iterdir():
        if d.is_dir():
            try:
                # Try to parse as a number
                time_val = float(d.name)
                time_dirs.append(time_val)
            except ValueError:
                # Not a numeric directory (e.g., "system", "constant")
                continue

    return max(time_dirs) if time_dirs else 0.0


def update_controldict_endtime(case_name: str, new_endtime: float) -> tuple[float, float]:
    """Update the endTime entry in system/controlDict.

    Args:
        case_name: Name of the case
        new_endtime: New endTime value to set

    Returns:
        Tuple of (old_endtime, new_endtime) for verification

    Raises:
        ValueError: If endTime entry not found or could not be updated
    """
    controldict_path = PROJECT_ROOT / "cases" / case_name / "system" / "controlDict"

    if not controldict_path.exists():
        raise FileNotFoundError(f"controlDict not found at {controldict_path}")

    with open(controldict_path, 'r') as f:
        lines = f.readlines()

    old_endtime = None
    updated_lines = []
    endtime_found = False

    for line in lines:
        if line.strip().startswith('endTime'):
            parts = line.split()
            if len(parts) >= 2:
                old_endtime = float(parts[1].rstrip(';'))
            updated_lines.append(f"endTime         {new_endtime};\n")
            endtime_found = True
        else:
            updated_lines.append(line)

    if not endtime_found:
        raise ValueError(f"Could not find 'endTime' entry in {controldict_path}")

    with open(controldict_path, 'w') as f:
        f.writelines(updated_lines)

    with open(controldict_path, 'r') as f:
        for line in f:
            if line.strip().startswith('endTime'):
                parts = line.split()
                if len(parts) >= 2:
                    verified_endtime = float(parts[1].rstrip(';'))
                    if abs(verified_endtime - new_endtime) > 1e-9:
                        raise ValueError(f"endTime verification failed: wrote {new_endtime}, read back {verified_endtime}")
                    break

    return old_endtime if old_endtime is not None else 0.0, new_endtime


@mcp.tool()
def run_solver(
    case_name: str,
    max_iterations: Optional[int] = 500,
    continue_from_latest: bool = False
) -> str:
    """Run OpenFOAM solver on a fully set-up case and report convergence.

    The case must already exist with mesh generated (via generate_mesh) and
    boundary conditions configured (via setup_case). This tool reads the solver
    name from system/controlDict and runs it (simpleFoam for incompressible,
    rhoSimpleFoam for compressible, etc.), then monitors convergence and reports
    final residuals.

    Args:
        case_name: Name of existing case (must be fully set up)
        max_iterations: Safety cap on iterations (default 500), set via controlDict endTime
        continue_from_latest: If True, continue from latest time folder instead of
                            restarting from time 0 (default False). OpenFOAM automatically
                            picks up from the latest time directory when multiple exist.

    Returns:
        Summary of solver run: iterations completed, final residuals for all
        solved fields (Ux, Uy, p, T, e, rho, etc.), convergence status,
        and diagnostic info if the run failed
    """
    case_path = PROJECT_ROOT / "cases" / case_name

    try:
        solver_name = read_solver_from_controldict(case_name)
    except (FileNotFoundError, ValueError) as e:
        return f"Error: Could not determine solver from controlDict: {e}"

    latest_time = get_latest_time(case_path)
    is_continuation = continue_from_latest and latest_time > 0

    # Transient solvers use physical endTime from case_setup; don't overwrite
    TRANSIENT_SOLVERS = {"rhoCentralFoam", "rhoPimpleFoam", "pimpleFoam"}
    is_transient = solver_name in TRANSIENT_SOLVERS

    endtime_info = ""
    if max_iterations and not is_transient:
        if is_continuation:
            new_endtime = latest_time + max_iterations
            endtime_info = f"Extending endTime from {latest_time} to {new_endtime} (+{max_iterations} iterations)\n"
        else:
            new_endtime = max_iterations
            endtime_info = f"Setting endTime to {new_endtime} iterations\n"

        try:
            old_endtime, verified_endtime = update_controldict_endtime(case_name, new_endtime)
            endtime_info += f"controlDict endTime updated: {old_endtime} -> {verified_endtime}\n"
        except Exception as e:
            return f"Error: Could not update controlDict endTime: {e}"
    elif is_transient:
        endtime_info = f"Transient solver ({solver_name}): using endTime from controlDict\n"

    try:
        timeout = max(300, max_iterations * 2) if (max_iterations and not is_transient) else 600
        returncode, stdout, stderr = run_solver_wsl(case_name, solver_name, timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"Error: {solver_name} timed out after {timeout} seconds. The solver may be diverging or the case is too large."
    except Exception as e:
        return f"Error running {solver_name}: {e}"

    log_path = case_path / f"log.{solver_name}"
    log_mode = 'a' if is_continuation else 'w'
    log_saved = False
    log_error = None

    try:
        with open(log_path, log_mode) as f:
            if is_continuation:
                f.write(f"\n\n{'='*60}\n")
                f.write(f"=== CONTINUATION RUN (from time {latest_time}) ===\n")
                f.write(f"{'='*60}\n\n")
            f.write(stdout)
            if stderr:
                f.write("\n\n=== STDERR ===\n\n")
                f.write(stderr)
        log_saved = True
    except Exception as e:
        log_error = str(e)

    if returncode != 0 and not stdout:
        error_msg = f"{solver_name} failed with return code {returncode}\n\n"
        if stderr:
            error_msg += f"Error output:\n{stderr}"
        return error_msg

    parse_result = parse_solver_output(stdout)
    iterations = parse_result['iterations']
    residuals = parse_result['residuals']

    converged, conv_message = check_convergence(residuals, solver_name)

    summary = f"Solver run completed for case: {case_name}\n"
    summary += f"Solver: {solver_name}\n"
    if is_continuation:
        summary += f"Mode: Continuation from time {latest_time}\n"
    if endtime_info:
        summary += endtime_info
    if log_saved:
        summary += f"Full solver output saved to: {log_path}\n"
    elif log_error:
        summary += f"Warning: Could not save log file: {log_error}\n"
    summary += "\n"

    if is_transient:
        summary += f"Physical time reached: {iterations}s"
    else:
        summary += f"Iterations: {iterations}"
        if max_iterations:
            summary += f" (max: {max_iterations})"
    summary += "\n\n"

    if residuals:
        summary += "Final residuals:\n"
        for field in ['Ux', 'Uy', 'Uz']:
            if field in residuals:
                summary += f"  {field}: {residuals[field]:.6e}\n"
        if 'p' in residuals:
            summary += f"  p: {residuals['p']:.6e}\n"
        for field in ['T', 'e', 'h', 'rho']:
            if field in residuals:
                summary += f"  {field}: {residuals[field]:.6e}\n"
        for field, value in residuals.items():
            if field not in ['Ux', 'Uy', 'Uz', 'p', 'T', 'e', 'h', 'rho']:
                summary += f"  {field}: {value:.6e}\n"
    else:
        summary += "Warning: Could not extract residual data from solver output\n"

    summary += f"\nConvergence status: {'CONVERGED' if converged else 'NOT CONVERGED'}\n"
    summary += f"{conv_message}\n"

    if returncode != 0 or not converged:
        summary += "\n" + "="*60 + "\n"
        summary += "Diagnostic info (last 20 lines of solver output):\n"
        summary += "="*60 + "\n"
        summary += get_last_n_lines(stdout, 20)

        if stderr:
            summary += "\n\nStderr output:\n"
            summary += stderr

    if returncode != 0:
        summary += "\n\nSolver exited with errors. Common causes:"
        summary += "\n  - Mesh quality issues (check with checkMesh)"
        summary += "\n  - Unstable relaxation factors"
        summary += "\n  - Bad initial/boundary conditions"
        summary += "\n  - Divergence due to high velocities or gradients"

    return summary
