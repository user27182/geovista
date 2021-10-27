from collections.abc import Iterable
from datetime import datetime
from typing import Dict, Optional, Tuple, Union

import numpy as np
from numpy.typing import ArrayLike
import pyproj
import pyvista as pv

from .common import to_xyz, wrap
from .log import get_logger

__all__ = ["BBox", "line", "npoints", "npoints_by_idx", "panel", "wedge"]

# Configure the logger.
logger = get_logger(__name__)

# type aliases
Corners = Tuple[float, float, float, float]

#: Default geodesic ellipse. See :func:`pyproj.get_ellps_map`.
ELLIPSE: str = "WGS84"

#: Number of equally spaced geodesic points between/including endpoint/s.
GEODESIC_NPTS: int = 64

#: The bounding-box face geometry will contain ``BBOX_C**2`` cells.
BBOX_C: int = 256

#: The bounding-box tolerance on intersection.
BBOX_TOLERANCE: int = 0

#: Lookup table for cubed sphere panel index by panel name.
PANEL_IDX_BY_NAME: Dict[str, int] = dict(
    africa=0,
    asia=1,
    pacific=2,
    americas=3,
    polar=4,
    antarctic=5,
)

#: Lookup table for cubed sphere panel name by panel index.
PANEL_NAME_BY_IDX: Dict[int, str] = {
    0: "africa",
    1: "asia",
    2: "pacific",
    3: "americas",
    4: "polar",
    5: "antarctic",
}

#: Latitude (degrees) of a cubed sphere panel corner.
CSC: float = np.rad2deg(np.arcsin(1 / np.sqrt(3)))

#: Cubed sphere panel bounded-box longitudes and latitudes.
PANEL_BBOX_BY_IDX: Dict[int, Tuple[Corners, Corners]] = {
    0: ((-45, 45, 45, -45), (CSC, CSC, -CSC, -CSC)),
    1: ((45, 135, 135, 45), (CSC, CSC, -CSC, -CSC)),
    2: ((135, -135, -135, 135), (CSC, CSC, -CSC, -CSC)),
    3: ((-135, -45, -45, -135), (CSC, CSC, -CSC, -CSC)),
    4: ((-45, 45, 135, -135), (CSC, CSC, CSC, CSC)),
    5: ((-45, 45, 135, -135), (-CSC, -CSC, -CSC, -CSC)),
}

#: The number of cubed sphere panels.
N_PANELS: int = len(PANEL_IDX_BY_NAME)

#: Preference for an operation to focus on all cell vertices.
PREFERENCE_CELL: str = "cell"

#: Preference for an operation to focus on the cell center.
PREFERENCE_CENTER: str = "center"

#: Preference for an operation to focus on any cell vertex.
PREFERENCE_POINT: str = "point"

#: Enumeration of supported preferences.
PREFERENCES: Tuple[str] = (PREFERENCE_CELL, PREFERENCE_CENTER, PREFERENCE_POINT)


