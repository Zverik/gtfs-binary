import argparse
import struct
import os
import json
import zstandard
import statistics
import random
from typing import BinaryIO
from google.protobuf.message import Message
from . import gtfs_binary_pb2 as g


ARCH = zstandard.ZstdDecompressor()


def prep(f: dict) -> str:
    return json.dumps(
        {k: v for k, v in f.items() if v is not None}, ensure_ascii=False)


def print_footer(f: g.Footer):
    print(prep({
        'version': f.version,
        'date': f.date,
        'original_url': f.original_url,
        'compressed': f.compressed,
    }))
    for b in f.blocks:
        print(prep({
            'block': g.Block.Name(b.block),
            'offset': b.offset,
            'length': b.length,
            'compressed': b.compressed,
        }))


def print_agencies(f: g.Footer):
    for a in f.agencies:
        print(prep({
            'name': a.name,
            'url': a.url,
            'timezone': a.timezone,
            'lang': a.lang,
            'phone': a.phone,
            'fare_url': a.fare_url,
            'email': a.email,
        }))


def list_info(v: list[int], absolute: bool = False) -> dict:
    if len(v) <= 3:
        return {"list": list(v)}

    vv = v if not absolute else [abs(x) for x in v]
    return {
        'sample': list(v) if len(v) <= 10 else random.sample(v, 10),
        'count': len(v),
        'min': min(vv),
        'max': max(vv),
        'sum': sum(vv),
        'average': round(statistics.mean(vv)),
        'median': round(statistics.median(vv)),
        'p90': round(statistics.quantiles(vv, n=10)[-1]),
    }


def print_shape_metadata(s: g.ShapeMetadata):
    print('Shapes: ' + prep({
        'chunk_size': s.chunk_size,
        'chunk_lengths': list_info(s.chunk_lengths),
    }))


def print_stop_metadata(s: g.StopMetadata):
    print('Stops: ' + prep({
        'geohash_xor': s.geohash_xor,
        'geohashes': list_info(s.geohashes),
        'has_stations': s.has_stations,
        'chunk_lengths': list_info(s.chunk_lengths, True),
        'chunk_stop_counts': list_info(s.chunk_stop_counts),
    }))


def print_calendar_metadata(c: g.CalendarMetadata):
    print('Calendar: ' + prep({
        'base_date': c.base_date,
        # ...
        'days_in_months': c.days_in_month,
        'months_lengths': list_info(c.month_lengths, True),
    }))


def print_route_metadata(r: g.RouteMetadata):
    print('Routes: ' + prep({
        'has_wheelchair_info': r.has_wheelchair_info,
        'has_bike_info': r.has_bike_info,
        'route_lengths': list_info(r.route_lengths),
    }))


def read_data(f: BinaryIO, offset: int, length: int,
              compressed: bool = True) -> bytes:
    f.seek(offset)
    data = f.read(length)
    if compressed and length > 0:
        data = ARCH.decompress(data)
    return data


def read_message(f: BinaryIO, message: Message, offset: int, length: int,
                 compressed: bool = True) -> Message:
    message.ParseFromString(read_data(f, offset, length, compressed))
    return message


def read_block(f: BinaryIO, message: Message, block: g.BlockMetadata
               ) -> Message:
    return read_message(f, message, block.offset, block.length,
                        block.compressed)


def main():
    parser = argparse.ArgumentParser(
        description='Inspects a GTFS feed into a binary format')
    parser.add_argument('input', help='Source GTFS Binary file')
    parser.add_argument(
        '-b', '--block',
        help='Block name (agencies/stops/shapes/calendar/routes)')
    options = parser.parse_args()

    f = open(options.input, 'rb')
    if f.read(4) != b'GTB\n':
        print('The header does not match the spec.')
        return

    f.seek(-2, os.SEEK_END)
    footer_len = struct.unpack('>H', f.read(2))[0]
    f.seek(-2-footer_len, os.SEEK_END)
    footer = g.Footer()
    footer.ParseFromString(f.read(footer_len))

    blocks = {b.block: b for b in footer.blocks}
    shapes = read_block(f, g.ShapeMetadata(), blocks[g.Block.B_SHAPES])
    stops = read_block(f, g.StopMetadata(), blocks[g.Block.B_STOPS])
    calendar = read_block(f, g.CalendarMetadata(), blocks[g.Block.B_CALENDAR])
    routes = read_block(f, g.RouteMetadata(), blocks[g.Block.B_ROUTES])

    if not options.block:
        print_footer(footer)
        print_shape_metadata(shapes)
        print_stop_metadata(stops)
        print_calendar_metadata(calendar)
        print_route_metadata(routes)
    elif options.block == 'agencies':
        print_agencies(footer)
    elif options.block == 'shapes':
        # TODO
        print(f'Unsupported block type: {options.block}')
    else:
        print(f'Unsupported block type: {options.block}')


if __name__ == '__main__':
    main()
