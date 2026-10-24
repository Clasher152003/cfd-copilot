from pathlib import Path
from typing import Literal, Optional

try:
    from .mcp_instance import mcp
except ImportError:
    from mcp_instance import mcp


def write_controldict_simplefoam(system_path: Path, include_force_coeffs: bool = False,
                                  chord_length: float = 1.0, freestream_velocity: float = 20.0,
                                  angle_of_attack: float = 0.0) -> None:
    """Write controlDict for simpleFoam with residual-based stopping.

    Args:
        system_path: Path to system directory
        include_force_coeffs: If True, add forceCoeffs function object for aerodynamic forces
        chord_length: Reference chord length for force coefficients (meters)
        freestream_velocity: Freestream velocity magnitude (m/s)
        angle_of_attack: Angle of attack in degrees
    """
    import math

    functions_block = """    residuals
    {
        type            residuals;
        libs            (utilityFunctionObjects);
        writeControl    timeStep;
        writeInterval   1;
        fields          (U p);
    }"""

    if include_force_coeffs:
        aoa_rad = math.radians(angle_of_attack)
        drag_x = math.cos(aoa_rad)
        drag_y = math.sin(aoa_rad)
        lift_x = -math.sin(aoa_rad)
        lift_y = math.cos(aoa_rad)

        # Reference area for 2D case (chord × actual mesh z-depth)
        # The airfoil_ogrid mesh has z from -0.005 to 0.005 (depth = 0.01m)
        mesh_z_depth = 0.01
        aref = chord_length * mesh_z_depth

        # Reference point at quarter-chord
        cofr_x = 0.25 * chord_length

        functions_block += f"""

    forceCoeffs1
    {{
        type            forceCoeffs;
        libs            (forces);

        patches         (airfoil);

        pName           p;
        UName           U;
        rho             rhoInf;
        rhoInf          1.225;  // Air density at sea level (kg/m³)

        liftDir         ({lift_x:.6f} {lift_y:.6f} 0);
        dragDir         ({drag_x:.6f} {drag_y:.6f} 0);
        CofR            ({cofr_x:.6f} 0 0);  // Quarter-chord reference point
        pitchAxis       (0 0 1);

        magUInf         {freestream_velocity};
        lRef            {chord_length};  // Chord length
        Aref            {aref};          // Reference area (chord × span)

        writeControl    timeStep;
        writeInterval   1;
    }}"""

    content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    object      controlDict;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

application     simpleFoam;

startFrom       startTime;

startTime       0;

stopAt          endTime;

endTime         500;

deltaT          1;

writeControl    timeStep;

writeInterval   100;

purgeWrite      2;

writeFormat     ascii;

writePrecision  6;

writeCompression off;

timeFormat      general;

timePrecision   6;

runTimeModifiable true;

// Residual control for convergence
functions
{{
{functions_block}
}}

// ************************************************************************* //
"""
    with open(system_path / "controlDict", 'w') as f:
        f.write(content)


def write_fvschemes_simplefoam(system_path: Path) -> None:
    """Write fvSchemes with proper discretization schemes for steady RANS."""
    content = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    grad(p)         Gauss linear;
    grad(U)         Gauss linear;
}

divSchemes
{
    default         none;
    div(phi,U)      Gauss linearUpwind grad(U);
    div(phi,k)      Gauss upwind;
    div(phi,epsilon) Gauss upwind;
    div(phi,omega)  Gauss upwind;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
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

wallDist
{
    method          meshWave;
}

// ************************************************************************* //
"""
    with open(system_path / "fvSchemes", 'w') as f:
        f.write(content)


def write_fvsolution_simplefoam(system_path: Path) -> None:
    """Write fvSolution with SIMPLE algorithm and proper solvers."""
    content = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    p
    {
        solver          GAMG;
        tolerance       1e-06;
        relTol          0.1;
        smoother        GaussSeidel;
        nPreSweeps      0;
        nPostSweeps     2;
        cacheAgglomeration true;
        nCellsInCoarsestLevel 10;
        agglomerator    faceAreaPair;
        mergeLevels     1;
    }

    U
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-07;
        relTol          0.1;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;
    consistent      yes;

    residualControl
    {
        p               1e-4;
        U               1e-4;
    }
}

