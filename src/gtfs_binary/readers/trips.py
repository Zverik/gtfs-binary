from ..helpers import IdReference, Trip, GtfsHelper, g
from typing import TextIO
from zipfile import ZipFile
from dataclasses import dataclass
from math import sqrt


@dataclass
class StopTime:
    stop_id: int
    seq_id: int
    departure: int | None
    approximate: bool
    dist: float

    @property
    def departure_guard(self) -> int:
        if self.departure is None:
            raise ValueError(
                f'Departure is none for stop_id {self.stop_id}, '
                f'seq_id {self.seq_id}')
        return self.departure


class TripsReader:
    def __init__(self, zipfile: ZipFile, ids: IdReference,
                 stops: list[g.StopsChunk]):
        self.z = GtfsHelper(zipfile)
        self.ids = ids
        self.stops = stops

    def prepare(self) -> dict[str, Trip]:
        trips: dict[str, Trip] = {}
        with self.z.open_table('trips') as f:
            for row, trip_id in self.z.table_reader(f, 'trip_id'):
                trips[trip_id] = Trip(
                    service_id=self.ids.services[row['service_id']],
                    departures=[],
                    wheelchair=self.parse_accessibility(
                        row.get('wheelchair_accessible')),
                    bikes=self.parse_accessibility(row.get('bikes_allowed')),
                )

        with self.z.open_table('stop_times') as f:
            self.from_stop_times(f, trips)
        if self.z.has_file('frequencies'):
            with self.z.open_table('frequencies') as f:
                self.from_frequencies(f, trips)

        return trips

    def calculate_missing_departures(
            self, trip_id: str, times: list[StopTime]):
        """
        Fills in the missing departure times. Uses stop locations,
        trip distances and existing departure times to do that.
        Throws an exception when it cannot.
        Modifies the [times] parameter in-place.
        """
        if times[0].departure is None or times[-1].departure is None:
            raise ValueError(
                'Neither arrival nor departure are specified '
                f'for the first stop in trip {trip_id}')

        def stop_dist(stop1: g.StopsChunk, stop2: g.StopsChunk) -> float:
            dlat = stop2.lat - stop1.lat
            dlon = stop2.lon - stop1.lon
            return sqrt(dlat * dlat + dlon * dlon)

        last_ok = 0
        i = 1
        while i < len(times):
            if times[i].departure is not None:
                last_ok = i
                i += 1
            else:
                next_ok = i + 1
                while times[next_ok].departure is None:
                    next_ok += 1

                if not all(t.dist >= 0 for t in times[last_ok:next_ok+1]):
                    # Fill distances from stop locations.
                    times[last_ok].dist = 0
                    for i in range(last_ok + 1, next_ok + 1):
                        stop1 = self.stops[times[i - 1].stop_id]
                        stop2 = self.stops[times[i].stop_id]
                        times[i].dist = (
                            times[i-1].dist + stop_dist(stop1, stop2))

                first_dep = times[last_ok].departure_guard
                diff = times[next_ok].departure_guard - first_dep
                first_dist = times[last_ok].dist
                # Supporting decreasing distances.
                total_dist = abs(times[next_ok].dist - first_dist)
                for i in range(last_ok + 1, next_ok):
                    times[i].departure = first_dep + round(
                        diff * abs(times[i].dist - first_dist) / total_dist)
                i = next_ok + 1

    def from_stop_times(self, fileobj: TextIO, trips: dict[str, Trip]):
        for rows, trip_id in self.z.sequence_reader(
                fileobj, 'trip_id', 'stop_sequence'):
            if trips[trip_id].departures:
                raise ValueError(f'Trip was already filled: {trip_id}')

            cur_times: list[StopTime] = []
            for row in rows:
                arrival = self.parse_time(row['arrival_time'])
                departure = self.parse_time(row['departure_time']) or arrival
                departure = None if departure is None else int(departure / 5)
                dist = float(row.get('dist_traveled', '-1'))

                cur_times.append(StopTime(
                    stop_id=self.ids.stops[row['stop_id']],
                    seq_id=int(row['stop_sequence']),
                    departure=departure,
                    approximate=row.get('timepoint') == '0',
                    dist=dist,
                ))
            cur_times.sort(key=lambda t: t.seq_id)
            self.calculate_missing_departures(trip_id, cur_times)
            trips[trip_id].departures = [t.departure_guard for t in cur_times]
            trips[trip_id].approximate = any(t.approximate for t in cur_times)

    def from_frequencies(self, fileobj: TextIO, trips: dict[str, Trip]):
        for row, trip_id in self.z.table_reader(fileobj, 'trip_id'):
            trip = trips[trip_id]  # assuming it's there
            start = self.parse_time(row['start_time']) or 0
            end = self.parse_time(row['end_time']) or 0
            # Offset all departures so they start at start_time.
            start_diff = int(start / 5) - trip.departures[0]
            trip.departures = [d + start_diff for d in trip.departures]
            trip.end_time = int((end + 4) / 5)
            trip.interval = int(row['headway_secs'])
            trip.approximate = row.get('exact_times') != '1'

    def parse_time(self, tim: str) -> int | None:
        tim = tim.strip()
        if not tim:
            return None
        if len(tim) == 7:
            tim = '0' + tim
        if len(tim) != 8:
            raise ValueError(f'Wrong time value: {tim}')
        return int(tim[:2]) * 3600 + int(tim[3:5]) * 60 + int(tim[6:])

    def parse_accessibility(self, value: str | None) -> int:
        if not value or value == '0':
            return g.Accessibility.A_UNKNOWN
        if value == '1':
            return g.Accessibility.A_SOME
        if value == '2':
            return g.Accessibility.A_NO
        raise ValueError(f'Unknown accessibility value for a trip: {value}')