class BBox:
    """
    TBD

    Notes
    -----
    .. versionadded:: 0.1.0

    """

    RADIUS_RATIO = 1e-1

    def __init__(
        self,
        lons: ArrayLike,
        lats: ArrayLike,
        ellps: Optional[str] = ELLIPSE,
        radius: Optional[float] = 1.0,
        c: Optional[int] = BBOX_C,
        triangulate: Optional[bool] = False,
    ):
        """
        TBD

        Notes
        -----
        .. versionadded:: 0.1.0

        """
        if not isinstance(lons, Iterable):
            lons = [lons]
        if not isinstance(lats, Iterable):
            lats = [lats]

        lons = np.asanyarray(lons)
        lats = np.asanyarray(lats)
        n_lons, n_lats = lons.size, lats.size

        if n_lons != n_lats:
            emsg = (
                f"Require the same number of longitudes ({n_lons}) and "
                f"latitudes ({n_lats})."
            )
            raise ValueError(emsg)

        if n_lons < 4:
            emsg = (
                "Require a bounded-box geometry containing at least 4 longitude/latitude "
                f"values to create the bounded-box manifold, got '{n_lons}'."
            )
            raise ValueError(emsg)

        if n_lons > 5:
            emsg = (
                "Require a bounded-box geometry containing 4 (open) or 5 (closed) "
                "longitude/latitude values to create the bounded-box manifold, "
                f"got {n_lons}."
            )
            raise ValueError(emsg)

        # ensure the specified bbox geometry is open
        if np.isclose(lons[0], lons[-1]) and np.isclose(lats[0], lats[-1]):
            lons, lats = lons[-1], lats[-1]

        self.lons = lons
        self.lats = lats
        self.ellps = ellps
        self.radius = radius
        self.c = c
        self.triangulate = triangulate

        # initialise
        self._idx_map = np.empty((self.c + 1, self.c + 1), dtype=int)
        self._bbox_lons, self._bbox_lats = [], []
        self._bbox_count = 0
        self._geod = pyproj.Geod(ellps=ellps)
        self._npts = self.c - 1
        self._n_faces = self.c * self.c
        self._n_points = (self.c + 1) * (self.c + 1)
        self._extra = dict(cls=self.__class__.__name__)

        offset = self.radius * self.RADIUS_RATIO
        self._inner_radius = self.radius - offset
        self._outer_radius = self.radius + offset

        logger.debug(f"c: {self.c}", extra=self._extra)
        logger.debug(f"n_faces: {self._n_faces}", extra=self._extra)
        logger.debug(f"idx_map: {self._idx_map.shape}", extra=self._extra)
        logger.debug(
            f"radii: {self.radius}, {self._inner_radius}, {self._outer_radius}",
            extra=self._extra,
        )

        self._generate_mesh()

    def __eq__(self, other) -> bool:
        result = NotImplemented
        if isinstance(other, BBox):
            result = False
            lhs = (self.ellps, self.c, self.triangulate)
            rhs = (other.ellps, other.c, other.triangulate)
            if all(map(lambda x: x[0] == x[1], zip(lhs, rhs))) and np.isclose(
                self.radius, other.radius
            ):
                if np.allclose(self.lons, other.lons):
                    result = np.allclose(self.lats, other.lats)
        return result

    def __ne__(self, other) -> bool:
        result = self == other
        if result is not NotImplemented:
            result = not result
        return result

    def __repr__(self) -> str:
        params = (
            f"ellps={self.ellps}, c={self.c}, n_points={self.mesh.n_points}, "
            f"n_cells={self.mesh.n_cells}"
        )
        result = f"{__package__}.{self.__class__.__name__}<{params}>"
        return result

    def _face_edge_idxs(self) -> ArrayLike:
        """
        TBD

        Notes
        -----
        .. versionadded:: 0.1.0

        """
        edge = np.concatenate(
            [
                self._idx_map[0],
                self._idx_map[1:, -1],
                self._idx_map[-1, -2::-1],
                self._idx_map[-2:0:-1, 0],
            ]
        )
        return edge

    def _generate_face(self) -> None:
        """
        TBD

        Notes
        -----
        .. versionadded:: 0.1.0

        """
        # corner indices
        c1_idx, c2_idx, c3_idx, c4_idx = range(4)

        def bbox_extend(lons: Tuple[float], lats: Tuple[float]) -> None:
            assert len(lons) == len(lats)
            self._bbox_lons.extend(lons)
            self._bbox_lats.extend(lats)
            self._bbox_count += len(lons)

        def bbox_update(idx1, idx2, row=None, column=None) -> None:
            assert row is not None or column is not None
            if row is None:
                row = slice(None)
            if column is None:
                column = slice(None)
            glons, glats = npoints_by_idx(
                self._bbox_lons,
                self._bbox_lats,
                idx1,
                idx2,
                npts=self._npts,
                geod=self._geod,
            )
            self._idx_map[row, column] = (
                [idx1] + list(np.arange(self._npts) + self._bbox_count) + [idx2]
            )
            bbox_extend(glons, glats)

        # register bbox edge indices, and points
        bbox_extend(self.lons, self.lats)
        bbox_update(c1_idx, c2_idx, row=0)
        bbox_update(c4_idx, c3_idx, row=-1)
        bbox_update(c1_idx, c4_idx, column=0)
        bbox_update(c2_idx, c3_idx, column=-1)

        # register bbox inner indices and points
        for row_idx in range(1, self.c):
            row = self._idx_map[row_idx]
            bbox_update(row[0], row[-1], row=row_idx)

    def _generate_mesh(self) -> None:
        """
        TBD

        Notes
        -----
        .. versionadded:: 0.1.0

        """
        self._generate_face()
        skirt_faces = self._generate_skirt()

        # generate the face indices
        bbox_n_faces = self._n_faces * 2
        faces_N = np.broadcast_to(np.array([4], dtype=np.int8), (bbox_n_faces, 1))
        faces_c1 = np.ravel(self._idx_map[: self.c, : self.c]).reshape(-1, 1)
        faces_c2 = np.ravel(self._idx_map[: self.c, 1:]).reshape(-1, 1)
        faces_c3 = np.ravel(self._idx_map[1:, 1:]).reshape(-1, 1)
        faces_c4 = np.ravel(self._idx_map[1:, : self.c]).reshape(-1, 1)
        inner_faces = np.hstack([faces_c1, faces_c2, faces_c3, faces_c4])
        outer_faces = inner_faces + self._n_points
        faces = np.vstack([inner_faces, outer_faces])
        bbox_faces = np.hstack([faces_N, faces])

        # convert bbox lons/lats to ndarray (internal convenience i.e., boundary)
        self._bbox_lons = np.asanyarray(self._bbox_lons)
        self._bbox_lats = np.asanyarray(self._bbox_lats)

        # generate the face points
        inner_xyz = to_xyz(self._bbox_lons, self._bbox_lats, radius=self._inner_radius)
        outer_xyz = to_xyz(self._bbox_lons, self._bbox_lats, radius=self._outer_radius)
        bbox_xyz = np.vstack([inner_xyz, outer_xyz])

        # include the bbox skirt
        bbox_faces = np.vstack([bbox_faces, skirt_faces])
        bbox_n_faces += skirt_faces.shape[0]

        # create the mesh
        self.mesh = pv.PolyData(bbox_xyz, faces=bbox_faces, n_faces=bbox_n_faces)
        logger.debug(
            f"bbox: n_faces={self.mesh.n_faces}, n_points={self.mesh.n_points}",
            extra=self._extra,
        )

        if self.triangulate:
            self.mesh = self.mesh.triangulate()
            logger.debug(
                f"bbox: n_faces={self.mesh.n_faces}, n_points={self.mesh.n_points} (tri)",
                extra=self._extra,
            )

    def _generate_skirt(self) -> ArrayLike:
        """
        TBD

        Notes
        -----
        .. verseionadded:: 0.1.0

        """
        skirt_n_faces = 4 * self.c
        faces_N = np.broadcast_to(np.array([4], dtype=np.int8), (skirt_n_faces, 1))
        faces_c1 = self._face_edge_idxs().reshape(-1, 1)
        faces_c2 = np.roll(faces_c1, -1)
        faces_c3 = faces_c2 + self._n_points
        faces_c4 = np.roll(faces_c3, 1)
        faces = np.hstack([faces_N, faces_c1, faces_c2, faces_c3, faces_c4])
        logger.debug(f"skirt_n_faces: {skirt_n_faces}", extra=self._extra)
        return faces

    def boundary(self, radius: Optional[float] = None):
        """
        TBD

        Notes
        -----
        .. versionadded:: 0.1.0

        """
        # TODO: address "fudge-factor" zlevel
        if radius is None:
            radius = 1.0 + 1.0 / 1e4

        edge_idxs = self._face_edge_idxs()
        edge_lons = self._bbox_lons[edge_idxs]
        edge_lats = self._bbox_lats[edge_idxs]
        edge_xyz = to_xyz(edge_lons, edge_lats, radius=radius)
        edge = pv.lines_from_points(edge_xyz, close=True)
        return edge

    def enclosed(
        self,
        surface: pv.PolyData,
        tolerance: Optional[float] = BBOX_TOLERANCE,
        outside: Optional[bool] = False,
        preference: str = PREFERENCE_CENTER,
    ) -> pv.UnstructuredGrid:
        """
        Extract the mesh region of the ``surface`` contained within the
        bounded-box.

        Note that, any ``surface`` points that are on the edge of the
        bounded-box will be deemed to be inside, and so will the cells
        associated with those ``surface`` points. See ``preference``.

        Parameters
        ----------
        surface : PolyData
            The :class:`~pyvista.PolyData` mesh to be checked for containment.
        tolerance : float, default=0
            The tolerance on the intersection operation with the ``surface``,
            expressed as a fraction of the diagonal of the bounding box.
        outside : bool, default=False
            By default, select those points of the ``surface`` that are inside
            the bounded-box. Otherwise, select those points that are outside
            the bounded-box.
        preference : str, default="cell"
            Criteria for defining whether a face of a ``surface`` mesh is
            deemed to be enclosed by the bounded-box. A ``preference`` of
            ``cell`` requires all points defining the face to be in or on the
            bounded-box. A ``preference`` of ``center`` requires that only the
            face cell center is in or on the bounded-box. A ``preference`` of
            ``point`` requires at least one point that defines the face to be
            in or on the bounded-box.

        Returns
        -------
        UnstructuredGrid
            The :class:`~pyvista.UnstructuredGrid` representing those parts of
            the provided ``surface`` enclosed by the bounded-box. This behaviour
            may be inverted with the ``outside`` parameter.

        Notes
        -----
        .. versionadded:: 0.1.0

        """
        if preference is None:
            preference = PREFERENCE_CELL

        if preference.lower() not in PREFERENCES:
            ordered = sorted(PREFERENCES)
            valid = ", ".join(f"'{kind}'" for kind in ordered[:-1])
            valid = f"{valid} or '{ordered[-1]}'"
            emsg = f"Preference must be either {valid}, got '{preference}'."
            raise ValueError(emsg)

        preference = preference.lower()
        check_cells = False
        logger.debug(f"preference: '{preference}'", extra=self._extra)
        logger.debug(
            f"surface: n_cells {surface.n_cells}, n_points {surface.n_points}",
            extra=self._extra,
        )

        if preference == PREFERENCE_CELL:
            preference = PREFERENCE_POINT
            check_cells = True

        if preference == PREFERENCE_CENTER:
            original = surface
            surface = surface.cell_centers()
            logger.debug(
                f"calculated {surface.n_cells} cell centers", extra=self._extra
            )

        # filter the surface with the bbox mesh
        start = datetime.now()
        selected = surface.select_enclosed_points(
            self.mesh, tolerance=tolerance, inside_out=outside, check_surface=False
        )
        end = datetime.now()

        logger.debug(
            f"selected enclosed points in {(end-start).total_seconds()}s",
            extra=self._extra,
        )

        # sample the surface with the enclosed cells to extract the bbox region
        if preference == PREFERENCE_CENTER:
            region = original.extract_cells(selected["SelectedPoints"].view(bool))
        else:
            region = selected.threshold(
                0.5, scalars="SelectedPoints", preference="cell"
            )

        logger.debug(
            f"region: n_cells {region.n_cells}, n_points {region.n_points}",
            extra=self._extra,
        )

        # if required, perform cell vertex enclosure checks on the bbox region
        if check_cells and region.n_cells and region.n_points:
            enclosed = []
            npts_per_cell = region.cells[0]
            cells = region.cells.reshape(-1, npts_per_cell + 1)

            # only support cells with the same type e.g., all quads, or all
            # triangles etc, but never a mixture.
            if np.diff(cells[:, 0]).sum() != 0:
                emsg = (
                    "Cannot extract surface enclosed by the bounded-box when "
                    "the surface has mixed face types and 'preference' is "
                    "'cell'. Try 'center' or 'point' instead."
                )
                raise ValueError(emsg)

            for idx in range(1, npts_per_cell + 1):
                points = pv.PolyData(region.points[cells[:, idx]])
                start = datetime.now()
                selected = points.select_enclosed_points(
                    self.mesh,
                    tolerance=tolerance,
                    inside_out=outside,
                    check_surface=False,
                )
                end = datetime.now()
                enclosed.append(selected["SelectedPoints"].view(bool).reshape(-1, 1))
                logger.debug(
                    f"cell idx {idx}: selected {np.sum(selected['SelectedPoints'])} from "
                    f"{points.n_cells} points [{(end-start).total_seconds()}]",
                    extra=self._extra,
                )

            enclosed = np.all(np.hstack(enclosed), axis=-1)
            region = region.extract_cells(enclosed)
            logger.debug(
                f"region: n_cells {region.n_cells}, n_points {region.n_points}",
                extra=self._extra,
            )

        return region


