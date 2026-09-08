import argparse
import json
from datetime import date
from zipfile import ZipFile
from .helpers import GtfsBinary, readers, Metadata
from .readers import (
    AgencyReader, StopsReader, ShapesReader, CalendarReader,
    RoutesReader, ItineraryReader, TripsReader,
)


def pack(filename: str, output: str, compress: bool = False,
         base_date: str | None = None, follows: str | None = None,
         metadata: dict | None = None):
    if follows:
        with open(follows, 'rb') as f:
            footer = readers.read_footer(f)
        version = footer.date + 1
    else:
        version = int(date.today().strftime('%y%m%d'))
    feed = GtfsBinary(date=version, metadata=None if not metadata
                      else Metadata(metadata))
    with ZipFile(filename, 'r') as z:
        agencies = AgencyReader(z, feed.ids)
        feed.agencies = agencies.prepare()
        stops = StopsReader(z, feed.ids)
        feed.stops = stops.prepare()
        shapes = ShapesReader(z, feed.ids)
        feed.shapes = shapes.prepare()
        calendar = CalendarReader(z, feed.ids, base_date)
        feed.services = calendar.prepare()
        routes = RoutesReader(z, feed.ids)
        feed.routes = routes.prepare()
        itins = ItineraryReader(z, feed.ids)
        feed.itineraries = itins.prepare()
        feed.trip_refs = itins.trip_refs
        trips = TripsReader(z, feed.ids, feed.stops)
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
    parser.add_argument(
        '-m', '--metadata',
        help='JSON-formatted file with a feed metadata')
    options = parser.parse_args()

    if options.metadata:
        with open(options.metadata, 'r') as f:
            meta = json.load(f)
    else:
        meta = None

    pack(options.input, options.output, options.compress, options.base_date,
         options.follows, meta)


if __name__ == '__main__':
    main()
