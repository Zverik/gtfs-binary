from ..helpers import IdReference, Trip, GtfsHelper, g
from typing import TextIO
from zipfile import ZipFile
from dataclasses import dataclass


@dataclass
class StopTime:
    seq_id: int
    departure: int
    approximate: bool
    dist_traveled: float


class TripsReader:
    def __init__(self, zipfile: ZipFile, ids: IdReference):
        self.z = GtfsHelper(zipfile)
        self.ids = ids

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

    def from_stop_times(self, fileobj: TextIO, trips: dict[str, Trip]):
        for rows, trip_id in self.z.sequence_reader(
                fileobj, 'trip_id', 'stop_sequence'):
            if trips[trip_id].departures:
                raise ValueError(f'Trip was already filled: {trip_id}')

            cur_times: list[StopTime] = []
            for row in rows:
                arrival = self.parse_time(row['arrival_time'])
                departure = self.parse_time(row['departure_time']) or arrival
                departure = -1 if departure is None else int(departure / 5)
                dist = float(row.get('dist_traveled', '0'))

                cur_times.append(StopTime(
                    seq_id=int(row['stop_sequence']),
                    departure=departure,
                    approximate=row.get('timepoint') == '0',
                    dist_traveled=dist,
                ))
            cur_times.sort(key=lambda t: t.seq_id)
            if cur_times[0].departure < 0:
                raise ValueError(
                    'Neither arrival nor departure are specified '
                    f'for the first stop in trip {trip_id}')
            trips[trip_id].departures = [t.departure for t in cur_times]
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