def line(
    lons: ArrayLike,
    lats: ArrayLike,
    npts: Optional[int] = GEODESIC_NPTS,
    ellps: Optional[str] = ELLIPSE,
    radius: Optional[float] = None,
    close: Optional[bool] = False,
) -> pv.PolyData:
    """
    TBD

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    # TODO: address "fudge-factor" zlevel
    if radius is None:
        radius = 1.0 + 1.0 / 1e4

    if not isinstance(lons, Iterable):
        lons = [lons]
    if not isinstance(lats, Iterable):
        lats = [lats]

    lons = np.asanyarray(lons)
    lats = np.asanyarray(lats)
    n_lons, n_lats = lons.size, lats.size

    if n_lons != n_lats:
        emsg = (
            f"Require the same number of longitudes ({n_lons}) and "
            f"latitudes ({n_lats})."
        )
        raise ValueError(emsg)

    if n_lons < 2:
        emsg = (
            "Require a line geometry containing at least 2 longitude/latitude "
            f"values, got '{n_lons}'."
        )
        raise ValueError(emsg)

    # ensure the specified line geometry is open
    if np.isclose(lons[0], lons[-1]) and np.isclose(lats[0], lats[-1]):
        lons, lats = lons[-1], lats[-1]

    line_lons, line_lats = [], []
    geod = pyproj.Geod(ellps=ellps)

    for idx in range(n_lons - 1):
        glons, glats = npoints_by_idx(
            lons,
            lats,
            idx,
            idx + 1,
            npts=npts,
            include_start=True,
            include_end=False,
            geod=geod,
        )
        line_lons.extend(glons)
        line_lats.extend(glats)

    # finally, include the end-point
    line_lons.append(lons[-1])
    line_lats.append(lats[-1])

    xyz = to_xyz(line_lons, line_lats, radius=radius)
    line = pv.lines_from_points(xyz, close=close)

    return line


def npoints(
    start_lon: float,
    start_lat: float,
    end_lon: float,
    end_lat: float,
    npts: Optional[int] = GEODESIC_NPTS,
    radians: Optional[bool] = False,
    include_start: Optional[bool] = False,
    include_end: Optional[bool] = False,
    geod: Optional[pyproj.Geod] = None,
) -> Tuple[Tuple[float], Tuple[float]]:
    """
    TBD

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    if geod is None:
        geod = pyproj.Geod(ellps=ELLIPSE)

    initial_idx = 0 if include_start else 1
    terminus_idx = 0 if include_end else 1

    glonlats = geod.npts(
        start_lon,
        start_lat,
        end_lon,
        end_lat,
        npts,
        radians=radians,
        initial_idx=initial_idx,
        terminus_idx=terminus_idx,
    )
    glons, glats = zip(*glonlats)
    glons = tuple(wrap(glons))

    return glons, glats


