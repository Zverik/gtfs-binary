import argparse
from datetime import date
from zipfile import ZipFile
from .helpers import GtfsBinary, IdReference
from .readers import (
    AgencyReader, StopsReader, ShapesReader, CalendarReader,
    RoutesReader, ItineraryReader, TripsReader,
)


def main():
    parser = argparse.ArgumentParser(
        description='Compresses a GTFS feed into a binary format')
    parser.add_argument('input', help='Source zipped gtfs file')
    parser.add_argument(
        '-o', '--output', required=True,
        help='Output binary file (use gtb extension)')
    parser.add_argument(
        '-c', '--compress', action='store_true',
        help='Compress blocks with zstd')
    options = parser.parse_args()

    feed = GtfsBinary(date=int(date.today().strftime('%y%m%d')))
    ids = IdReference()
    with ZipFile(options.input, 'r') as z:
        agencies = AgencyReader(z, ids)
        feed.agencies = agencies.prepare()
        stops = StopsReader(z, ids)
        feed.stops = stops.prepare()
        shapes = ShapesReader(z, ids)
        feed.shapes = shapes.prepare()
        calendar = CalendarReader(z, ids)
        feed.services = calendar.prepare()
        routes = RoutesReader(z, ids)
        feed.routes = routes.prepare()
        itins = ItineraryReader(z, ids)
        feed.itineraries = itins.prepare()
        feed.trip_refs = itins.trip_refs
        trips = TripsReader(z, ids)
        feed.trips = trips.prepare()

    with open(options.output, 'wb') as f:
        feed.write(f, compress=options.compress)


if __name__ == '__main__':
    main()
