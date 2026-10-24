import csv
from pathlib import Path
import numpy as np
from typing import Literal

try:
    from .mcp_instance import mcp
except ImportError:
    from mcp_instance import mcp


def naca_4digit(code: str, chord: float, num_points: int = 100) -> list[tuple[float, float]]:
    """Generate NACA 4-digit airfoil coordinates.

    Args:
        code: 4-digit NACA code (e.g., "2412")
        chord: Chord length in meters
        num_points: Number of points per surface

    Returns:
        List of (x, y) coordinate tuples
    """
    m = int(code[0]) / 100.0  # maximum camber
    p = int(code[1]) / 10.0   # location of maximum camber
    t = int(code[2:4]) / 100.0  # maximum thickness

    beta = np.linspace(0, np.pi, num_points)
    x = (1 - np.cos(beta)) / 2 * chord

    # Thickness distribution
    yt = 5 * t * chord * (
        0.2969 * np.sqrt(x / chord) -
        0.1260 * (x / chord) -
        0.3516 * (x / chord)**2 +
        0.2843 * (x / chord)**3 -
        0.1015 * (x / chord)**4
    )

    # Camber line
    yc = np.zeros_like(x)
    dyc_dx = np.zeros_like(x)

    for i, xi in enumerate(x):
        if xi < p * chord:
            if p != 0:
                yc[i] = m * xi / p**2 * (2 * p - xi / chord)
                dyc_dx[i] = 2 * m / p**2 * (p - xi / chord)
        else:
            if p != 1:
                yc[i] = m * (chord - xi) / (1 - p)**2 * (1 + xi / chord - 2 * p)
                dyc_dx[i] = 2 * m / (1 - p)**2 * (p - xi / chord)

    # Angle of camber line
    theta = np.arctan(dyc_dx)

    # Upper and lower surface coordinates
    xu = x - yt * np.sin(theta)
    yu = yc + yt * np.cos(theta)
    xl = x + yt * np.sin(theta)
    yl = yc - yt * np.cos(theta)

    # Combine upper and lower surfaces (counterclockwise from trailing edge)
    coords = []
    for i in range(len(xu) - 1, -1, -1):  # upper surface, TE to LE
        coords.append((xu[i], yu[i]))
    for i in range(1, len(xl)):  # lower surface, LE to TE
        coords.append((xl[i], yl[i]))

    return coords


def nozzle_profile(throat_radius: float, exit_radius: float, length: float,
                   num_points: int = 100) -> list[tuple[float, float]]:
    """Generate converging-diverging nozzle profile.

    Args:
        throat_radius: Throat radius in meters
        exit_radius: Exit radius in meters
        length: Total nozzle length in meters

    Returns:
        List of (x, y) coordinate tuples (axial position, radial position)
    """
    # Converging section (0 to 0.4*length)
    # Diverging section (0.4*length to length)
    x_conv = np.linspace(0, 0.4 * length, num_points // 2)
    x_div = np.linspace(0.4 * length, length, num_points // 2)

    # Smooth transition using cubic interpolation
    # Assume inlet radius = 1.5 * throat_radius
    inlet_radius = 1.5 * throat_radius

    # Converging section: cubic profile
    r_conv = inlet_radius - (inlet_radius - throat_radius) * (x_conv / (0.4 * length))**2

    # Diverging section: cubic profile
    r_div = throat_radius + (exit_radius - throat_radius) * ((x_div - 0.4 * length) / (0.6 * length))**2

    x = np.concatenate([x_conv, x_div])
    r = np.concatenate([r_conv, r_div])

    coords = [(xi, ri) for xi, ri in zip(x, r)]
    return coords


def duct_profile(radius: float, length: float, num_points: int = 50) -> list[tuple[float, float]]:
    """Generate straight duct profile.

    Args:
        radius: Duct radius in meters
        length: Duct length in meters

    Returns:
        List of (x, y) coordinate tuples (axial position, radial position)
    """
    x = np.linspace(0, length, num_points)
    coords = [(xi, radius) for xi in x]
    return coords


@mcp.tool()
def generate_geometry(
    shape_type: Literal["airfoil", "nozzle", "duct"],
    naca_code: str = "0012",
    chord_length: float = 1.0,
    throat_radius: float = 0.05,
    exit_radius: float = 0.1,
    radius: float = 0.1,
    length: float = 1.0
) -> str:
    """Generate 2D CFD geometry profiles and save as CSV.

    Creates coordinate points for common CFD geometries and saves them
    to cases/geometry/ directory.

    Args:
        shape_type: Type of geometry ("airfoil", "nozzle", or "duct")
        naca_code: NACA 4-digit code for airfoil (e.g., "2412", "0012")
        chord_length: Airfoil chord length in meters
        throat_radius: Nozzle throat radius in meters
        exit_radius: Nozzle exit radius in meters
        radius: Duct radius in meters
        length: Length in meters (for nozzle or duct)

    Returns:
        Summary string with shape type, dimensions, and file path
    """
    output_dir = Path("cases/geometry")
    output_dir.mkdir(parents=True, exist_ok=True)

    if shape_type == "airfoil":
        coords = naca_4digit(naca_code, chord_length)
        filename = f"naca_{naca_code}_c{chord_length:.3f}m.csv"
        summary = (f"Airfoil: NACA {naca_code}, chord={chord_length:.3f}m, "
                  f"{len(coords)} points")

    elif shape_type == "nozzle":
        coords = nozzle_profile(throat_radius, exit_radius, length)
        filename = f"nozzle_rt{throat_radius:.4f}_re{exit_radius:.4f}_L{length:.3f}m.csv"
        summary = (f"Nozzle: throat_r={throat_radius:.4f}m, exit_r={exit_radius:.4f}m, "
                  f"length={length:.3f}m, {len(coords)} points")

    elif shape_type == "duct":
        coords = duct_profile(radius, length)
        filename = f"duct_r{radius:.4f}_L{length:.3f}m.csv"
        summary = (f"Duct: radius={radius:.4f}m, length={length:.3f}m, "
                  f"{len(coords)} points")

    else:
        return f"Error: Unknown shape_type '{shape_type}'. Use 'airfoil', 'nozzle', or 'duct'."

    filepath = output_dir / filename
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['x', 'y'])
        writer.writerows(coords)

    return f"{summary}\nSaved to: {filepath}"
