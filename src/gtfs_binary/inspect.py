import argparse
import struct
import os
import json
import zstandard
import statistics
import random
from datetime import date, timedelta
from functools import reduce
from typing import BinaryIO, Any
from google.protobuf.message import Message
from .helpers import decoding as dec, PackedTrie, g


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


def print_agencies(f: g.Agencies):
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


def list_info(v: list[int], absolute: bool = False, sample: bool = True
              ) -> dict[str, Any]:
    if len(v) <= 3:
        return {"list": list(v)}

    vv = v if not absolute else [abs(x) for x in v]
    k = 'start' if len(v) <= 10 or not sample else 'sample'
    return {
        k: (list(v)[:10] if len(v) <= 10 or not sample
            else random.sample(v, 10)),
        'count': len(v),
        'min': min(vv),
        'max': max(vv),
        'sum': sum(vv),
        'average': round(statistics.mean(vv)),
        'median': round(statistics.median(vv)),
        'p90': round(statistics.quantiles(vv, n=10)[-1]),
    }


def trie_info(t: g.StopLookup) -> dict[str, int]:
    return {
        'string_len': len(t.string_blob),
        'ids_count': len(t.stop_ids),
        'nodes_count': len(t.node_edge_offset),
        'edges_count': len(t.edge_label_offset),
    }


def print_shape_metadata(s: g.ShapeMetadata):
    print('Shapes: ' + prep({
        'chunk_size': s.chunk_size,
        'chunk_lengths': list_info(s.chunk_lengths),
    }))


def print_shape(f: BinaryIO, compressed: bool, block: g.BlockMetadata,
                s: g.ShapeMetadata, shape_id: int | None = None):
    if len(s.chunk_lengths) == 0:
        return
    if shape_id is None:
        shape_id = random.randrange(s.chunk_size * len(s.chunk_lengths))
    shape_chunk = shape_id // s.chunk_size
    offset = block.offset + block.length + sum(
        c for c in s.chunk_lengths[:shape_chunk])
    print(f'Shape {shape_id} in chunk {shape_chunk}, offset {offset}')
    chunk = read_message(
        f, g.ShapeChunk(), offset, s.chunk_lengths[shape_chunk], compressed)
    shape = chunk.shapes[shape_id - shape_chunk * s.chunk_size]
    print('Latitudes: ' + prep(list_info(shape.latitudes, sample=False)))
    print('Longitudes: ' + prep(list_info(shape.longitudes, sample=False)))


def print_stop_metadata(s: g.StopMetadata):
    print('Stops: ' + prep({
        'has_stations': s.has_stations,
        'chunk_lengths': list_info(s.chunk_lengths, True),
        'chunk_stop_counts': list_info(s.chunk_stop_counts),
    }))


def print_stop(f: BinaryIO, block: g.BlockMetadata, s: g.StopMetadata,
               stop_id: int | None = None):
    if stop_id is None:
        stop_id = random.randrange(sum(s.chunk_stop_counts))
        print(prep({
            'geohash_xor': s.geohash_xor,
            'geohashes': list_info(s.geohashes),
            'has_stations': s.has_stations,
            'chunk_lengths': list_info(s.chunk_lengths, True),
            'chunk_stop_counts': list_info(s.chunk_stop_counts),
        }))

    stop_chunk = 0
    chunk_first_stop_id = 0
    for i, ch in enumerate(s.chunk_stop_counts):
        if chunk_first_stop_id + ch > stop_id:
            stop_chunk = i
            break
        chunk_first_stop_id += ch
    offset = block.offset + block.length + sum(
        abs(c) for c in s.chunk_lengths[:stop_chunk])
    print(f'Stop {stop_id} in chunk {stop_chunk}, offset {offset}')
    chunk = read_data(f, offset, abs(s.chunk_lengths[stop_chunk]),
                      s.chunk_lengths[stop_chunk] > 0)
    chunk_len = s.chunk_stop_counts[stop_chunk]
    d = stop_id - chunk_first_stop_id

    info: dict[str, Any] = {}
    values: list[Any] = []
    values, pos = dec.unpack_strings(chunk, 0, chunk_len)
    info['gtfs_id'] = values[d]
    values, pos = dec.unpack_strings(chunk, pos, chunk_len)
    info['code'] = values[d]
    values, pos = dec.unpack_strings(chunk, pos, chunk_len)
    info['name'] = values[d]
    values, pos = dec.unpack_strings(chunk, pos, chunk_len)
    info['desc'] = values[d]
    values, pos = dec.unpack_sints_delta(chunk, pos, chunk_len)
    info['lat'] = values[d] / 100000
    values, pos = dec.unpack_sints_delta(chunk, pos, chunk_len)
    info['lon'] = values[d] / 100000
    values, pos = dec.unpack_2bit(chunk, pos, chunk_len)
    info['wheelchair'] = g.Accessibility.Name(values[d])
    for i in range(chunk_len):
        route_ids, pos = dec.unpack_uints_delta(chunk, pos, -1)
        if i == d:
            info['route_ids'] = route_ids
    if s.has_stations:
        values, pos = dec.unpack_1bit(chunk, pos, chunk_len)
        info['is_station'] = values[d]
        values, pos = dec.unpack_uints_rle(chunk, pos, chunk_len)
        info['parent_id'] = None if values[d] == 0 else values[d] - 1
    print(prep(info))


