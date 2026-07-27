import itertools
import zstandard
import struct
from math import ceil
from typing import BinaryIO
from datetime import date, timedelta
from collections import defaultdict
from statistics import mode
from .. import gtfs_binary_pb2 as g
from . import encoding as e
from .trie import Trie, pack_trie


class CalendarService:
    def __init__(self, start_date: date, end_date: date,
                 weekdays: list[bool]) -> None:
        self.start_date = start_date
        self.end_date = end_date
        self.weekdays = weekdays
        self.including_days: list[date] = []
        self.except_days: list[date] = []


class Trip:
    def __init__(self, service_id: int,
                 departures: list[int], end_time: int = 0,
                 interval: int = 0, approximate: bool = False,
                 wheelchair: g.Accessibility = g.Accessibility.A_UNKNOWN,
                 bikes: g.Accessibility = g.Accessibility.A_UNKNOWN) -> None:
        self.service_id = service_id
        self.approximate = approximate
        self.departures = departures
        self.end_time = end_time
        self.interval = end_time
        self.wheelchair = wheelchair
        self.bikes = bikes


class Itinerary:
    def __init__(self, shape_id: int | None, stops: list[int],
                 headsigns: list[str],
                 pickup_types: list[g.PickupDropoff],
                 dropoff_types: list[g.PickupDropoff]):
        self.shape_id = shape_id
        self.stops = stops
        self.headsigns = headsigns
        self.pickup_types = pickup_types
        self.dropoff_types = dropoff_types


class IdReference:
    def __init__(self) -> None:
        self.agencies: dict[str, int] = {}
        self.stops: dict[str, int] = {}
        self.shapes: dict[str, int] = {}
        self.routes: dict[str, int] = {}
        self.services: dict[str, int] = {}


