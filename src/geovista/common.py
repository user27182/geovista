"""
A package for provisioning common geovista infra-structure.

"""
from collections.abc import Iterable
from typing import Any, Optional, Tuple

import numpy as np
from numpy import ma
import numpy.typing as npt
import pyvista as pv

__all__ = [
    "GV_CELL_IDS",
    "GV_FIELD_CRS",
    "GV_FIELD_NAME",
    "GV_FIELD_RADIUS",
    "GV_POINT_IDS",
    "GV_REMESH_POINT_IDS",
    "RADIUS",
    "REMESH_JOIN",
    "REMESH_SEAM",
    "VTK_CELL_IDS",
    "VTK_POINT_IDS",
    "ZLEVEL_FACTOR",
    "calculate_radius",
    "nan_mask",
    "sanitize_data",
    "set_jupyter_backend",
    "to_lonlat",
    "to_lonlats",
    "to_xy0",
    "to_xyz",
    "triangulated",
    "wrap",
]

#
# TODO: support richer default management
#

#: Default base for wrapped longitude half-open interval, in degrees.
BASE: float = -180.0

#: Name of the geovista cell indices array.
GV_CELL_IDS: str = "gvOriginalCellIds"

#: The field array name of the CF serialized pyproj CRS.
GV_FIELD_CRS: str = "gvCRS"

#: The field array name of the mesh containing field, point and/or cell data.
GV_FIELD_NAME: str = "gvName"

#: The field array name of the mesh radius.
GV_FIELD_RADIUS: str = "gvRadius"

#: Name of the geovista point indices array.
GV_POINT_IDS: str = "gvOriginalPointIds"

#: Name of the geovista remesh point indices/marker array.
GV_REMESH_POINT_IDS: str = "gvRemeshPointIds"

#: Default jupyter plotting backend for pyvista.
JUPYTER_BACKEND: str = "pythreejs"

#: Default period for wrapped longitude half-open interval, in degrees.
PERIOD: float = 360.0

#: Default radius of a spherical mesh.
RADIUS: float = 1.0

#: Marker for remesh filter cell join point.
REMESH_JOIN: int = -3

#: Marker for remesh filter western cell boundary point.
REMESH_SEAM: int = -1

#: Name of the VTK cell indices array.
VTK_CELL_IDS: str = "vtkOriginalCellIds"

#: Name of the VTK point indices array.
VTK_POINT_IDS: str = "vtkOriginalPointIds"

#: Proportional multiplier for z-axis levels/offsets.
ZLEVEL_FACTOR: float = 1e-3


def active_kernel() -> bool:
    """
    Determine whether we are executing within an ``IPython`` kernel.

    Returns
    -------
    bool

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    result = True

    try:
        # pylint: disable-next=import-outside-toplevel
        from IPython import get_ipython

        ip = get_ipython()
        # the following statement may or may not raise an exception
        ip.kernel  # pylint: disable=pointless-statement
    except (AttributeError, ModuleNotFoundError):
        result = False

    return result


def calculate_radius(
    mesh: pv.PolyData,
    origin: Optional[Tuple[float, float, float]] = None,
) -> float:
    """
    Determine the radius of the provided mesh.

    Note that, assumes that the mesh is a sphere that has not been warped.

    Parameters
    ----------
    mesh : PolyData
        The surface that requires its radius to be calculated, relative to
        the `origin`.
    origin : float, default=(0, 0, 0)
        The (x, y, z) cartesian center of the spheroid mesh.

    Returns
    -------
    float
        The radius of the provided mesh.

    Notes
    -----
    .. versionadded: 0.1.0

    """
    xmin, xmax, ymin, ymax, zmin, zmax = mesh.bounds
    xdiff, ydiff, zdiff = (xmax - xmin), (ymax - ymin), (zmax - zmin)

    if np.isclose(xdiff, 0) or np.isclose(ydiff, 0) or np.isclose(zdiff, 0):
        emsg = (
            "Cannot calculate radius of a surface that does not appear to be "
            "spherical."
        )
        raise ValueError(emsg)

    if origin is None:
        origin = (0, 0, 0)

    ox, oy, oz = origin
    # sample a representative mesh point
    mx, my, mz = mesh.points[0]
    radius = np.sqrt((mx - ox) ** 2 + (my - oy) ** 2 + (mz - oz) ** 2)

    gvRadius = (
        mesh.field_data[GV_FIELD_RADIUS][0]
        if GV_FIELD_RADIUS in mesh.field_data
        else RADIUS
    )

    if np.isclose(radius, gvRadius):
        radius = gvRadius

    mesh.field_data[GV_FIELD_RADIUS] = np.array([radius])

    return radius


def nan_mask(data: npt.ArrayLike) -> np.ndarray:
    """
    Replaces any masked array values with NaNs.

    As a consequence of filling the mask with NaNs, non-float arrays will be
    cast to float.

    Parameters
    ----------
    data : ArrayLike
        The masked array to be filled with NaNs.

    Returns
    -------
    ndarray
        The `data` with masked values replaced with NaNs.

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    if np.ma.isMaskedArray(data):
        if data.dtype.char not in np.typecodes["Float"]:
            data = ma.asanyarray(data, dtype=float)

        data = data.filled(np.nan)

    return data


