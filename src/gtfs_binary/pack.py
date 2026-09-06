import argparse
from datetime import date
from zipfile import ZipFile
from .helpers import GtfsBinary, IdReference, readers
from .readers import (
    AgencyReader, StopsReader, ShapesReader, CalendarReader,
    RoutesReader, ItineraryReader, TripsReader,
)


def pack(filename: str, output: str, compress: bool = False,
         base_date: str | None = None, follows: str | None = None):
    if follows:
        with open(follows, 'rb') as f:
            footer = readers.read_footer(f)
        version = footer.date + 1
    else:
        version = int(date.today().strftime('%y%m%d'))
    feed = GtfsBinary(date=version)
    ids = IdReference()
    with ZipFile(filename, 'r') as z:
        agencies = AgencyReader(z, ids)
        feed.agencies = agencies.prepare()
        stops = StopsReader(z, ids)
        feed.stops = stops.prepare()
        shapes = ShapesReader(z, ids)
        feed.shapes = shapes.prepare()
        calendar = CalendarReader(z, ids, base_date)
        feed.services = calendar.prepare()
        routes = RoutesReader(z, ids)
        feed.routes = routes.prepare()
        itins = ItineraryReader(z, ids)
        feed.itineraries = itins.prepare()
        feed.trip_refs = itins.trip_refs
        trips = TripsReader(z, ids, feed.stops)
        feed.trips = trips.prepare()

    with open(output, 'wb') as f:
        feed.write(f, compress=compress)


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
    parser.add_argument(
        '--base-date', help='Base date as YYYY-MM-DD (only for testing)')
    parser.add_argument(
        '-f', '--follows',
        help='A feed from which to take a version and increment by one')
    options = parser.parse_args()
    pack(options.input, options.output, options.compress, options.base_date,
         options.follows)


if __name__ == '__main__':
    main()
