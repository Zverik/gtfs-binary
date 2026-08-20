from ..helpers import GtfsHelper, IdReference, g
from zipfile import ZipFile


COORD_SCALE = 100000


class StopsReader:
    def __init__(self, zipfile: ZipFile, ids: IdReference):
        self.z = GtfsHelper(zipfile)
        self.ids = ids
        self.stops: list[g.StopsChunk] = []
        self.geohash_xor = 0

    def prepare(self) -> list[g.StopsChunk]:
        stops: dict[str, g.StopsChunk] = {}
        parents: dict[str, str] = {}
        with self.z.open_table('stops') as f:
            for row, stop_id in self.z.table_reader(f, 'stop_id'):
                parent_id = row.get('parent_station')
                if parent_id:
                    parents[stop_id] = parent_id
                loc_type = row.get('location_type', '')
                if loc_type and int(loc_type) > 1:
                    continue
                stop = g.StopsChunk(
                    gtfs_id=stop_id,
                    code=row.get('stop_code') or None,
                    desc=row.get('stop_desc') or None,
                    name=row['stop_name'],
                    lat=round(float(row['stop_lat']) * COORD_SCALE),
                    lon=round(float(row['stop_lon']) * COORD_SCALE),
                    wheelchair=parse_accessibility(
                        row.get('wheelchair_boarding')),
                    is_station=loc_type == '1',
                    # route_ids to be filled after reading routes
                )
                # Precision 22 is equivalent to tiles at zoom 12.
                # 24 is for 13.
                stop.geohash = geohash(
                    float(stop.lat) / COORD_SCALE,
                    float(stop.lon) / COORD_SCALE, 24)
                stops[stop_id] = stop

        # Set the same geohash for children as for the parent.
        for stop_id, parent_id in parents.items():
            stops[stop_id].geohash = stops[parent_id].geohash

        # Every geohash except the first is XOR-ed with the first.
        result = list(stops.items())
        self.geohash_xor = result[0][1].geohash
        for t in result:
            t[1].geohash ^= self.geohash_xor
        result.sort(key=lambda t: t[1].geohash)
        result[0][1].geohash ^= self.geohash_xor

        self.ids.stops = {s[0]: i for i, s in enumerate(result)}

        # Set parent ids, because only now we know their numeric values.
        for stop_id, stop in result:
            if stop_id in parents:
                stop.parent_id = self.ids.stops[stop_id]

        # Redirect boarding points and entrances to parent stations.
        for stop_id, parent_id in parents.items():
            if stop_id not in self.ids.stops:
                self.ids.stops[stop_id] = self.ids.stops[parent_id]

        self.stops = [s[1] for s in result]
        return self.stops


def parse_accessibility(value: str | None) -> int:
    if not value:
        return 0
    if value == '0':
        return g.Accessibility.A_UNKNOWN
    if value == '1':
        return g.Accessibility.A_SOME
    if value == '2':
        return g.Accessibility.A_NO
    raise ValueError(f'Unknown accessibility value for a stop: {value}')


def geohash(lat: float, lon: float, precision: int = 22) -> int:
    if lat < -90 or lat > 90:
        raise ValueError(f'Latitude is out of bounds: {lat}')
    while lon < -180:
        lon += 180
    while lon > 180:
        lon -= 180

    min_lat = -90.0
    max_lat = 90.0
    min_lon = -180.0
    max_lon = 180.0

    result = 0
    for i in range(precision):
        result <<= 1
        if i & 1 == 0:
            mid_lon = (min_lon + max_lon) / 2
            if lon >= mid_lon:
                result |= 1
                min_lon = mid_lon
            else:
                max_lon = mid_lon
        else:
            mid_lat = (min_lat + max_lat) / 2
            if lat >= mid_lat:
                result |= 1
                min_lat = mid_lat
            else:
                max_lat = mid_lat
    return result
