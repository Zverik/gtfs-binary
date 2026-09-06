import os
import struct
import zstandard
from . import g
from typing import BinaryIO
from google.protobuf.message import Message


ARCH = zstandard.ZstdDecompressor()


def read_footer(f: BinaryIO) -> g.Footer:
    if f.read(4) != b'GTB\n':
        raise IOError('The header does not match the spec.')

    f.seek(-2, os.SEEK_END)
    footer_len = struct.unpack('>H', f.read(2))[0]
    f.seek(-2-footer_len, os.SEEK_END)
    footer = g.Footer()
    footer.ParseFromString(f.read(footer_len))
    return footer


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