relaxationFactors
{
    fields
    {
        p               0.3;
    }
    equations
    {
        U               0.7;
    }
}

// ************************************************************************* //
"""
    with open(system_path / "fvSolution", 'w') as f:
        f.write(content)


def write_velocity_field(zero_path: Path, inlet_velocity: float, flow_type: str,
                         freestream_velocity: float = None, angle_of_attack: float = 0.0) -> None:
    """Write 0/U file with velocity boundary conditions.

    Args:
        zero_path: Path to 0 directory
        inlet_velocity: Velocity for internal flow (m/s)
        flow_type: "internal" or "external"
        freestream_velocity: Freestream velocity for external flow (m/s)
        angle_of_attack: Angle of attack for external flow (degrees)
    """
    import math

    if flow_type == "internal":
        bc_content = f"""    inlet
    {{
        type            fixedValue;
        value           uniform ({inlet_velocity} 0 0);
    }}
    outlet
    {{
        type            zeroGradient;
    }}
    walls
    {{
        type            noSlip;
    }}
    frontAndBack
    {{
        type            empty;
    }}"""
        internal_field_value = f"{inlet_velocity} 0 0"

    elif flow_type == "external":
        aoa_rad = math.radians(angle_of_attack)
        u_x = freestream_velocity * math.cos(aoa_rad)
        u_y = freestream_velocity * math.sin(aoa_rad)

        bc_content = f"""    farfield
    {{
        type            freestreamVelocity;
        freestreamValue uniform ({u_x} {u_y} 0);
    }}
    airfoil
    {{
        type            noSlip;
    }}
    front
    {{
        type            empty;
    }}
    back
    {{
        type            empty;
    }}"""
        internal_field_value = f"{u_x} {u_y} 0"

    else:
        # Fallback for unknown flow types
        bc_content = f"""    farfield
    {{
        type            fixedValue;
        value           uniform ({inlet_velocity} 0 0);
    }}
    airfoil
    {{
        type            noSlip;
    }}
    frontAndBack
    {{
        type            empty;
    }}"""
        internal_field_value = f"{inlet_velocity} 0 0"

    content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       volVectorField;
    object      U;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 1 -1 0 0 0 0];

internalField   uniform ({internal_field_value});

boundaryField
{{
{bc_content}
}}

// ************************************************************************* //
"""
    with open(zero_path / "U", 'w') as f:
        f.write(content)


def write_pressure_field(zero_path: Path, outlet_pressure: float, flow_type: str,
                        freestream_pressure: float = None) -> None:
    """Write 0/p file with pressure boundary conditions.

    Args:
        zero_path: Path to 0 directory
        outlet_pressure: Pressure for internal flow (Pa)
        flow_type: "internal" or "external"
        freestream_pressure: Freestream pressure for external flow (Pa)
    """
    if flow_type == "internal":
        bc_content = f"""    inlet
    {{
        type            zeroGradient;
    }}
    outlet
    {{
        type            fixedValue;
        value           uniform {outlet_pressure};
    }}
    walls
    {{
        type            zeroGradient;
    }}
    frontAndBack
    {{
        type            empty;
    }}"""
        internal_field_value = outlet_pressure

    elif flow_type == "external":
        # Use freestream pressure if provided, otherwise use outlet_pressure
        p_freestream = freestream_pressure if freestream_pressure is not None else outlet_pressure

        bc_content = f"""    farfield
    {{
        type            freestreamPressure;
        freestreamValue uniform {p_freestream};
    }}
    airfoil
    {{
        type            zeroGradient;
    }}
    front
    {{
        type            empty;
    }}
    back
    {{
        type            empty;
    }}"""
        internal_field_value = p_freestream

    else:
        # Fallback for unknown flow types
        bc_content = f"""    farfield
    {{
        type            fixedValue;
        value           uniform {outlet_pressure};
    }}
    airfoil
    {{
        type            zeroGradient;
    }}
    frontAndBack
    {{
        type            empty;
    }}"""
        internal_field_value = outlet_pressure

    content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       volScalarField;
    object      p;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 2 -2 0 0 0 0];

