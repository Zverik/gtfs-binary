import argparse
import zstandard
import os
import struct
from typing import BinaryIO
from google.protobuf.message import Message
from .helpers import g


ARCH = zstandard.ZstdDecompressor()


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


class GTBWriter:
    def __init__(self, f: BinaryIO, compressing: bool):
        self.f = f
        self.compressed = compressing
        self.arch = zstandard.ZstdCompressor(level=10)

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

    def write(self, fileobj: BinaryIO):
        pos = 4
        blocks: list[g.BlockMetadata] = []

        def write_block(metadata: bytes, data: bytes, block: g.Block
                        ) -> None:
            nonlocal pos, blocks
            compr = self.compress_if_better(metadata)
            fileobj.write(compr[1])
            if data:
                fileobj.write(data)
            blocks.append(g.BlockMetadata(
                block=block,
                offset=pos,
                length=len(compr[1]),
                compressed=compr[0],
            ))
            pos += len(compr[1]) + len(data)

        self.f.seek(-2, os.SEEK_END)
        footer_len = struct.unpack('>H', self.f.read(2))[0]
        self.f.seek(-2-footer_len, os.SEEK_END)
        footer = g.Footer()
        footer.ParseFromString(self.f.read(footer_len))

        o_blk = {b.block: b for b in footer.blocks}
        o_cmp = footer.compressed

        fileobj.write(b'GTB\n')
        write_block(*self.pack_agencies(o_blk[g.Block.B_AGENCIES], o_cmp),
                    g.Block.B_AGENCIES)
        write_block(*self.pack_shapes(o_blk[g.Block.B_SHAPES], o_cmp),
                    g.Block.B_SHAPES)
        write_block(*self.pack_stops(o_blk[g.Block.B_STOPS], o_cmp),
                    g.Block.B_STOPS)
        write_block(*self.pack_lookup(o_blk[g.Block.B_LOOKUP], o_cmp),
                    g.Block.B_LOOKUP)
        write_block(*self.pack_calendar(o_blk[g.Block.B_CALENDAR], o_cmp),
                    g.Block.B_CALENDAR)
        write_block(*self.pack_routes(o_blk[g.Block.B_ROUTES], o_cmp),
                    g.Block.B_ROUTES)
        footer.compressed = self.compressed
        footer.blocks.clear()
        footer.blocks.extend(blocks)
        footer_data = footer.SerializeToString()
        fileobj.write(footer_data)
        fileobj.write(struct.pack('>H', len(footer_data)))

    def pack_agencies(self, block: g.BlockMetadata, cmp: bool
                      ) -> tuple[bytes, bytes]:
        agencies = read_block(self.f, g.Agencies(), block)
        return agencies.SerializeToString(), b''

    def pack_lookup(self, block: g.BlockMetadata, cmp: bool
                    ) -> tuple[bytes, bytes]:
        lookup = read_block(self.f, g.LookupMetadata(), block)
        return lookup.SerializeToString(), b''

    def pack_shapes(self, block: g.BlockMetadata, cmp: bool
                    ) -> tuple[bytes, bytes]:
        shapes = read_block(self.f, g.ShapeMetadata(), block)
        chunks: list[bytes] = []
        offset = block.offset + block.length
        for chunk_len in shapes.chunk_lengths:
            chunk = read_data(self.f, offset, chunk_len, cmp)
            chunks.append(self.compress(chunk))
            offset += chunk_len
        metadata = g.ShapeMetadata(
            chunk_size=shapes.chunk_size,
            chunk_lengths=[len(c) for c in chunks])
        return metadata.SerializeToString(), b''.join(chunks)

    def pack_stops(self, block: g.BlockMetadata, cmp: bool
                   ) -> tuple[bytes, bytes]:
        stops = read_block(self.f, g.StopMetadata(), block)
        chunks: list[tuple[bool, bytes]] = []
        offset = block.offset + block.length
        for chunk_len in stops.chunk_lengths:
            chunk = read_data(self.f, offset, chunk_len, cmp)
            chunks.append(self.compress_if_better(chunk))
            offset += abs(chunk_len)
        stops.chunk_lengths.clear()
        stops.chunk_lengths.extend(
            [len(c[1]) * (1 if c[0] else -1) for c in chunks])
        return stops.SerializeToString(), b''.join(c[1] for c in chunks)

    def pack_calendar(self, block: g.BlockMetadata, cmp: bool
                      ) -> tuple[bytes, bytes]:
        calendar = read_block(self.f, g.CalendarMetadata(), block)
        chunks: list[tuple[bool, bytes]] = []
        offset = block.offset + block.length
        for chunk_len in calendar.month_lengths:
            chunk = read_data(self.f, offset, chunk_len, cmp)
            chunks.append(self.compress_if_better(chunk))
            offset += abs(chunk_len)
        calendar.month_lengths.clear()
        calendar.month_lengths.extend(
            [len(c[1]) * (1 if c[0] else -1) for c in chunks])
        return calendar.SerializeToString(), b''.join(c[1] for c in chunks)

    def pack_routes(self, block: g.BlockMetadata, cmp: bool
                    ) -> tuple[bytes, bytes]:
        routes = read_block(self.f, g.RouteMetadata(), block)
        chunks: list[bytes] = []
        offset = block.offset + block.length
        for chunk_len in routes.route_lengths:
            chunk = read_data(self.f, offset, chunk_len, cmp)
            chunks.append(self.compress(chunk))
            offset += chunk_len

        metadata = g.RouteMetadata(
            route_lengths=[len(c) for c in chunks],
            has_wheelchair_info=routes.has_wheelchair_info,
            has_bike_info=routes.has_bike_info,
        )
        return metadata.SerializeToString(), b''.join(chunks)


def main():
    parser = argparse.ArgumentParser(
        description='Compresses or decompresses GTFS Binary blocks')
    parser.add_argument('action', help='[c]ompress/[d]ecompress')
    parser.add_argument('input', help='Source GTFS Binary file')
    parser.add_argument('output', help='Output GTFS Binary file')
    options = parser.parse_args()

    f = open(options.input, 'rb')
    if f.read(4) != b'GTB\n':
        print('The header does not match the spec.')
        return

    gtb = GTBWriter(f, options.action[0] == 'c')
    with open(options.output, 'wb') as ff:
        gtb.write(ff)


if __name__ == '__main__':
    main()