def npoints_by_idx(
    lons: ArrayLike,
    lats: ArrayLike,
    start_idx: int,
    end_idx: int,
    npts: Optional[int] = GEODESIC_NPTS,
    radians: Optional[bool] = False,
    include_start: Optional[bool] = False,
    include_end: Optional[bool] = False,
    geod: Optional[pyproj.Geod] = None,
) -> Tuple[Tuple[float], Tuple[float]]:
    """
    TBD

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    if geod is None:
        geod = pyproj.Geod(ellps=ELLIPSE)

    start_lonlat = lons[start_idx], lats[start_idx]
    end_lonlat = lons[end_idx], lats[end_idx]

    result = npoints(
        *start_lonlat,
        *end_lonlat,
        npts=npts,
        radians=radians,
        include_start=include_start,
        include_end=include_end,
        geod=geod,
    )

    return result


def panel(
    name: Union[int, str],
    ellps: Optional[str] = ELLIPSE,
    radius: Optional[float] = 1.0,
    c: Optional[int] = BBOX_C,
    triangulate: Optional[bool] = False,
) -> BBox:
    """
    TBD

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    if isinstance(name, str):
        if name.lower() not in PANEL_IDX_BY_NAME.keys():
            ordered = sorted(PANEL_IDX_BY_NAME.keys())
            valid = ", ".join(f"'{kind}'" for kind in ordered[:-1])
            valid = f"{valid} or '{ordered[-1]}'"
            emsg = f"Panel name must be either {valid}, got '{name}'."
            raise ValueError(emsg)
        idx = PANEL_IDX_BY_NAME[name.lower()]
    else:
        idx = name
        if idx not in range(N_PANELS):
            emsg = (
                f"Panel index must be in the closed interval "
                f"[0, {N_PANELS-1}], got '{idx}'."
            )
            raise ValueError(emsg)

    lons, lats = PANEL_BBOX_BY_IDX[idx]

    return BBox(lons, lats, ellps=ellps, radius=radius, c=c, triangulate=triangulate)


def wedge(
    lon1: float,
    lon2: float,
    ellps: Optional[str] = ELLIPSE,
    radius: Optional[float] = 1.0,
    c: Optional[int] = BBOX_C,
    triangulate: Optional[bool] = False,
) -> BBox:
    """
    TBD

    Notes
    -----
    .. versionadded:: 0.1.0

    """
    delta = abs(lon1 - lon2)

    if 0 < delta >= 180:
        emsg = (
            "A geodesic wedge must have an absolute longitudinal difference "
            f"(degrees) in the open interval (0, 180), got '{delta}'."
        )
        raise ValueError(emsg)

    lons = (lon1, lon2, lon2, lon1)
    lats = (90, 90, -90, -90)

    return BBox(lons, lats, ellps=ellps, radius=radius, c=c, triangulate=triangulate)
