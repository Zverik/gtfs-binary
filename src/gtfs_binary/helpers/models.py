import itertools
from datetime import date
from functools import cached_property
from .. import gtfs_binary_pb2 as g

SHAPE_SCALE = 100000
STOP_COORD_SCALE = 100000


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

    @cached_property
    def departure_deltas(self) -> list[int]:
        return [d[1] - d[0] for d in itertools.pairwise(self.departures)]


class Itinerary:
    def __init__(self, shape_id: int | None, stops: list[int],
                 headsigns: list[str],
                 pickup_types: list[g.PickupDropoff],
                 dropoff_types: list[g.PickupDropoff],
                 opposite_direction: bool):
        self.shape_id = shape_id
        self.stops = stops
        self.headsigns = headsigns
        self.pickup_types = pickup_types
        self.dropoff_types = dropoff_types
        self.opposite_direction = opposite_direction
