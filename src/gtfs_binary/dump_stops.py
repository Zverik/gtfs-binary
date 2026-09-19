import argparse
import json
from typing import Any
from .helpers import decoding as dec, g
from .helpers.readers import read_footer, read_data, read_block


def read_stop_chunk(chunk: bytes, chunk_len: int, s: g.StopMetadata
                    ) -> list[dict[str, Any]]:
    info: list[dict[str, Any]] = []
    for i in range(chunk_len):
        info.append({})
    values: list[Any] = []
    v: Any = None  # just to satisfy mypy
    values, pos = dec.unpack_strings(chunk, 0, chunk_len)
    for i, v in enumerate(values):
        info[i]['gtfs_id'] = str(v)
    values, pos = dec.unpack_strings(chunk, pos, chunk_len)
    for i, v in enumerate(values):
        info[i]['code'] = v
    values, pos = dec.unpack_strings(chunk, pos, chunk_len)
    for i, v in enumerate(values):
        info[i]['name'] = v
    values, pos = dec.unpack_strings(chunk, pos, chunk_len)
    for i, v in enumerate(values):
        info[i]['desc'] = v
    values, pos = dec.unpack_sints_delta(chunk, pos, chunk_len)
    for i, v in enumerate(values):
        info[i]['lat'] = v / 100000.0
    values, pos = dec.unpack_sints_delta(chunk, pos, chunk_len)
    for i, v in enumerate(values):
        info[i]['lon'] = v / 100000.0
    values, pos = dec.unpack_2bit(chunk, pos, chunk_len)
    for i, v in enumerate(values):
        info[i]['wheelchair'] = g.Accessibility.Name(v)
    for i in range(chunk_len):
        route_ids, pos = dec.unpack_uints_delta(chunk, pos, -1)
        info[i]['route_ids'] = route_ids
    if s.has_stations:
        values, pos = dec.unpack_1bit(chunk, pos, chunk_len)
        for i, v in enumerate(values):
            info[i]['is_station'] = v
        values, pos = dec.unpack_uints_rle(chunk, pos, chunk_len)
        for i, v in enumerate(values):
            if v:
                info[i]['parent_id'] = v - 1
    if s.has_directions:
        values, pos = dec.unpack_4bit(chunk, pos, chunk_len)
        for i, v in enumerate(values):
            if v:
                info[i]['direction'] = g.Direction.Name(v)
    return info


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Dumps all the stops from GTB to a GeoJSON')
    parser.add_argument('input', help='Source GTFS Binary file')
    parser.add_argument('output', help='Output GeoJSON file')
    options = parser.parse_args()

    features: list[dict] = []
    with open(options.input, 'rb') as f:
        footer = read_footer(f)
        blocks = {b.block: b for b in footer.blocks}
        block = blocks[g.Block.B_STOPS]
        stops = read_block(f, g.StopMetadata(), block)
        offset = block.offset + block.length
        for i in range(len(stops.chunk_lengths)):
            chunk = read_data(f, offset, stops.chunk_lengths[i],
                              stops.chunk_lengths[i] > 0)
            chunk_len = stops.chunk_stop_counts[i]
            offset += abs(stops.chunk_lengths[i])
            decoded = read_stop_chunk(chunk, chunk_len, stops)
            for stop in decoded:
                geometry = {
                    'type': 'Point',
                    'coordinates': [stop['lon'], stop['lat']],
                }
                features.append({
                    'type': 'Feature',
                    'geometry': geometry,
                    'properties': stop,
                })

    with open(options.output, 'w') as f:
        json.dump({'type': 'FeatureCollection', 'features': features}, f)