internalField   uniform {internal_field_value};

boundaryField
{{
{bc_content}
}}

// ************************************************************************* //
"""
    with open(zero_path / "p", 'w') as f:
        f.write(content)


def write_turbulence_properties(constant_path: Path) -> None:
    """Write constant/turbulenceProperties for laminar flow."""
    content = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    object      turbulenceProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

simulationType  laminar;

// ************************************************************************* //
"""
    with open(constant_path / "turbulenceProperties", 'w') as f:
        f.write(content)


def write_transport_properties(constant_path: Path) -> None:
    """Write constant/transportProperties for incompressible flow."""
    content = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    object      transportProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

transportModel  Newtonian;

// Kinematic viscosity (air at 20°C: 1.5e-5 m²/s)
nu              [0 2 -1 0 0 0 0] 1.5e-05;

// ************************************************************************* //
"""
    with open(constant_path / "transportProperties", 'w') as f:
        f.write(content)


def write_controldict_rhocentralfoam(system_path: Path) -> None:
    """Write controlDict for rhoCentralFoam (transient density-based solver for supersonic flow)."""
    content = """/*--------------------------------*- C++ -*----------------------------------*\\
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

application     rhoCentralFoam;

startFrom       startTime;

startTime       0;

stopAt          endTime;

endTime         0.01;

deltaT          1e-7;

writeControl    adjustableRunTime;

writeInterval   0.001;

purgeWrite      2;

writeFormat     ascii;

writePrecision  6;

writeCompression off;

timeFormat      general;

timePrecision   6;

runTimeModifiable true;

adjustTimeStep  yes;

maxCo           0.5;

maxDeltaT       1e-5;

// ************************************************************************* //
"""
    with open(system_path / "controlDict", 'w') as f:
        f.write(content)


def write_fvschemes_rhocentralfoam(system_path: Path) -> None:
    """Write fvSchemes for rhoCentralFoam with Kurganov flux scheme."""
    content = """/*--------------------------------*- C++ -*----------------------------------*\\
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

fluxScheme      Kurganov;

ddtSchemes
{
    default         Euler;
}

gradSchemes
{
    default         Gauss linear;
}

divSchemes
{
    default         none;
    div(tauMC)      Gauss linear;
}

laplacianSchemes
{
    default         Gauss linear corrected;
}

interpolationSchemes
{
    default         linear;
    reconstruct(rho)   vanLeer;
    reconstruct(U)     vanLeerV;
    reconstruct(T)     vanLeer;
}

snGradSchemes
{
    default         corrected;
}

// ************************************************************************* //
"""
    with open(system_path / "fvSchemes", 'w') as f:
        f.write(content)


def write_fvsolution_rhocentralfoam(system_path: Path) -> None:
    """Write fvSolution for rhoCentralFoam (no SIMPLE, just linear solvers)."""
    content = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    "(rho|rhoU|rhoE)"
    {
        solver          diagonal;
    }

    "(U|e|h)"
    {
        solver          smoothSolver;
        smoother        GaussSeidel;
        nSweeps         2;
        tolerance       1e-09;
        relTol          0.01;
    }
}

// ************************************************************************* //
"""
    with open(system_path / "fvSolution", 'w') as f:
        f.write(content)


def write_controldict_rhosimplefoam(system_path: Path) -> None:
    """Write controlDict for rhoSimpleFoam with residual-based stopping."""
    content = """/*--------------------------------*- C++ -*----------------------------------*\\
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

application     rhoSimpleFoam;

startFrom       startTime;

startTime       0;

stopAt          endTime;

endTime         1000;

deltaT          1;

writeControl    timeStep;

writeInterval   100;

purgeWrite      2;

writeFormat     ascii;

writePrecision  6;

writeCompression off;

timeFormat      general;

timePrecision   6;

runTimeModifiable true;

// Residual control for convergence
functions
{
    residuals
    {
        type            residuals;
        libs            (utilityFunctionObjects);
        writeControl    timeStep;
        writeInterval   1;
        fields          (U p T);
    }
}

// ************************************************************************* //
"""
    with open(system_path / "controlDict", 'w') as f:
        f.write(content)


def write_fvschemes_rhosimplefoam(system_path: Path) -> None:
    """Write fvSchemes with bounded schemes for compressible flow."""
    content = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    div(phi,U)      bounded Gauss upwind;
    div(phi,e)      bounded Gauss upwind;
    div(phi,h)      bounded Gauss upwind;
    div(phi,K)      bounded Gauss upwind;
    div(phi,k)      bounded Gauss upwind;
    div(phi,epsilon) bounded Gauss upwind;
    div(phi,omega)  bounded Gauss upwind;
    div(phid,p)     bounded Gauss upwind;
    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;
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

wallDist
{
    method          meshWave;
}

// ************************************************************************* //
"""
    with open(system_path / "fvSchemes", 'w') as f:
        f.write(content)


def write_fvsolution_rhosimplefoam(system_path: Path) -> None:
    """Write fvSolution with SIMPLE algorithm for compressible flow."""
    content = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    p
    {
        solver          GAMG;
        tolerance       1e-06;
        relTol          0.1;
        smoother        GaussSeidel;
        nPreSweeps      0;
        nPostSweeps     2;
        cacheAgglomeration true;
        nCellsInCoarsestLevel 10;
        agglomerator    faceAreaPair;
        mergeLevels     1;
    }

    U
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-07;
        relTol          0.1;
    }

    "(e|h)"
    {
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-07;
        relTol          0.1;
    }
}

SIMPLE
{
    nNonOrthogonalCorrectors 0;
    consistent      yes;

    // Pressure limiters to prevent thermodynamic state violations
    pMin            10000;      // Minimum pressure (10 kPa)
    pMax            1000000;    // Maximum pressure (1 MPa)

    residualControl
    {
        p               1e-4;
        U               1e-4;
        "(e|h)"         1e-4;
    }
}

relaxationFactors
{
    fields
    {
        p               0.3;
        rho             0.05;
    }
    equations
    {
        // Very conservative relaxation to prevent thermodynamic coupling instability
        // Match enthalpy to pressure (both 0.3) since they're tightly coupled via T = T(h,p)
        U               0.3;
        "(e|h)"         0.3;
    }
}

// ************************************************************************* //
"""
    with open(system_path / "fvSolution", 'w') as f:
        f.write(content)


def write_thermophysical_properties(constant_path: Path) -> None:
    """Write constant/thermophysicalProperties for air as perfect gas."""
    content = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    object      thermophysicalProperties;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

thermoType
{
    type            hePsiThermo;
    mixture         pureMixture;
    transport       sutherland;
    thermo          hConst;
    equationOfState perfectGas;
    specie          specie;
    energy          sensibleEnthalpy;
}

mixture
{
    specie
    {
        molWeight       28.96;  // Air molecular weight
    }
    thermodynamics
    {
        Cp              1005;   // Specific heat at constant pressure (J/kg/K)
        Hf              0;      // Heat of formation
    }
    transport
    {
        // Sutherland's law for air
        As              1.458e-06;
        Ts              110.4;
    }
}

// ************************************************************************* //
"""
    with open(constant_path / "thermophysicalProperties", 'w') as f:
        f.write(content)


def write_velocity_field_compressible(zero_path: Path) -> None:
    """Write 0/U file for compressible nozzle flow.

    Initialize to small forward velocity (10 m/s) to:
    - Avoid divide-by-zero at inlet stagnation point
    - Minimize dynamic pressure error (½ρU² = 60 Pa << total pressure)
    - Allow smooth acceleration through nozzle
    """
    content = """/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       volVectorField;
    object      U;
}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 1 -1 0 0 0 0];

internalField   uniform (10 0 0);

boundaryField
{
    inlet
    {
        type            pressureInletOutletVelocity;
        value           uniform (0 0 0);
    }
    outlet
    {
        type            zeroGradient;
    }
    wall
    {
        type            noSlip;
    }
    wedge_back
    {
        type            wedge;
    }
    wedge_front
    {
        type            wedge;
    }
    centerline
    {
        type            symmetry;
    }
}

// ************************************************************************* //
"""
    with open(zero_path / "U", 'w') as f:
        f.write(content)


def write_pressure_field_compressible(zero_path: Path, inlet_total_pressure: float,
                                       outlet_static_pressure: float) -> None:
    """Write 0/p file with totalPressure at inlet for compressible flow.

    Initialize internal field to average pressure to balance gradients at both boundaries.
    This avoids large shocks at either inlet or outlet during startup.
    """
    # Initialize to average pressure to balance inlet and outlet gradients
    initial_pressure = (inlet_total_pressure + outlet_static_pressure) / 2.0

    content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       volScalarField;
    object      p;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [1 -1 -2 0 0 0 0];

internalField   uniform {initial_pressure};

boundaryField
{{
    inlet
    {{
        type            totalPressure;
        p0              uniform {inlet_total_pressure};
        gamma           1.4;
    }}
    outlet
    {{
        type            fixedValue;
        value           uniform {outlet_static_pressure};
    }}
    wall
    {{
        type            zeroGradient;
    }}
    wedge_back
    {{
        type            wedge;
    }}
    wedge_front
    {{
        type            wedge;
    }}
    centerline
    {{
        type            symmetry;
    }}
}}

// ************************************************************************* //
"""
    with open(zero_path / "p", 'w') as f:
        f.write(content)


def write_temperature_field_compressible(zero_path: Path, inlet_total_temperature: float) -> None:
    """Write 0/T file with totalTemperature at inlet for compressible flow.

    Initialize to 90% of inlet total temperature as a reasonable estimate
    between inlet stagnation and expected outlet static temperature.
    This reduces thermal imbalance during startup.
    """
    # Initialize to 90% of total temperature (reasonable average for subsonic/transonic flow)
    initial_temperature = inlet_total_temperature * 0.9

    content = f"""/*--------------------------------*- C++ -*----------------------------------*\\
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
    class       volScalarField;
    object      T;
}}
// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

dimensions      [0 0 0 1 0 0 0];

internalField   uniform {initial_temperature};

boundaryField
{{
    inlet
    {{
        type            totalTemperature;
        T0              uniform {inlet_total_temperature};
        gamma           1.4;
    }}
    outlet
    {{
        type            zeroGradient;
    }}
    wall
    {{
        type            zeroGradient;
    }}
    wedge_back
    {{
        type            wedge;
    }}
    wedge_front
    {{
        type            wedge;
    }}
    centerline
    {{
        type            symmetry;
    }}
}}

// ************************************************************************* //
"""
    with open(zero_path / "T", 'w') as f:
        f.write(content)


@mcp.tool()
def setup_case(
    case_name: str,
    inlet_velocity: Optional[float] = None,
    outlet_pressure: Optional[float] = None,
    flow_type: Literal["internal", "external", "nozzle_compressible", "nozzle_compressible_simple"] = "internal",
    inlet_total_pressure: Optional[float] = None,
    inlet_total_temperature: Optional[float] = None,
    outlet_static_pressure: Optional[float] = None,
    freestream_velocity: Optional[float] = None,
    angle_of_attack: float = 0.0,
    chord_length: float = 1.0
) -> str:
    """Setup OpenFOAM case with proper solver settings and initial/boundary conditions.

    Supports incompressible (simpleFoam), compressible steady (rhoSimpleFoam),
    and compressible transient (rhoCentralFoam) solvers.
    Overwrites placeholder files from generate_mesh with real solver settings.

    Args:
        case_name: Name of existing case (mesh must be already generated)
        inlet_velocity: Velocity at inlet in m/s (for incompressible "internal" flow)
        outlet_pressure: Pressure at outlet in Pa (for incompressible "internal" flow)
        flow_type: "internal" (incompressible duct), "external" (airfoil),
                   "nozzle_compressible" (supersonic nozzle with rhoCentralFoam - default for high PR),
                   "nozzle_compressible_simple" (subsonic/transonic nozzle with rhoSimpleFoam)
        inlet_total_pressure: Total (stagnation) pressure at inlet in Pa (for compressible nozzles)
        inlet_total_temperature: Total (stagnation) temperature at inlet in K (for compressible nozzles)
        outlet_static_pressure: Static pressure at outlet in Pa (for compressible nozzles)
        freestream_velocity: Freestream velocity in m/s (for "external" flow)
        angle_of_attack: Angle of attack in degrees (for "external" flow, default 0)
        chord_length: Airfoil chord length in meters (for "external" flow, used in force coefficient calculation, default 1.0)

    Returns:
        Summary of files written and confirmation that case is solver-ready
    """
    if flow_type in ["nozzle_compressible", "nozzle_compressible_simple"]:
        if inlet_total_pressure is None or inlet_total_temperature is None or outlet_static_pressure is None:
            return (f"Error: flow_type '{flow_type}' requires inlet_total_pressure, "
                   f"inlet_total_temperature, and outlet_static_pressure parameters.")
    elif flow_type == "internal":
        if inlet_velocity is None:
            return "Error: flow_type 'internal' requires inlet_velocity parameter."
        if outlet_pressure is None:
            outlet_pressure = 0.0
    elif flow_type == "external":
        if freestream_velocity is None:
            return "Error: flow_type 'external' requires freestream_velocity parameter."
        if outlet_pressure is None:
            outlet_pressure = 0.0  # Default to atmospheric (gauge pressure = 0)
    else:
        return f"Error: Unknown flow_type '{flow_type}'."

    case_path = Path("cases") / case_name
    if not case_path.exists():
        return f"Error: Case '{case_name}' does not exist. Run generate_mesh first."

    mesh_path = case_path / "constant" / "polyMesh"
    if not mesh_path.exists():
        return f"Error: Mesh not found for case '{case_name}'. Run generate_mesh first."

    try:
        system_path = case_path / "system"
        constant_path = case_path / "constant"
        zero_path = case_path / "0"

        system_path.mkdir(exist_ok=True)
        constant_path.mkdir(exist_ok=True)
        zero_path.mkdir(exist_ok=True)

        if flow_type == "nozzle_compressible":
            write_controldict_rhocentralfoam(system_path)
            write_fvschemes_rhocentralfoam(system_path)
            write_fvsolution_rhocentralfoam(system_path)

            write_velocity_field_compressible(zero_path)
            write_pressure_field_compressible(zero_path, inlet_total_pressure, outlet_static_pressure)
            write_temperature_field_compressible(zero_path, inlet_total_temperature)

            write_turbulence_properties(constant_path)
            write_thermophysical_properties(constant_path)

            summary = f"Case setup completed for: {case_name}\n\n"
            summary += "Solver: rhoCentralFoam (compressible, transient, density-based for supersonic flow)\n\n"
            summary += "Files written:\n"
            summary += "  system/controlDict    - rhoCentralFoam, transient (endTime=0.01s), adjustTimeStep\n"
            summary += "                        - deltaT=1e-7, maxCo=0.5, maxDeltaT=1e-5\n"
            summary += "  system/fvSchemes      - Kurganov flux scheme, vanLeer reconstruction\n"
            summary += "  system/fvSolution     - Explicit density-based solver (no SIMPLE)\n"
            summary += f"  0/U                   - pressureInletOutletVelocity at inlet, zeroGradient at outlet, noSlip at wall\n"
            summary += f"  0/p                   - totalPressure at inlet = {inlet_total_pressure} Pa\n"
            summary += f"                        - fixedValue at outlet = {outlet_static_pressure} Pa\n"
            summary += f"  0/T                   - totalTemperature at inlet = {inlet_total_temperature} K\n"
            summary += f"                        - zeroGradient at outlet/wall (adiabatic)\n"
            summary += "  constant/turbulenceProperties    - laminar flow\n"
            summary += "  constant/thermophysicalProperties - air as perfect gas (Cp=1005, MW=28.96)\n"
            summary += "                                    - Sutherland's law for viscosity\n\n"
            summary += "Boundary conditions (nozzle_wedge mesh):\n"
            summary += "  inlet:      totalPressure p, totalTemperature T, pressureInletOutletVelocity U\n"
            summary += "  outlet:     fixedValue p, zeroGradient T, zeroGradient U\n"
            summary += "  wall:       zeroGradient p, zeroGradient T, noSlip U\n"
            summary += "  centerline: symmetry\n"
            summary += "  wedges:     wedge (axisymmetric)\n\n"
            summary += "Case is now solver-ready for rhoCentralFoam\n"
            summary += "  Note: rhoCentralFoam is suited for supersonic/shock-containing flows (M>1, PR>10)"

        elif flow_type == "nozzle_compressible_simple":
            write_controldict_rhosimplefoam(system_path)
            write_fvschemes_rhosimplefoam(system_path)
            write_fvsolution_rhosimplefoam(system_path)

            write_velocity_field_compressible(zero_path)
            write_pressure_field_compressible(zero_path, inlet_total_pressure, outlet_static_pressure)
            write_temperature_field_compressible(zero_path, inlet_total_temperature)

            write_turbulence_properties(constant_path)
            write_thermophysical_properties(constant_path)

            summary = f"Case setup completed for: {case_name}\n\n"
            summary += "Solver: rhoSimpleFoam (compressible, steady-state, pressure-based)\n\n"
            summary += "Files written:\n"
            summary += "  system/controlDict    - rhoSimpleFoam, 1000 iterations, residual control\n"
            summary += "  system/fvSchemes      - bounded upwind schemes for compressible flow\n"
            summary += "  system/fvSolution     - SIMPLE algorithm with density relaxation\n"
            summary += f"  0/U                   - pressureInletOutletVelocity at inlet, zeroGradient at outlet, noSlip at wall\n"
            summary += f"  0/p                   - totalPressure at inlet = {inlet_total_pressure} Pa\n"
            summary += f"                        - fixedValue at outlet = {outlet_static_pressure} Pa\n"
            summary += f"  0/T                   - totalTemperature at inlet = {inlet_total_temperature} K\n"
            summary += f"                        - zeroGradient at outlet/wall (adiabatic)\n"
            summary += "  constant/turbulenceProperties    - laminar flow\n"
            summary += "  constant/thermophysicalProperties - air as perfect gas (Cp=1005, MW=28.96)\n"
            summary += "                                    - Sutherland's law for viscosity\n\n"
            summary += "Boundary conditions (nozzle_wedge mesh):\n"
            summary += "  inlet:      totalPressure p, totalTemperature T, pressureInletOutletVelocity U\n"
            summary += "  outlet:     fixedValue p, zeroGradient T, zeroGradient U\n"
            summary += "  wall:       zeroGradient p, zeroGradient T, noSlip U\n"
            summary += "  centerline: symmetry\n"
            summary += "  wedges:     wedge (axisymmetric)\n\n"
            summary += "Case is now solver-ready for rhoSimpleFoam\n"
            summary += "  Note: rhoSimpleFoam is suited for subsonic/transonic flows (M<1.5, PR<10)"

        elif flow_type == "external":
            write_controldict_simplefoam(system_path, include_force_coeffs=True,
                                        chord_length=chord_length,
                                        freestream_velocity=freestream_velocity,
                                        angle_of_attack=angle_of_attack)
            write_fvschemes_simplefoam(system_path)
            write_fvsolution_simplefoam(system_path)

            write_velocity_field(zero_path, inlet_velocity=0, flow_type=flow_type,
                               freestream_velocity=freestream_velocity,
                               angle_of_attack=angle_of_attack)
            write_pressure_field(zero_path, outlet_pressure=outlet_pressure,
                               flow_type=flow_type, freestream_pressure=outlet_pressure)

            write_turbulence_properties(constant_path)
            write_transport_properties(constant_path)

            import math
            aoa_rad = math.radians(angle_of_attack)
            u_x = freestream_velocity * math.cos(aoa_rad)
            u_y = freestream_velocity * math.sin(aoa_rad)

            summary = f"Case setup completed for: {case_name}\n\n"
            summary += "Solver: simpleFoam (incompressible, steady-state)\n\n"
            summary += "Files written:\n"
            summary += "  system/controlDict    - simpleFoam, 500 iterations, residual control\n"
            summary += f"                        - forceCoeffs function enabled (chord={chord_length}m)\n"
            summary += "  system/fvSchemes      - steady RANS schemes (linearUpwind for U)\n"
            summary += "  system/fvSolution     - SIMPLE algorithm with relaxation factors\n"
            summary += f"  0/U                   - freestream velocity = {freestream_velocity} m/s\n"
            summary += f"                        - angle of attack = {angle_of_attack}°\n"
            summary += f"                        - velocity components: Ux = {u_x:.4f} m/s, Uy = {u_y:.4f} m/s\n"
            summary += f"  0/p                   - freestream pressure = {outlet_pressure} Pa (gauge)\n"
            summary += "  constant/turbulenceProperties - laminar flow\n"
            summary += "  constant/transportProperties  - nu = 1.5e-5 m²/s (air at 20°C)\n\n"
            summary += "Boundary conditions (airfoil_ogrid mesh):\n"
            summary += "  airfoil:  noSlip U, zeroGradient p (standard wall)\n"
            summary += "  farfield: freestreamVelocity U, freestreamPressure p\n"
            summary += "            (correctly handles inflow/outflow on same patch)\n"
            summary += "  front/back: empty (2D case)\n\n"
            summary += "Case is now solver-ready for simpleFoam (external aerodynamics)"

        else:  # flow_type == "internal"
            write_controldict_simplefoam(system_path)
            write_fvschemes_simplefoam(system_path)
            write_fvsolution_simplefoam(system_path)

            write_velocity_field(zero_path, inlet_velocity, flow_type)
            write_pressure_field(zero_path, outlet_pressure, flow_type)

            write_turbulence_properties(constant_path)
            write_transport_properties(constant_path)

            summary = f"Case setup completed for: {case_name}\n\n"
            summary += "Solver: simpleFoam (incompressible, steady-state)\n\n"
            summary += "Files written:\n"
            summary += "  system/controlDict    - simpleFoam, 500 iterations, residual control\n"
            summary += "  system/fvSchemes      - steady RANS schemes (linearUpwind for U)\n"
            summary += "  system/fvSolution     - SIMPLE algorithm with relaxation factors\n"
            summary += f"  0/U                   - inlet velocity = {inlet_velocity} m/s (x-direction)\n"
            summary += f"  0/p                   - outlet pressure = {outlet_pressure} Pa (gauge)\n"
            summary += "  constant/turbulenceProperties - laminar flow\n"
            summary += "  constant/transportProperties  - nu = 1.5e-5 m²/s (air at 20°C)\n\n"
            summary += "Boundary conditions:\n"
            summary += "  inlet:  fixedValue U, zeroGradient p\n"
            summary += "  outlet: zeroGradient U, fixedValue p\n"
            summary += "  walls:  noSlip U, zeroGradient p\n\n"
            summary += "Case is now solver-ready for simpleFoam"

        return summary

    except Exception as e:
        return f"Error setting up case: {e}"
