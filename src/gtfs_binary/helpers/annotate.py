import math
import itertools
from .. import gtfs_binary_pb2 as g
from .models import Itinerary, STOP_COORD_SCALE, SHAPE_SCALE


class Point:
    def __init__(self, *, lat: float | None = None, lon: float | None = None,
                 stop: g.StopsChunk | None = None, shape_pt: int | None = None,
                 shape: g.Shape | None = None):
        if lat is not None and lon is not None:
            self.lat = lat
            self.lon = lon
        elif stop:
            self.lat = stop.lat / STOP_COORD_SCALE
            self.lon = stop.lon / STOP_COORD_SCALE
        elif shape_pt is not None and shape:
            self.lat = shape.latitudes[shape_pt] / SHAPE_SCALE
            self.lon = shape.longitudes[shape_pt] / SHAPE_SCALE
        else:
            raise ValueError('No parameters set for a point!')

    def is_same(self, other: Point, eps: float = 1e-8) -> bool:
        return self.distance2(other) < eps

    def distance(self, other) -> float:
        """Returns euclidian distance from self to other."""
        l1 = math.radians(self.lon)
        l2 = math.radians(other.lon)
        f1 = math.radians(self.lat)
        f2 = math.radians(other.lat)
        x = (l2 - l1) * math.cos((f1 + f2) / 2)
        y = f2 - f1
        return math.sqrt(x * x + y * y) * 6371000

    def distance2(self, other: Point) -> float:
        """Returns dx² + dy²."""
        return (math.pow(self.lon - other.lon, 2) +
                math.pow(self.lat - other.lat, 2))

    def bearing(self, other: Point) -> float:
        dx = math.radians(other.lon - self.lon)
        p1y = math.radians(self.lat)
        p2y = math.radians(other.lat)

        x = math.sin(dx) * math.cos(p2y)
        y = (math.cos(p1y) * math.sin(p2y) -
             math.cos(p2y) * math.sin(p1y) * math.cos(dx))

        b = math.atan2(y, x)
        return math.degrees(b)

    def project_on_segment(self, p1: Point, p2: Point) -> Point | None:
        dlon = p2.lon - p1.lon
        dlat = p2.lat - p1.lat

        if abs(dlat) < 1e-8 and abs(dlon) < 1e-8:
            return self

        d = (self.lon - p1.lon) * dlon + (self.lat - p1.lat) * dlat
        t = d / p1.distance2(p2)

        if t < 0 or t > 1:
            return None

        dlon = p2.lon - p1.lon
        dlat = p2.lat - p1.lat
        return Point(lon=p1.lon + t * dlon, lat=p1.lat + t * dlat)


class StopDirections:
    def __init__(self, stops: list[g.StopsChunk],
                 itineraries: dict[int, list[Itinerary]],
                 shapes: list[g.Shape]):
        self.stops = stops
        self.itineraries = itineraries.values()
        self.shapes = shapes

    def stop_bearing(self, stop1: int, stop2: int) -> float:
        return Point(stop=self.stops[stop1]).bearing(
            Point(stop=self.stops[stop2]))

    def stop_direction_from_shape(
            self, stop_id: int, shape_id: int) -> float | None:
        # Project the stop onto the shape.
        shape = self.shapes[shape_id]
        min_dist = 50.0  # meters
        closest_pt: Point | None = None
        closest_idx = -1
        pt = Point(stop=self.stops[stop_id])
        for i in range(1, len(shape.longitudes)):
            proj = pt.project_on_segment(
                Point(shape=shape, shape_pt=i-1),
                Point(shape=shape, shape_pt=i))
            if proj:
                dist = pt.distance(proj)
                if dist < min_dist:
                    min_dist = dist
                    closest_pt = proj
                    closest_idx = i

        # Find the bearing to the next point.
        if closest_pt is None:
            return None

        if closest_pt.is_same(Point(shape=shape, shape_pt=closest_idx)):
            if closest_idx + 1 < len(shape.longitudes):
                return closest_pt.bearing(Point(
                    shape=shape, shape_pt=closest_idx+1))
            else:
                return None
        return closest_pt.bearing(Point(shape=shape, shape_pt=closest_idx))

    def converge_directions(self, directions: list[float]) -> g.Direction:
        if not directions:
            return g.Direction.D_UNKNOWN

        # Direction span should be under 120°
        d_min = min((a + 360) % 360 for a in directions)
        d_max = max((a + 360) % 360 for a in directions)
        if d_max - d_min > 120:
            return g.Direction.D_UNKNOWN

        # Snap the centerline to a cardinal direction.
        d = ((d_min + d_max) / 2) % 360
        if d < 45 or d > 315:
            return g.Direction.D_EAST
        if d < 135:
            return g.Direction.D_NORTH
        if d < 225:
            return g.Direction.D_WEST
        return g.Direction.D_SOUTH

    def detect_stop_direction(self, stop_id: int) -> g.Direction:
        directions: list[float] = []
        for itin in itertools.chain.from_iterable(self.itineraries):
            try:
                idx = itin.stops.index(stop_id)
                # print(f'itin idx {idx} of {len(itin.stops)}')
                d: float | None = None
                if itin.shape_id is not None:
                    d = self.stop_direction_from_shape(stop_id, itin.shape_id)
                    # print(f'from shape: {d}')
                if d is None and idx + 1 < len(itin.stops):
                    d = self.stop_bearing(stop_id, itin.stops[idx + 1])
                    # print(f'to the next stop: {d}')
                if d is not None:
                    directions.append(d)
            except ValueError:
                pass  # no stop in the itinerary

        result = self.converge_directions(directions)
        # print(f'Stop {self.stops[stop_id].name} dir {directions} '
        #       f'result {g.Direction.Name(result)}')
        return result

    def fill_stop_directions(self) -> None:
        for stop_id, stop in enumerate(self.stops):
            stop.direction = self.detect_stop_direction(stop_id)