def sanitize_data(
    *meshes: Any,
) -> None:
    """
    Purge standard VTK helper cell and point data index arrays.

    Parameters
    ----------
    meshes : iterable of PolyData
        The :class:`pyvista.PolyData` to sanitize.

    Notes
    -----
    .. versionadded:: 0.1.0
    """
    if not meshes:
        emsg = "Expected one or more meshes to sanitize."
        raise ValueError(emsg)

    for mesh in meshes:
        if VTK_CELL_IDS in mesh.cell_data:
            del mesh.cell_data[VTK_CELL_IDS]

        if VTK_POINT_IDS in mesh.point_data:
            del mesh.point_data[VTK_POINT_IDS]


def set_jupyter_backend(backend: Optional[str] = None) -> bool:
    """
    Configure the jupyter plotting backend for pyvista.

    Parameters
    ----------
    backend : str, optional
        The pyvista plotting backend. For further details see
        :func:`pyvista.set_jupyter_backend`. If ``None``, defaults to
        :data:`JUPYTER_BACKEND`.

    Returns
    -------
    bool
        Whether the jupyter backend was successfully configured.

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    result = False
    if active_kernel():
        try:
            if backend is None:
                backend = JUPYTER_BACKEND
            pv.set_jupyter_backend(backend)
            result = True
        except ImportError:
            pass

    return result


def to_lonlat(
    xyz: npt.ArrayLike,
    radians: Optional[float] = None,
    radius: Optional[float] = None,
) -> np.ndarray:
    """
    Convert the cartesian `xyz` point on a sphere to geographic longitude
    and latitude, in degrees.

    Parameters
    ----------
    xyz : ArrayLike
        The cartesian (x, y, z) point to be converted.
    radians : bool, default=False
        Convert resultant longitude and latitude values to radians.
        Default units are degrees.
    radius : float, default=1.0
        The `radius` of the sphere. Defaults to an S2 unit sphere.

    Returns
    -------
    ndarray
        The longitude and latitude values.

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    point = np.asanyarray(xyz)

    if point.shape != (3,):
        shape = f" with shape {point.shape}" if point.shape else ""
        emsg = (
            "Require a 1D array of (x, y, z) points, got a "
            f"{point.ndim}D array{shape}."
        )
        raise ValueError(emsg)

    (result,) = to_lonlats(point, radians=radians, radius=radius)

    return result


