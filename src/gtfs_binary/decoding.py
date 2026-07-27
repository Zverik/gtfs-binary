import itertools


def unpack_string(data: bytes, start: int) -> tuple[str, int]:
    strlen = data[start]
    return data[start+1:start+1+strlen].decode(), start + strlen + 1


def unpack_strings(data: bytes, start: int, count: int
                   ) -> tuple[list[str], int]:
    result = []
    for i in range(count):
        if start >= len(data):
            raise IndexError(f'Expected {count}, ran out at {len(result)}')
        s, start = unpack_string(data, start)
        result.append(s)
    return result, start


def unpack_1bit(data: bytes, start: int, count: int
                ) -> tuple[list[bool], int]:
    result: list[bool] = []
    for byte in range((count + 7) // 8):
        cnt = min(8, count - byte * 8)
        result += [data[start] & (1 << i) != 0 for i in range(7, 7-cnt, -1)]
        start += 1
    return result, start


def unpack_2bit(data: bytes, start: int, count: int) -> tuple[list[int], int]:
    result: list[int] = []
    for byte in range((count + 3) // 4):
        cnt = min(4, count - byte * 4)
        result += [(data[start] >> i) & 3
                   for i in range(6, 6-cnt*2, -2)]
        start += 1
    return result, start


def unpack_uint(data: bytes, start: int) -> tuple[int, int]:
    result = 0
    mult = 1
    while data[start] & 0x80 > 0:
        result += (data[start] & 0x7F) * mult
        mult <<= 7
        start += 1
    result += data[start] * mult
    return result, start + 1


def uint_to_sint(value: int) -> int:
    v = value >> 1
    return -v-1 if value & 1 else v


def unpack_sint(data: bytes, start: int) -> tuple[int, int]:
    value, start = unpack_uint(data, start)
    return uint_to_sint(value), start


def unpack_uints(data: bytes, start: int, count: int
                 ) -> tuple[list[int], int]:
    if count < 0:
        count, start = unpack_uint(data, start)
    result: list[int] = []
    for i in range(count):
        if start >= len(data):
            raise IndexError(f'Expected {count}, ran out at {len(result)}')
        value, start = unpack_uint(data, start)
        result.append(value)
    return result, start


def unpack_sints(data: bytes, start: int, count: int
                 ) -> tuple[list[int], int]:
    result, start = unpack_uints(data, start, count)
    return [uint_to_sint(v) for v in result], start


def unpack_uints_delta(data: bytes, dstart: int, count: int, start: int = 0
                       ) -> tuple[list[int], int]:
    values, dstart = unpack_uints(data, dstart, count)
    return list(itertools.accumulate(values, initial=start))[1:], dstart


def unpack_sints_delta(data: bytes, dstart: int, count: int, start: int = 0
                       ) -> tuple[list[int], int]:
    values, dstart = unpack_sints(data, dstart, count)
    return list(itertools.accumulate(values, initial=start))[1:], dstart


def unpack_bytes_rle(data: bytes, start: int, count: int
                     ) -> tuple[bytes, int]:
    if count < 0:
        count, start = unpack_uint(data, start)
    result, start = unpack_rle(
        data, start, count, lambda v, s: (v[s].to_bytes(), s + 1))
    return b''.join(result), start


def unpack_uints_rle(data: bytes, start: int, count: int
                     ) -> tuple[list[int], int]:
    if count < 0:
        count, start = unpack_uint(data, start)
    result, start = unpack_rle(
        data, start, count, lambda v, s: unpack_uint(v, s))
    return result, start


def unpack_strings_rle(data: bytes, start: int, count: int
                       ) -> tuple[list[str], int]:
    if count < 0:
        count, start = unpack_uint(data, start)
    result, start = unpack_rle(
        data, start, count, lambda v, s: unpack_string(v, s))
    return result, start


def unpack_rle(data: bytes, start: int, count: int, unpack_value,
               min_run: int = 2) -> tuple[list, int]:
    result = []
    while start < len(data) and len(result) < count:
        runlen = data[start]
        start += 1
        if runlen >= 0x80:
            for i in range(256-runlen):
                value, start = unpack_value(data, start)
                result.append(value)
        else:
            value, start = unpack_value(data, start)
            result.extend([value] * (runlen + min_run))
    return result, start