def print_lookup_metadata(meta: g.LookupMetadata):
    print('Lookup: ' + prep({
        'stop_by_name': trie_info(meta.stop_by_name),
        'stop_by_gtfs_id': trie_info(meta.stop_by_gtfs_id),
        'route_by_gtfs_id': trie_info(meta.route_by_gtfs_id),
    }))


def print_lookup(f: BinaryIO, meta: g.LookupMetadata,
                 query: str,
                 stop_block: g.BlockMetadata,
                 stop_meta: g.StopMetadata):
    if not query:
        print_lookup_metadata(meta)
    else:
        p = PackedTrie(meta.stop_by_name)
        stop_ids = p.find(query)
        if not stop_ids:
            print('Nothing was found')
        else:
            for stop_id in stop_ids:
                print_stop(f, stop_block, stop_meta, stop_id)


def print_calendar_metadata(c: g.CalendarMetadata):
    print('Calendar: ' + prep({
        'base_date': c.base_date,
        'days_in_month': c.days_in_month,
        'months_lengths': list_info(c.month_lengths, True),
    }))


def print_calendar(f: BinaryIO, compressed: bool, block: g.BlockMetadata,
                   c: g.CalendarMetadata, service_id: int | None = None):
    if service_id is None:
        service_id = random.randrange(len(c.start_dates))
        print(prep({
            'base_date': c.base_date,
            'start_dates': list_info(c.start_dates),
            'end_dates': list_info(c.end_dates),
            'weekdays': list_info(c.weekdays),
            'days_in_month': c.days_in_month,
            'months_lengths': list_info(c.month_lengths, True),
        }))

    base_date = date(
        2000 + c.base_date // 10000, (c.base_date // 100) % 100,
        c.base_date % 100)

    start_date = reduce(lambda a, b: a + b, c.start_dates[:service_id])
    print(prep({
        'service_id': service_id,
        'start_date': (base_date + timedelta(start_date)).strftime('%Y-%m-%d'),
        'end_date': (base_date + timedelta(
            start_date + c.end_dates[service_id])).strftime('%Y-%m-%d'),
        'weekdays': bin(c.weekdays[service_id]),
    }))

    today = date.today() + timedelta(days=30)
    today_month = (today - base_date).days // c.days_in_month
    if today_month >= len(c.month_lengths):
        if len(c.month_lengths) == 1:
            today = base_date
            today_month = 0
        else:
            today = base_date + timedelta(days=c.days_in_month)
            today_month = 1
    offset = block.offset + block.length + sum(
        c for c in c.month_lengths[:today_month])
    print(f'Day {today.strftime('%Y-%m-%d')} in month {today_month}, '
          f'offset {offset}')
    month = read_message(
        f, g.CalendarMonth(), offset, c.month_lengths[today_month], compressed)
    info = {
        'date_offsets': list(month.date_offsets),
        'included_in': {},
        'exception_in': {},
    }

    current_date = base_date + timedelta(days=today_month * c.days_in_month)
    for i, cdate in enumerate(month.dates):
        if i == 0:
            skip = 0
        elif i < len(month.date_offsets):
            skip = month.date_offsets[i]
        else:
            skip = 1

        current_date += timedelta(days=skip)
        if current_date == today:
            info['included_in'] = list_info(cdate.included_in)
            info['exception_in'] = list_info(cdate.exception_in)
        if current_date >= today:
            break

    print(prep(info))


def print_route_metadata(r: g.RouteMetadata):
    print('Routes: ' + prep({
        'has_wheelchair_info': r.has_wheelchair_info,
        'has_bike_info': r.has_bike_info,
        'route_lengths': list_info(r.route_lengths),
    }))