def to_lonlats(
    xyz: npt.ArrayLike,
    radians: Optional[bool] = False,
    radius: Optional[float] = None,
    stacked: Optional[bool] = True,
) -> np.ndarray:
    """
    Convert the cartesian `xyz` points on a sphere to geographic longitudes
    and latitudes, in degrees.

    Parameters
    ----------
    xyz : ArrayLike
        The cartesian (x, y, z) points to be converted.
    radians : bool, default=False
        Convert resultant longitude and latitude values to radians.
        Default units are degrees.
    radius : float, default=1.0
        The `radius` of the sphere. Defaults to an S2 unit sphere.
    stacked : bool, default=True
        Default the resultant shape to be (N, 2), otherwise (2, N).

    Returns
    -------
    ndarray
        The longitude and latitude values.

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    points = np.atleast_2d(xyz)
    radius = RADIUS if radius is None else abs(radius)

    if points.ndim != 2 or points.shape[1] != 3:
        emsg = (
            "Require a 2D array of (x, y, z) points, got a "
            f"{points.ndim}D array with shape {points.shape}."
        )
        raise ValueError(emsg)

    base, period = (np.radians(BASE), np.radians(PERIOD)) if radians else (BASE, PERIOD)

    lons = np.arctan2(points[:, 1], points[:, 0])
    if not radians:
        lons = np.degrees(lons)
    lons = wrap(lons, base=base, period=period)

    zr = points[:, 2] / radius
    # defensive clobber of values outside arcsin domain [-1, 1]
    if indices := np.where(zr > 1):
        zr[indices] = 1.0
    if indices := np.where(zr < -1):
        zr[indices] = -1.0
    lats = np.arcsin(zr)
    if not radians:
        lats = np.degrees(lats)

    data = [lons, lats]
    result = np.vstack(data).T if stacked else np.array(data)

    return result


def to_xy0(
    mesh: pv.PolyData,
    radius: Optional[float] = None,
    stacked: Optional[bool] = True,
    closed_interval: Optional[bool] = False,
) -> np.ndarray:
    """
    Convert the `mesh` cartesian `xyz` points on a sphere to geographic
    longitude (φ) and latitude (λ) `xy0` (i.e., φλ0) coordinates.

    Parameters
    ----------
    mesh : PolyData
        The mesh containing the cartesian (x, y, z) points to be converted to
        longitude and latitude coordinates.
    radius : float, optional
        The radius of the sphere. If not provided the radius is determined
        from the mesh.
    stacked : bool, default=True
        Specify whether the resultant xy0 coordinates have shape (N, 3).
        Otherwise, they will have shape (3, N).
    closed_interval : bool, default=False
        Longitude values will be in the half-closed interval [-180, 180). However,
        if the mesh has a seam at the 180th meridian and `closed_interval`
        is ``True``, then longitudes will be in the closed interval [-180, 180].

    Returns
    -------
    ndarray
        The longitude and latitude xy0 coordinates, in degrees.

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    radius = calculate_radius(mesh) if radius is None else abs(radius)
    lons, lats = to_lonlats(mesh.points, radius=radius, stacked=False)
    z = np.zeros_like(lons)
    data = [lons, lats, z]

    if closed_interval:
        if GV_REMESH_POINT_IDS in mesh.point_data:
            seam_ids = np.where(mesh[GV_REMESH_POINT_IDS] == REMESH_SEAM)[0]
            seam_lons = lons[seam_ids]
            seam_mask = np.isclose(np.abs(seam_lons), 180)
            lons[seam_ids[seam_mask]] = 180

    result = np.vstack(data).T if stacked else np.array(data)

    return result


def to_xyz(
    longitudes: npt.ArrayLike,
    latitudes: npt.ArrayLike,
    radius: Optional[float] = None,
    stacked: Optional[bool] = True,
) -> np.ndarray:
    """
    Convert longitudes (φ) and latitudes (λ) to geocentric xyz coordinates.

    Parameters
    ----------
    longitudes : ArrayLike
        The longitude values (degrees) to be converted.
    latitudes : ArrayLike
        The latitude values (degrees) to be converted.
    radius : float, default=1.0
        The radius of the sphere. Defaults to an S2 unit sphere.
    stacked : bool, default=True
        Specify whether the resultant xyz coordinates have shape (N, 3).
        Otherwise, they will have shape (3, N).

    Returns
    -------
    ndarray
        The geocentric xyz coordinates.

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    longitudes = np.ravel(longitudes)
    latitudes = np.ravel(latitudes)
    radius = RADIUS if radius is None else abs(radius)

    x_rad = np.radians(longitudes)
    y_rad = np.radians(90.0 - latitudes)
    x = radius * np.sin(y_rad) * np.cos(x_rad)
    y = radius * np.sin(y_rad) * np.sin(x_rad)
    z = radius * np.cos(y_rad)
    xyz = [x, y, z]

    if stacked:
        xyz = np.vstack(xyz).T
    else:
        xyz = np.array(xyz)

    return xyz


def triangulated(surface: pv.PolyData) -> bool:
    """
    Determine whether the provided surface is triangulated.

    Parameters
    ----------
    surface : PolyData
        The :class:`pyvista.PolyData` surface mesh to check
        whether the geometry of all its cells are triangles.

    Returns
    -------
    bool
        Whether the surface is fully triangulated.

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    return np.all(np.diff(surface._offset_array) == 3)


def wrap(
    longitudes: npt.ArrayLike,
    base: Optional[float] = BASE,
    period: Optional[float] = PERIOD,
    dtype: Optional[np.dtype] = None,
) -> np.ndarray:
    """
    Transform the longitude values to be within the half-open interval
    [base, base + period).

    Parameters
    ----------
    longitudes : ArrayLike
        One or more longitude values to be wrapped.
    base : float, default=-180.0
        The start limit of the half-open interval.
    period : float, default=360.0
        The end limit of the half-open interval expressed as a length
        from the `base`, in the same units.
    dtype : data-type, default=float64
        The resultant longitude `dtype`.

    Returns
    -------
    ndarray
        The transformed longitude values.

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    if not isinstance(longitudes, Iterable):
        longitudes = [longitudes]

    if dtype is None:
        dtype = np.float64

    longitudes = np.asanyarray(longitudes, dtype=dtype)
    result = ((longitudes - base + period * 2) % period) + base

    return result