class GtfsBinary:
    def __init__(self, date: int, original_url: str | None = None):
        self.date = date
        self.original_url = original_url
        self.agencies: list[g.Agency] = []
        self.shapes: list[g.Shape] = []
        # Expected to be sorted by geohash.
        self.stops: list[g.StopsChunk] = []
        # Expected to be sorted by start_date.
        self.services: list[CalendarService] = []
        self.routes: list[g.Route] = []
        # route_id → list of itineraries.
        self.itineraries: dict[int, list[Itinerary]] = {}
        # trip_id → route_id, itinerary_id
        self.trip_refs: dict[str, tuple[int, int]] = {}
        # trip_id → trip data
        self.trips: dict[str, Trip] = {}
        self.compressed = True
        self.arch = zstandard.ZstdCompressor(level=10)

    def write(self, fileobj: BinaryIO, compress: bool = True):
        pos = 4
        blocks: list[g.BlockMetadata] = []

        def write_block(metadata: bytes, data: bytes, block: g.Block) -> None:
            nonlocal pos, blocks
            compr = self.compress_if_better(metadata)
            fileobj.write(compr[1])
            fileobj.write(data)
            blocks.append(g.BlockMetadata(
                block=block,
                offset=pos,
                length=len(compr[1]),
                compressed=compr[0],
            ))
            pos += len(compr[1]) + len(data)

        fileobj.write(b'GTB\n')
        self.compressed = compress
        write_block(*self.pack_shapes(), g.Block.B_SHAPES)
        write_block(*self.pack_stops(), g.Block.B_STOPS)
        write_block(*self.pack_calendar(), g.Block.B_CALENDAR)
        write_block(*self.pack_routes(), g.Block.B_ROUTES)
        footer = g.Footer(
            version=1,
            date=self.date,
            original_url=self.original_url,
            compressed=compress,
            agencies=self.agencies,
            blocks=blocks,
        ).SerializeToString()
        fileobj.write(footer)
        fileobj.write(struct.pack('>H', len(footer)))

    def compress(self, chunk: bytes) -> bytes:
        if not self.compressed:
            return chunk
        return self.arch.compress(chunk)

    def compress_if_better(self, chunk: bytes) -> tuple[bool, bytes]:
        if not self.compressed:
            return False, chunk
        cmp = self.arch.compress(chunk)
        if len(cmp) < len(chunk):
            return True, cmp
        return False, chunk

    def pack_shapes(self, chunk_size: int = 10) -> tuple[bytes, bytes]:
        chunks: list[bytes] = []
        for shapes in itertools.batched(self.shapes, chunk_size):
            chunk = g.ShapeChunk(shapes=shapes)
            last_coord = (0, 0)
            for shape in chunk.shapes:
                # new_last = (shape.latitudes[-1], shape.longitudes[-1])
                for i in range(len(shape.latitudes) - 1, -1, -1):
                    shape.latitudes[i] -= (last_coord[0] if i == 0
                                           else shape.latitudes[i-1])
                    shape.longitudes[i] -= (last_coord[1] if i == 0
                                            else shape.longitudes[i-1])
                # last_coord = new_last
            chunks.append(self.compress(chunk.SerializeToString()))
        metadata = g.ShapeMetadata(
            chunk_size=chunk_size,
            chunk_lengths=[len(c) for c in chunks])
        return metadata.SerializeToString(), b''.join(chunks)

    def pack_stops(self) -> tuple[bytes, bytes]:
        has_stations = any(s.parent_id for s in self.stops)
        routes_by_stops = self.routes_by_stops()
        # TODO: normalize unicode
        trie = Trie([s.name.lower() for s in self.stops])

        chunks: list[tuple[bool, bytes]] = []
        geohash_xor = self.stops[0].geohash
        geohashes: list[int] = []
        stop_counts: list[int] = []
        last_geohash = 0
        first_id = 0
        for geohash, ichunk in itertools.groupby(
                self.stops, lambda s: s.geohash):
            if geohash == geohash_xor:
                geohash = 0
            lchunk = list(ichunk)
            batch_size = ceil(len(lchunk) / ceil(len(lchunk) / 50))
            for subchunk in itertools.batched(lchunk, batch_size):
                chunk = list(subchunk)
                geohashes.append(geohash - last_geohash)
                stop_counts.append(len(chunk))
                chunks.append(self.compress_if_better(self.pack_stop_chunk(
                    chunk, has_stations, first_id, routes_by_stops)))
                last_geohash = geohash
                first_id += len(chunk)

        metadata = g.StopMetadata(
            geohash_xor=geohash_xor,
            geohashes=geohashes,
            chunk_lengths=[len(c[1]) * (1 if c[0] else -1) for c in chunks],
            chunk_stop_counts=stop_counts,
            has_stations=has_stations,
            name_lookup=pack_trie(trie),
        )
        return metadata.SerializeToString(), b''.join(c[1] for c in chunks)

    def pack_stop_chunk(self, stops: list[g.StopsChunk], stations: bool,
                        first_id: int, routes_by_stops: dict[int, list[int]],
                        ) -> bytes:
        result = b''
        result += e.pack_strings([s.gtfs_id for s in stops])
        result += e.pack_strings([s.code for s in stops])
        result += e.pack_strings([s.name for s in stops])
        result += e.pack_strings([s.desc for s in stops])
        result += e.pack_sints_delta([s.lat for s in stops])
        result += e.pack_sints_delta([s.lon for s in stops])
        result += e.pack_2bit([s.wheelchair for s in stops])
        for i, s in enumerate(stops, first_id):
            result += e.pack_uints_delta(
                routes_by_stops.get(i, []), add_len=True)
        if stations:
            result += e.pack_1bit([s.is_station for s in stops])
            result += e.pack_uints_rle([s.parent_id + 1 for s in stops])
        return result

    def routes_by_stops(self) -> dict[int, list[int]]:
        result: dict[int, set[int]] = defaultdict(set)
        for route_id, itins in self.itineraries.items():
            for i in itins:
                for s in i.stops:
                    result[s].add(route_id)

        return {s: list(sorted(r)) for s, r in result.items()}

    def pack_calendar(self) -> tuple[bytes, bytes]:
        base_date = self.services[0].start_date
        start_dates = [0] + [
            (b.start_date - a.start_date).days
            for a, b in itertools.pairwise(self.services)
        ]
        end_dates = [(s.end_date - s.start_date).days
                     for s in self.services]

        days_in_month, months = self.pack_calendar_months(base_date)
        cmonths = [self.compress_if_better(m.SerializeToString())
                   for m in months]

        metadata = g.CalendarMetadata(
            base_date=int(base_date.strftime('%y%m%d')),
            start_dates=start_dates,
            end_dates=end_dates,
            weekdays=[e.pack_1bit_to_uint(s.weekdays) for s in self.services],
            days_in_month=days_in_month,
            month_lengths=[len(m[1]) * (1 if m[0] else -1) for m in cmonths],
        )
        return metadata.SerializeToString(), b''.join(m[1] for m in cmonths)

    def delta_encode(self, values: list[int]) -> list[int]:
        if len(values) < 2:
            return values
        s = sorted(values)
        return [s[0]] + [b - a for a, b in itertools.pairwise(s)]

    def pack_calendar_months(self, base_date: date
                             ) -> tuple[int, list[g.CalendarMonth]]:
        """Returns (days_in_month, list of months)."""
        # Pack services into CalendarDates for every date.
        days = defaultdict[date, g.CalendarDate](g.CalendarDate)
        for service_id, s in enumerate(self.services):
            for d in s.including_days:
                if d >= base_date:
                    days[d].included_in.append(service_id)
            for d in s.except_days:
                if d >= base_date:
                    days[d].exception_in.append(service_id)

        # Delta-encode services in days.
        for day in days.values():
            incl = self.delta_encode(day.included_in)
            day.included_in.clear()
            day.included_in.extend(incl)
            excl = self.delta_encode(day.exception_in)
            day.exception_in.clear()
            day.exception_in.extend(excl)

        # Determine the days_in_month so that months are not too big.
        last_day = max(days.keys())
        days_list = [base_date + timedelta(d) for d in
                     range((last_day - base_date).days + 1)]
        day_sizes = [len(days[d].included_in) + len(days[d].exception_in)
                     for d in days_list]
        days_in_month = self.calculate_days_in_month(day_sizes)

        # Sort days into months.
        months: list[g.CalendarMonth] = []
        for days_chunk in itertools.batched(days_list, days_in_month):
            listed_dates = [d for d in days_chunk
                            if days[d].included_in or days[d].exception_in]
            if not listed_dates:
                months.append(g.CalendarMonth())
            else:
                date_offsets = (
                    [(listed_dates[0] - days_chunk[0]).days] +
                    [(b - a).days for a, b in itertools.pairwise(listed_dates)]
                )
                while len(date_offsets) > 0 and date_offsets[-1] == 1:
                    del date_offsets[-1]
                if date_offsets == [0]:
                    date_offsets = []

                months.append(g.CalendarMonth(
                    date_offsets=date_offsets,
                    dates=[days[d] for d in listed_dates],
                ))
        return days_in_month, months

    def calculate_days_in_month(self, days: list[int]) -> int:
        MAX_SERVICES_IN_MONTH = 2000
        MAX_DAYS_IN_MONTH = 30

        def fits(m: int) -> bool:
            for batch in itertools.batched(days, m):
                if any(d > MAX_SERVICES_IN_MONTH for d in batch):
                    return False
            return True

        low_bound = 2
        high_bound = MAX_DAYS_IN_MONTH
        if fits(high_bound):
            return high_bound
        if not fits(low_bound):
            return low_bound

        while low_bound < high_bound:
            mid = (low_bound + high_bound) // 2
            if fits(mid):
                # assuming for low + 1 == high, mid = low
                high_bound = mid
            else:
                low_bound = mid + 1

        return low_bound

    def pack_routes(self) -> tuple[bytes, bytes]:
        chunks: list[bytes] = []
        has_wheelchair = any(t.wheelchair != g.Accessibility.A_UNKNOWN
                             for t in self.trips.values())
        has_bike = any(t.bikes != g.Accessibility.A_UNKNOWN
                       for t in self.trips.values())
        # route_id → itinerary_id → list of (trip_id, trip)
        trip_index: dict[int, dict[int, list[tuple[str, Trip]]]] = (
            defaultdict(lambda: defaultdict(list)))
        for trip_id, route_itin in self.trip_refs.items():
            trip_index[route_itin[0]][route_itin[1]].append(
                (trip_id, self.trips[trip_id]))

        for route_id, route in enumerate(self.routes):
            if route_id not in self.itineraries:
                continue

            route_trips = trip_index[route_id]
            route.has_frequencies = False
            for itrips in route_trips.values():
                if any(t[1].interval for t in itrips):
                    route.has_frequencies = True
                    break

            for itin_id, itin in enumerate(self.itineraries[route_id]):
                trips = route_trips[itin_id]
                trips.sort(key=lambda t: t[1].departures[0])
                common_deltas = self.calculate_medians(
                    [t[1].departures for t in trips])

                trips_chunk = self.pack_trips_chunk(
                    trips, route.has_frequencies, has_wheelchair,
                    has_bike, common_deltas)

                route.itineraries.append(g.Itinerary(
                    shape_id=itin.shape_id,
                    stops=itin.stops,
                    headsigns=e.pack_strings_rle(itin.headsigns),
                    pickup_types=e.pack_2bit(itin.pickup_types),
                    dropoff_types=e.pack_2bit(itin.dropoff_types),
                    departure_deltas=common_deltas,
                    service_ids=e.pack_uints_rle(
                        [t[1].service_id for t in trips]),
                    trips=self.compress(trips_chunk),
                ))
            chunks.append(self.compress(route.SerializeToString()))

        metadata = g.RouteMetadata(
            route_lengths=[len(c) for c in chunks],
            has_wheelchair_info=has_wheelchair,
            has_bike_info=has_bike,
        )
        return metadata.SerializeToString(), b''.join(chunks)

    def calculate_medians(self, deltas: list[list[int]]) -> list[int]:
        result: list[int] = []
        for i in range(1, len(deltas[0])):
            result.append(mode(d[i] - d[i-1] for d in deltas))
        return result

    def pack_trips_chunk(self, trips: list[tuple[str, Trip]],
                         has_frequencies: bool,
                         has_wheelchair: bool, has_bikes: bool,
                         common_deltas: list[int]) -> bytes:
        result = b''
        result += e.pack_uints_delta([t[1].departures[0] for t in trips])
        all_deltas: list[int] = []
        for t in trips:
            all_deltas += [
                p[1] - p[0] - common_deltas[i]
                for i, p in enumerate(itertools.pairwise(t[1].departures))
            ]
        result += e.pack_sints_delta(all_deltas)

        result += e.pack_strings([t[0] for t in trips])
        result += e.pack_1bit([t[1].approximate for t in trips])

        if has_frequencies:
            result += e.pack_uints([
                0 if not t[1].interval else
                t[1].end_time - t[1].departures[0] for t in trips])
            result += e.pack_uints([t[1].interval for t in trips])

        if has_wheelchair:
            result += e.pack_2bit([t[1].wheelchair for t in trips])
        if has_bikes:
            result += e.pack_2bit([t[1].bikes for t in trips])
        return result