def int_to_time(value: int) -> str:
    hour = value // 3600
    minute = (value // 60) % 60
    second = value % 60
    return f'{hour:02d}:{minute:02d}:{second:02d}'


def print_route(f: BinaryIO, compressed: bool, block: g.BlockMetadata,
                r: g.RouteMetadata, route_id: int | None = None):
    if route_id is None:
        route_id = random.randrange(len(r.route_lengths))
    offset = block.offset + block.length + sum(
        c for c in r.route_lengths[:route_id])
    route = read_message(
        f, g.Route(), offset, r.route_lengths[route_id], compressed)
    print(prep({
        'route_id': route_id,
        'gtfs_id': route.gtfs_id,
        'agency_id': route.agency_id,
        'short_name': route.short_name,
        'long_name': route.long_name,
        'type': g.RouteType.Name(route.type),
        'desc': route.desc or None,
        'color': hex(route.color),
        'text_color': hex(route.text_color),
        'has_frequencies': route.has_frequencies,
        'headsigns_start': list(route.headsigns)[:10],
    }))
    for itin in route.itineraries:
        print()
        stop_count = len(itin.stop_ids)
        print(prep({
            'shape_id': itin.shape_id,
            'stop_ids': list(itin.stop_ids),
            'headsigns': [route.headsigns[h] for h in dec.unpack_uints_rle(
                itin.headsigns, 0, stop_count)[0]],
            'pickup_types': dec.unpack_2bit(
                itin.pickup_types, 0, stop_count)[0] or None,
            'dropoff_types': dec.unpack_2bit(
                itin.dropoff_types, 0, stop_count)[0] or None,
            'opposite_direction': itin.opposite_direction,
            'departure_deltas': list(itin.departure_deltas),
            'service_ids': list_info(itin.service_ids),
            'trips_length': len(itin.trips),
        }))
        print_trips(itin.trips,
                    len(itin.service_ids), stop_count, 2,
                    route.has_frequencies, r.has_wheelchair_info,
                    r.has_bike_info)


def print_trips(data: bytes, count: int, stops: int, toprint: int,
                has_frequencies: bool, has_wheelchair: bool,
                has_bikes: bool):
    if toprint > count:
        toprint = count
    if not toprint:
        return
    info: dict[str, list[Any]] = {}
    values: list[Any] = []

    deps, pos = dec.unpack_uints_delta(data, 0, count)
    info['first_stop_departure'] = [int_to_time(v*5) for v in deps[:toprint]]
    values, pos = dec.unpack_sints_rle(data, pos, count * (stops - 1))
    info['departure_deltas'] = []
    for i in range(toprint):
        info['departure_deltas'].append(
            [values[i+j] for j in range(0, len(values), count)])

    values, pos = dec.unpack_strings_common(data, pos, count)
    info['gtfs_id'] = values[:toprint]
    values, pos = dec.unpack_1bit(data, pos, count)
    info['approximate'] = values[:toprint]

    if has_frequencies:
        values, pos = dec.unpack_uints(data, pos, count)
        info['end_time'] = [
            int_to_time((v+d)*5) for v, d in zip(values[:toprint], deps)]
        values, pos = dec.unpack_uints(data, pos, count)
        info['interval'] = values[:toprint]
    if has_wheelchair:
        values, pos = dec.unpack_2bit(data, pos, count)
        info['wheelchair'] = [g.Accessibility.Name(v)
                              for v in values[:toprint]]
    if has_bikes:
        values, pos = dec.unpack_2bit(data, pos, count)
        info['bikes'] = [g.Accessibility.Name(v)
                         for v in values[:toprint]]
    for i in range(toprint):
        print(prep({k: v[i] for k, v in info.items()}))


def read_data(f: BinaryIO, offset: int, length: int,
              compressed: bool = True) -> bytes:
    f.seek(offset)
    data = f.read(abs(length))
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
        help='Block name (agencies/stops/lookup/shapes/calendar/routes)')
    parser.add_argument('--id', type=int, help='Object id to print')
    parser.add_argument('-q', '--query', help='Query string for lookup')
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
    agencies = read_block(f, g.Agencies(), blocks[g.Block.B_AGENCIES])
    shapes = read_block(f, g.ShapeMetadata(), blocks[g.Block.B_SHAPES])
    stops = read_block(f, g.StopMetadata(), blocks[g.Block.B_STOPS])
    lookup = read_block(f, g.LookupMetadata(), blocks[g.Block.B_LOOKUP])
    calendar = read_block(f, g.CalendarMetadata(), blocks[g.Block.B_CALENDAR])
    routes = read_block(f, g.RouteMetadata(), blocks[g.Block.B_ROUTES])

    if not options.block:
        print_footer(footer)
        print_shape_metadata(shapes)
        print_stop_metadata(stops)
        print_lookup_metadata(lookup)
        print_calendar_metadata(calendar)
        print_route_metadata(routes)
    elif options.block == 'agencies':
        print_agencies(agencies)
    elif options.block == 'shapes':
        print_shape(
            f, footer.compressed, blocks[g.Block.B_SHAPES], shapes, options.id)
    elif options.block == 'stops':
        print_stop(f, blocks[g.Block.B_STOPS], stops, options.id)
    elif options.block == 'lookup':
        if not options.query:
            print('--query parameter is required')
        else:
            print_lookup(f, lookup, options.query,
                         blocks[g.Block.B_STOPS], stops)
    elif options.block == 'calendar':
        print_calendar(f, footer.compressed, blocks[g.Block.B_CALENDAR],
                       calendar, options.id)
    elif options.block == 'routes':
        print_route(
            f, footer.compressed, blocks[g.Block.B_ROUTES], routes, options.id)
    else:
        print(f'Unsupported block type: {options.block}')


if __name__ == '__main__':
    main()
