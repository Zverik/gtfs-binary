from .helper import GtfsHelper
from .wrapper import IdReference, Itinerary
from zipfile import ZipFile
from typing import TextIO
from . import gtfs_binary_pb2 as g
from collections import defaultdict
from dataclasses import dataclass
from hashlib import md5


@dataclass
class StopData:
    seq_id: int
    stop_id: int
    headsign: str | None
    pickup: g.PickupDropoff
    dropoff: g.PickupDropoff


class Trip:
    def __init__(self, trip_id: str, row: dict[str, str],
                 stops: list[StopData], shape_id: int | None):
        self.trip_id = trip_id
        self.opposite = row.get('direction_id') == '1'
        self.stops = [s.stop_id for s in stops]
        self.shape_id = shape_id
        headsign = row.get('trip_headsign')
        self.headsigns = [s.headsign or headsign for s in stops]
        self.pickup_types = [s.pickup for s in stops]
        self.dropoff_types = [s.dropoff for s in stops]

        # Generate stops key.
        m = md5(usedforsecurity=False)
        if shape_id is not None:
            m.update(shape_id.to_bytes(4))
        for s in stops:
            m.update(s.stop_id.to_bytes(4))
        self.stops_key = m.hexdigest()

    def __hash__(self) -> int:
        return hash(self.stops_key)

    def __eq__(self, other):
        return self.stops_key == other.stops_key


class ItineraryReader:
    def __init__(self, zipfile: ZipFile, ids: IdReference):
        self.z = GtfsHelper(zipfile)
        self.ids = ids
        # trip_id → route_id, itinerary_id
        self.trip_refs: dict[str, tuple[int, int]] = {}

    def prepare(self) -> dict[int, list[Itinerary]]:
        with self.z.open_table('stop_times') as f:
            trip_stops = self.read_trip_stops(f)

        # route_id -> list[Trip]
        trips: dict[int, list[Trip]] = defaultdict(list)
        with self.z.open_table('trips') as f:
            for row, trip_id in self.z.table_reader(f, 'trip_id'):
                stops = trip_stops.get(trip_id)
                if not stops:
                    continue
                shape_id = (None if not row.get('shape_id')
                            else self.ids.shapes[row['shape_id']])
                route_id = self.ids.routes[row['route_id']]
                trips[route_id].append(Trip(trip_id, row, stops, shape_id))

        result: dict[int, list[Itinerary]] = defaultdict(list)
        for route_id, trip_list in trips.items():
            for trip in set(trip_list):
                itin = Itinerary(
                    shape_id=trip.shape_id,
                    stops=trip.stops,
                    headsigns=trip.headsigns,
                    pickup_types=trip.pickup_types,
                    dropoff_types=trip.dropoff_types,
                )

                result[route_id].append(itin)
                for t in trip_list:
                    if t.stops_key == trip.stops_key:
                        self.trip_refs[t.trip_id] = (
                            route_id, len(result[route_id]) - 1)

        return result

    def read_trip_stops(self, fileobj: TextIO) -> dict[str, list[StopData]]:
        trip_stops: dict[str, list[StopData]] = {}  # trip_id -> stop data
        for rows, trip_id in self.z.sequence_reader(
                fileobj, 'trip_id', 'stop_sequence'):
            trip_stops[trip_id] = [StopData(
                seq_id=int(row['stop_sequence']),
                # The stop should be already in the table.
                stop_id=self.ids.stops[row['stop_id']],
                headsign=row.get('stop_headsign'),
                pickup=self.parse_pickup_dropoff(row.get('pickup_type')),
                dropoff=self.parse_pickup_dropoff(row.get('drop_off_type')),
            ) for row in rows]
        return trip_stops

    def parse_pickup_dropoff(self, value: str | None) -> int:
        if not value or value == '0':
            return g.PickupDropoff.PD_YES
        if value == '1':
            return g.PickupDropoff.PD_NO
        if value == '2':
            return g.PickupDropoff.PD_PHONE_AGENCY
        if value == '3':
            return g.PickupDropoff.PD_TELL_DRIVER
        raise ValueError(f'Wrong continous pickup / drop_off value: {value}')

    def cut_last(self, values: list) -> list:
        i = len(values)
        while i > 1 and values[i - 1] == values[i - 2]:
            i -= 1
        return values[:i]
