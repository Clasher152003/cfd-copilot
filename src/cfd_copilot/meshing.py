import subprocess
import csv
import math
from pathlib import Path
from typing import Literal

try:
    from .mcp_instance import mcp
except ImportError:
    from mcp_instance import mcp

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _to_wsl_path(win_path: Path) -> str:
    p = win_path.resolve()
    return f"/mnt/{p.drive[0].lower()}{p.as_posix()[len(p.drive):]}"


def create_case_structure(case_path: Path) -> None:
    """Create OpenFOAM case directory structure."""
    (case_path / "system").mkdir(parents=True, exist_ok=True)
    (case_path / "constant").mkdir(parents=True, exist_ok=True)
    (case_path / "0").mkdir(parents=True, exist_ok=True)


def write_control_dict(system_path: Path) -> None:
    """Write a minimal controlDict for OpenFOAM case."""
    control_dict_content = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      controlDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

application     simpleFoam;

startFrom       startTime;

startTime       0;

stopAt          endTime;

endTime         1000;

deltaT          1;

writeControl    timeStep;

writeInterval   100;

purgeWrite      0;

writeFormat     ascii;

writePrecision  6;

writeCompression off;

timeFormat      general;

timePrecision   6;

runTimeModifiable true;

// ************************************************************************* //
"""
    with open(system_path / "controlDict", 'w') as f:
        f.write(control_dict_content)


def write_fv_schemes(system_path: Path) -> None:
    """Write a minimal fvSchemes for OpenFOAM case."""
    fv_schemes_content = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSchemes;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

ddtSchemes
{
    default         steadyState;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         none;
}

laplacianSchemes
{
    default         Gauss linear corrected;
}

interpolationSchemes
{
    default         linear;
}

snGradSchemes
{
    default         corrected;
}

// ************************************************************************* //
"""
    with open(system_path / "fvSchemes", 'w') as f:
        f.write(fv_schemes_content)


def write_fv_solution(system_path: Path) -> None:
    """Write a minimal fvSolution for OpenFOAM case."""
    fv_solution_content = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      fvSolution;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

solvers
{
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;
}

relaxationFactors
{
    fields
    {
    }
    equations
    {
    }
}

// ************************************************************************* //
"""
    with open(system_path / "fvSolution", 'w') as f:
        f.write(fv_solution_content)


def read_nozzle_profile(geometry_name: str) -> list[tuple[float, float]]:
    """Read nozzle profile CSV from cases/geometry/.

    Args:
        geometry_name: Name pattern to search for (e.g., "nozzle_rt")

    Returns:
        List of (x, radius) tuples
    """
    geometry_dir = Path("cases/geometry")

    # Find matching CSV file
    csv_files = list(geometry_dir.glob(f"{geometry_name}*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No nozzle profile CSV found matching '{geometry_name}' in {geometry_dir}")

    # Use the first matching file
    csv_path = csv_files[0]

    coords = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            x = float(row['x'])
            y = float(row['y'])
            coords.append((x, y))

    return coords


def read_airfoil_profile(geometry_name: str) -> list[tuple[float, float]]:
    """Read airfoil profile CSV from cases/geometry/.

    Args:
        geometry_name: Name pattern to search for (e.g., "naca_0012")

    Returns:
        List of (x, y) tuples tracing the full airfoil surface
    """
    geometry_dir = Path("cases/geometry")

    # Find matching CSV file
    csv_files = list(geometry_dir.glob(f"{geometry_name}*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No airfoil profile CSV found matching '{geometry_name}' in {geometry_dir}")

    # Use the first matching file
    csv_path = csv_files[0]

    coords = []
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            x = float(row['x'])
            y = float(row['y'])
            coords.append((x, y))

    return coords


def write_airfoil_ogrid_blockmesh(system_path: Path, profile: list[tuple[float, float]],
                                   nx: int = 100, ny: int = 50, farfield_radius_factor: float = 10.0) -> None:
    """Write blockMeshDict for 2D O-grid mesh around an airfoil using 4-block topology.

    Creates a proper 4-block O-grid mesh with correct right-hand-rule vertex ordering.
    Blocks are arranged as quadrants around the airfoil: upper-front, upper-back,
    lower-back, and lower-front.

    Args:
        system_path: Path to system directory
        profile: List of (x, y) tuples defining the airfoil surface
                 (counterclockwise from TE: upper surface TE->LE, lower surface LE->TE)
        nx: Number of cells around airfoil (tangential direction per block)
        ny: Number of cells from airfoil to far-field (radial direction)
        farfield_radius_factor: Far-field radius as multiple of chord length
    """
    import math

    x_coords = [x for x, y in profile]
    y_coords = [y for x, y in profile]

    x_min = min(x_coords)
    x_max = max(x_coords)
    chord = x_max - x_min

    le_idx = x_coords.index(x_min)
    te_start_idx = 0  # Profile starts at TE (upper surface)

    upper_surface = profile[te_start_idx:le_idx+1]
    lower_surface = profile[le_idx:]

    mid_chord_x = x_min + chord * 0.5
    upper_mid_idx = min(range(len(upper_surface)),
                       key=lambda i: abs(upper_surface[i][0] - mid_chord_x))
    lower_mid_idx = min(range(len(lower_surface)),
                       key=lambda i: abs(lower_surface[i][0] - mid_chord_x))

    te_x, te_y = profile[te_start_idx]
    mid_upper_x, mid_upper_y = upper_surface[upper_mid_idx]
    le_x, le_y = profile[le_idx]
    mid_lower_x, mid_lower_y = lower_surface[lower_mid_idx]

    x_center = x_min + chord * 0.5
    y_center = sum(y_coords) / len(y_coords)
    r_farfield = chord * farfield_radius_factor

    z_back = -0.005
    z_front = 0.005

    ff_east_x = x_center + r_farfield
    ff_east_y = y_center
    ff_north_x = x_center
    ff_north_y = y_center + r_farfield
    ff_west_x = x_center - r_farfield
    ff_west_y = y_center
    ff_south_x = x_center
    ff_south_y = y_center - r_farfield

    # Vertex list: 16 total (8 on back plane, 8 on front plane)
    # Back plane (z = z_back): 0-7
    # Front plane (z = z_front): 8-15
    #
    # Airfoil vertices: 0=TE, 1=mid-upper, 2=LE, 3=mid-lower (back)
    #                   8=TE, 9=mid-upper, 10=LE, 11=mid-lower (front)
    # Far-field vertices: 4=East, 5=North, 6=West, 7=South (back)
    #                     12=East, 13=North, 14=West, 15=South (front)

    vertices_str = f"""(
    // Back face (z = {z_back})
    ({te_x:.6f} {te_y:.6f} {z_back:.6f})           // 0: TE
    ({mid_upper_x:.6f} {mid_upper_y:.6f} {z_back:.6f})  // 1: mid-upper
    ({le_x:.6f} {le_y:.6f} {z_back:.6f})           // 2: LE
    ({mid_lower_x:.6f} {mid_lower_y:.6f} {z_back:.6f})  // 3: mid-lower
    ({ff_east_x:.6f} {ff_east_y:.6f} {z_back:.6f})   // 4: FF East
    ({ff_north_x:.6f} {ff_north_y:.6f} {z_back:.6f}) // 5: FF North
    ({ff_west_x:.6f} {ff_west_y:.6f} {z_back:.6f})   // 6: FF West
    ({ff_south_x:.6f} {ff_south_y:.6f} {z_back:.6f}) // 7: FF South

    // Front face (z = {z_front})
    ({te_x:.6f} {te_y:.6f} {z_front:.6f})           // 8: TE
    ({mid_upper_x:.6f} {mid_upper_y:.6f} {z_front:.6f})  // 9: mid-upper
    ({le_x:.6f} {le_y:.6f} {z_front:.6f})           // 10: LE
    ({mid_lower_x:.6f} {mid_lower_y:.6f} {z_front:.6f})  // 11: mid-lower
    ({ff_east_x:.6f} {ff_east_y:.6f} {z_front:.6f})   // 12: FF East
    ({ff_north_x:.6f} {ff_north_y:.6f} {z_front:.6f}) // 13: FF North
    ({ff_west_x:.6f} {ff_west_y:.6f} {z_front:.6f})   // 14: FF West
    ({ff_south_x:.6f} {ff_south_y:.6f} {z_front:.6f}) // 15: FF South
)"""

    # Define 4 blocks with correct vertex ordering (right-hand rule)
    # Each block: (v0 v1 v2 v3 v4 v5 v6 v7) where 0-3 are back face, 4-7 are front face
    # The quad 0-1-2-3 should be ordered counterclockwise when viewed from front

    # Block 0: upper-front quadrant (TE to mid-upper on airfoil, East to North on far-field)
    # Block 1: upper-back quadrant (mid-upper to LE on airfoil, North to West on far-field)
    # Block 2: lower-back quadrant (LE to mid-lower on airfoil, West to South on far-field)
    # Block 3: lower-front quadrant (mid-lower to TE on airfoil, South to East on far-field)

    radial_grading = 10  # Finer near airfoil, coarser at far-field
    tangential_grading = 1  # Uniform tangentially

    blocks_str = f"""(
    // Block 0: upper-front (TE to mid-upper, East to North)
    hex (0 4 5 1 8 12 13 9) ({nx//4} {ny} 1) simpleGrading ({tangential_grading} {radial_grading} 1)

    // Block 1: upper-back (mid-upper to LE, North to West)
    hex (1 5 6 2 9 13 14 10) ({nx//4} {ny} 1) simpleGrading ({tangential_grading} {radial_grading} 1)

    // Block 2: lower-back (LE to mid-lower, West to South)
    hex (2 6 7 3 10 14 15 11) ({nx//4} {ny} 1) simpleGrading ({tangential_grading} {radial_grading} 1)

    // Block 3: lower-front (mid-lower to TE, South to East)
    hex (3 7 4 0 11 15 12 8) ({nx//4} {ny} 1) simpleGrading ({tangential_grading} {radial_grading} 1)
)"""

    seg1_start = te_start_idx
    seg1_end = te_start_idx + upper_mid_idx
    seg1_points_back = [f"        ({x:.6f} {y:.6f} {z_back:.6f})"
                        for x, y in upper_surface[1:upper_mid_idx]]
    seg1_points_front = [f"        ({x:.6f} {y:.6f} {z_front:.6f})"
                         for x, y in upper_surface[1:upper_mid_idx]]

    # Segment 2: mid-upper to LE (back: 1->2, front: 9->10)
    seg2_points_back = [f"        ({x:.6f} {y:.6f} {z_back:.6f})"
                        for x, y in upper_surface[upper_mid_idx+1:len(upper_surface)-1]]
    seg2_points_front = [f"        ({x:.6f} {y:.6f} {z_front:.6f})"
                         for x, y in upper_surface[upper_mid_idx+1:len(upper_surface)-1]]

    # Segment 3: LE to mid-lower (back: 2->3, front: 10->11)
    seg3_points_back = [f"        ({x:.6f} {y:.6f} {z_back:.6f})"
                        for x, y in lower_surface[1:lower_mid_idx]]
    seg3_points_front = [f"        ({x:.6f} {y:.6f} {z_front:.6f})"
                         for x, y in lower_surface[1:lower_mid_idx]]

    # Segment 4: mid-lower to TE (back: 3->0, front: 11->8)
    seg4_points_back = [f"        ({x:.6f} {y:.6f} {z_back:.6f})"
                        for x, y in lower_surface[lower_mid_idx+1:-1]]
    seg4_points_front = [f"        ({x:.6f} {y:.6f} {z_front:.6f})"
                         for x, y in lower_surface[lower_mid_idx+1:-1]]

    def point_on_circle(x_ctr, y_ctr, radius, angle_deg, z):
        angle_rad = math.radians(angle_deg)
        x = x_ctr + radius * math.cos(angle_rad)
        y = y_ctr + radius * math.sin(angle_rad)
        return f"({x:.6f} {y:.6f} {z:.6f})"

    # Far-field arc interpolation points (at 45° between cardinal directions)
    arc_ne_back = point_on_circle(x_center, y_center, r_farfield, 45, z_back)
    arc_nw_back = point_on_circle(x_center, y_center, r_farfield, 135, z_back)
    arc_sw_back = point_on_circle(x_center, y_center, r_farfield, 225, z_back)
    arc_se_back = point_on_circle(x_center, y_center, r_farfield, 315, z_back)

    arc_ne_front = point_on_circle(x_center, y_center, r_farfield, 45, z_front)
    arc_nw_front = point_on_circle(x_center, y_center, r_farfield, 135, z_front)
    arc_sw_front = point_on_circle(x_center, y_center, r_farfield, 225, z_front)
    arc_se_front = point_on_circle(x_center, y_center, r_farfield, 315, z_front)

    edges_parts = ["("]

    # Airfoil splines (8 total: 4 on back, 4 on front)
    if seg1_points_back:
        edges_parts.append(f"    spline 0 1\n    (\n" + "\n".join(seg1_points_back) + "\n    )")
    if seg1_points_front:
        edges_parts.append(f"    spline 8 9\n    (\n" + "\n".join(seg1_points_front) + "\n    )")

    if seg2_points_back:
        edges_parts.append(f"    spline 1 2\n    (\n" + "\n".join(seg2_points_back) + "\n    )")
    if seg2_points_front:
        edges_parts.append(f"    spline 9 10\n    (\n" + "\n".join(seg2_points_front) + "\n    )")

    if seg3_points_back:
        edges_parts.append(f"    spline 2 3\n    (\n" + "\n".join(seg3_points_back) + "\n    )")
    if seg3_points_front:
        edges_parts.append(f"    spline 10 11\n    (\n" + "\n".join(seg3_points_front) + "\n    )")

    if seg4_points_back:
        edges_parts.append(f"    spline 3 0\n    (\n" + "\n".join(seg4_points_back) + "\n    )")
    if seg4_points_front:
        edges_parts.append(f"    spline 11 8\n    (\n" + "\n".join(seg4_points_front) + "\n    )")

    # Far-field arcs (8 total: 4 on back, 4 on front)
    edges_parts.extend([
        f"    arc 4 5 {arc_ne_back}  // East to North (back)",
        f"    arc 5 6 {arc_nw_back}  // North to West (back)",
        f"    arc 6 7 {arc_sw_back}  // West to South (back)",
        f"    arc 7 4 {arc_se_back}  // South to East (back)",
        f"    arc 12 13 {arc_ne_front}  // East to North (front)",
        f"    arc 13 14 {arc_nw_front}  // North to West (front)",
        f"    arc 14 15 {arc_sw_front}  // West to South (front)",
        f"    arc 15 12 {arc_se_front}  // South to East (front)",
    ])
    edges_parts.append(")")
    edges_str = "\n".join(edges_parts)

    boundary_str = """(
    airfoil
    {
        type wall;
        faces
        (
            (0 8 9 1)   // TE to mid-upper
            (1 9 10 2)  // mid-upper to LE
            (2 10 11 3) // LE to mid-lower
            (3 11 8 0)  // mid-lower to TE
        );
    }
    farfield
    {
        type patch;
        faces
        (
            (4 5 13 12)  // East to North
            (5 6 14 13)  // North to West
            (6 7 15 14)  // West to South
            (7 4 12 15)  // South to East
        );
    }
    front
    {
        type empty;
        faces
        (
            (8 9 13 12)   // Block 0 front
            (9 10 14 13)  // Block 1 front
            (10 11 15 14) // Block 2 front
            (11 8 12 15)  // Block 3 front
        );
    }
    back
    {
        type empty;
        faces
        (
            (0 1 5 4)   // Block 0 back
            (1 2 6 5)   // Block 1 back
            (2 3 7 6)   // Block 2 back
            (3 0 4 7)   // Block 3 back
        );
    }
)"""

    blockmesh_content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

scale 1;

vertices
{vertices_str};

blocks
{blocks_str};

edges
{edges_str};

boundary
{boundary_str};

mergePatchPairs
(
);

// ************************************************************************* //
"""

    with open(system_path / "blockMeshDict", 'w') as f:
        f.write(blockmesh_content)


def write_nozzle_wedge_blockmesh(system_path: Path, profile: list[tuple[float, float]],
                                  nx: int = 50, nr: int = 30) -> None:
    """Write blockMeshDict for axisymmetric nozzle wedge mesh.

    Creates a 2.5-degree wedge mesh with the nozzle profile as a spline edge.

    Args:
        system_path: Path to system directory
        profile: List of (x, radius) tuples defining the nozzle wall
        nx: Number of cells in axial direction
        nr: Number of cells in radial direction
    """
    x_min = profile[0][0]
    x_max = profile[-1][0]
    r_max = max(r for _, r in profile)

    # Core radius: small non-zero value to avoid axis singularity
    # Use 0.5% of minimum wall radius, or 0.0001m minimum
    r_min_wall = min(r for _, r in profile)
    r_core = max(0.0001, 0.005 * r_min_wall)

    # Wedge angle (2.5 degrees half-angle)
    wedge_angle = 2.5
    wedge_rad = math.radians(wedge_angle)

    # Define vertices for the wedge
    # Front wedge (z > 0), Back wedge (z < 0)
    # Vertex ordering: core_inlet, outlet, wall_outlet, wall_inlet for each wedge face

    # Calculate z-coordinates for wedge faces
    # For front face: y_front = r * cos(wedge_rad), z_front = r * sin(wedge_rad)
    # For back face: y_back = r * cos(wedge_rad), z_back = -r * sin(wedge_rad)

    r_inlet = profile[0][1]
    r_outlet = profile[-1][1]

    # Vertices (8 total for a single block wedge)
    # Back wedge face (negative z)
    v0 = f"({x_min:.6f} {r_core * math.cos(wedge_rad):.6f} {-r_core * math.sin(wedge_rad):.6f})"  # core inlet back
    v1 = f"({x_max:.6f} {r_core * math.cos(wedge_rad):.6f} {-r_core * math.sin(wedge_rad):.6f})"  # core outlet back
    v2 = f"({x_max:.6f} {r_outlet * math.cos(wedge_rad):.6f} {-r_outlet * math.sin(wedge_rad):.6f})"  # wall outlet back
    v3 = f"({x_min:.6f} {r_inlet * math.cos(wedge_rad):.6f} {-r_inlet * math.sin(wedge_rad):.6f})"  # wall inlet back

    # Front wedge face (positive z)
    v4 = f"({x_min:.6f} {r_core * math.cos(wedge_rad):.6f} {r_core * math.sin(wedge_rad):.6f})"  # core inlet front
    v5 = f"({x_max:.6f} {r_core * math.cos(wedge_rad):.6f} {r_core * math.sin(wedge_rad):.6f})"  # core outlet front
    v6 = f"({x_max:.6f} {r_outlet * math.cos(wedge_rad):.6f} {r_outlet * math.sin(wedge_rad):.6f})"  # wall outlet front
    v7 = f"({x_min:.6f} {r_inlet * math.cos(wedge_rad):.6f} {r_inlet * math.sin(wedge_rad):.6f})"  # wall inlet front

    spline_points_back = []
    spline_points_front_list = []

    for x, r in profile[1:-1]:  # Skip endpoints
        # Back wedge (negative z)
        spline_points_back.append(f"        ({x:.6f} {r * math.cos(wedge_rad):.6f} {-r * math.sin(wedge_rad):.6f})")
        # Front wedge (positive z)
        spline_points_front_list.append(f"        ({x:.6f} {r * math.cos(wedge_rad):.6f} {r * math.sin(wedge_rad):.6f})")

    spline_points = "\n".join(spline_points_back)
    spline_points_front = "\n".join(spline_points_front_list)

    # Grading: uniform for now to avoid degenerate cells at axis
    # SimpleGrading format: (x_grading y_grading z_grading)
    # In wedge meshes, cells at r=0 (axis) must not collapse to zero width
    # radial_grading > 1 would make cells finer near axis (vertices 0,1,4,5) - causes degeneracy
    # radial_grading < 1 would make cells finer near wall (vertices 2,3,6,7)
    axial_grading = 1  # uniform in x
    radial_grading = 1  # uniform in r - avoids axis degeneracy

    blockmesh_content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

convertToMeters 1;

vertices
(
    {v0}  // 0: axis inlet
    {v1}  // 1: axis outlet
    {v2}  // 2: wall outlet back
    {v3}  // 3: wall inlet back
    {v4}  // 4: axis inlet front
    {v5}  // 5: axis outlet front
    {v6}  // 6: wall outlet front
    {v7}  // 7: wall inlet front
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {nr} 1) simpleGrading ({axial_grading} {radial_grading} 1)
);

edges
(
    // Nozzle wall spline on back wedge face (edge 3-2)
    // Uses intermediate profile points to capture true converging-diverging shape
    spline 3 2
    (
{spline_points}
    )
    // Nozzle wall spline on front wedge face (edge 7-6)
    spline 7 6
    (
{spline_points_front}
    )
);

boundary
(
    inlet
    {{
        type patch;
        faces
        (
            (0 4 7 3)
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
            (1 2 6 5)
        );
    }}
    wall
    {{
        type wall;
        faces
        (
            (3 7 6 2)
        );
    }}
    wedge_back
    {{
        type wedge;
        faces
        (
            (0 1 2 3)
        );
    }}
    wedge_front
    {{
        type wedge;
        faces
        (
            (4 5 6 7)
        );
    }}
    centerline
    {{
        type symmetry;
        faces
        (
            (0 1 5 4)
        );
    }}
);

mergePatchPairs
(
);

// ************************************************************************* //
"""
    with open(system_path / "blockMeshDict", 'w') as f:
        f.write(blockmesh_content)


def write_blockmesh_dict(system_path: Path) -> None:
    """Write a minimal blockMeshDict for a simple rectangular domain."""
    blockmesh_content = """/*--------------------------------*- C++ -*----------------------------------*\\
| =========                 |                                                 |
| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |
|  \\\\    /   O peration     | Version:  v2312                                 |
|   \\\\  /    A nd           | Website:  www.openfoam.com                      |
|    \\\\/     M anipulation  |                                                 |
\\*---------------------------------------------------------------------------*/
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

convertToMeters 1;

vertices
(
    (0 0 0)
    (1 0 0)
    (1 1 0)
    (0 1 0)
    (0 0 0.1)
    (1 0 0.1)
    (1 1 0.1)
    (0 1 0.1)
);

blocks
(
    hex (0 1 2 3 4 5 6 7) (20 20 1) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    inlet
    {
        type patch;
        faces
        (
            (0 4 7 3)
        );
    }
    outlet
    {
        type patch;
        faces
        (
            (1 2 6 5)
        );
    }
    walls
    {
        type wall;
        faces
        (
            (0 1 5 4)
            (3 7 6 2)
        );
    }
    frontAndBack
    {
        type empty;
        faces
        (
            (0 3 2 1)
            (4 5 6 7)
        );
    }
);

mergePatchPairs
(
);

// ************************************************************************* //
"""
    with open(system_path / "blockMeshDict", 'w') as f:
        f.write(blockmesh_content)


def run_blockmesh_wsl(case_name: str) -> tuple[int, str, str]:
    """Run blockMesh via WSL.

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    wsl_path = _to_wsl_path(PROJECT_ROOT)
    cmd = [
        "wsl",
        "bash",
        "-c",
        f'source /usr/lib/openfoam/openfoam2406/etc/bashrc && cd {wsl_path} && blockMesh -case cases/{case_name}'
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60
    )

    return result.returncode, result.stdout, result.stderr


def parse_cell_count(stdout: str) -> int | None:
    """Extract cell count from blockMesh output."""
    for line in stdout.split('\n'):
        if 'cells:' in line.lower():
            parts = line.split(':')
            if len(parts) >= 2:
                try:
                    return int(parts[1].strip().split()[0])
                except (ValueError, IndexError):
                    pass
    return None


@mcp.tool()
def generate_mesh(
    case_name: str,
    mesh_type: Literal["blockMesh", "snappyHexMesh", "nozzle_wedge", "airfoil_ogrid"] = "blockMesh",
    geometry_name: str = ""
) -> str:
    """Generate CFD mesh for an OpenFOAM case using blockMesh or snappyHexMesh.

    Creates OpenFOAM case structure and generates mesh. Supports:
    - blockMesh: basic rectangular domains
    - nozzle_wedge: axisymmetric nozzle flows
    - airfoil_ogrid: 2D external flow around airfoils with O-grid topology
    Runs OpenFOAM commands via WSL on Windows.

    Args:
        case_name: Name of the case (creates cases/<case_name>/ directory)
        mesh_type: Type of meshing tool ("blockMesh", "snappyHexMesh", "nozzle_wedge", or "airfoil_ogrid")
        geometry_name: For nozzle_wedge or airfoil_ogrid, the geometry file prefix to search for
                      (e.g., "naca_0012" to match naca_0012_c1.000m.csv)
                      If empty, uses case_name as the search pattern

    Returns:
        Summary string with mesh generation status and cell count or error details
    """
    case_path = Path("cases") / case_name
    try:
        create_case_structure(case_path)
    except Exception as e:
        return f"Error creating case structure: {e}"

    system_path = case_path / "system"
    try:
        write_control_dict(system_path)
        write_fv_schemes(system_path)
        write_fv_solution(system_path)

        if mesh_type == "nozzle_wedge":
            search_pattern = geometry_name if geometry_name else case_name
            try:
                profile = read_nozzle_profile(search_pattern)
            except FileNotFoundError as e:
                return f"Error: {e}"
            except Exception as e:
                return f"Error reading nozzle profile: {e}"

            write_nozzle_wedge_blockmesh(system_path, profile, nx=50, nr=30)

        elif mesh_type == "airfoil_ogrid":
            search_pattern = geometry_name if geometry_name else case_name
            try:
                profile = read_airfoil_profile(search_pattern)
            except FileNotFoundError as e:
                return f"Error: {e}"
            except Exception as e:
                return f"Error reading airfoil profile: {e}"

            write_airfoil_ogrid_blockmesh(system_path, profile, nx=100, ny=50, farfield_radius_factor=10.0)

        else:
            write_blockmesh_dict(system_path)

    except Exception as e:
        return f"Error writing configuration files: {e}"

    try:
        returncode, stdout, stderr = run_blockmesh_wsl(case_name)
    except subprocess.TimeoutExpired:
        return f"Error: blockMesh command timed out after 60 seconds"
    except Exception as e:
        return f"Error running blockMesh: {e}"

    if returncode == 0:
        cell_count = parse_cell_count(stdout)
        if cell_count:
            summary = f"Mesh generated successfully!\nMesh type: {mesh_type}\nCells: {cell_count}\nCase: cases/{case_name}/"
        else:
            summary = f"Mesh generated successfully!\nMesh type: {mesh_type}\nCase: cases/{case_name}/"

        if "Writing polyMesh" in stdout:
            summary += "\n\nblockMesh completed - polyMesh written to constant/polyMesh/"

        return summary
    else:
        error_msg = f"blockMesh failed with return code {returncode}\n\n"

        if stderr:
            error_msg += f"Error output:\n{stderr}\n"

        if stdout:
            error_msg += f"\nStandard output:\n{stdout}"

        return error_msg
