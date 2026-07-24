import itertools


def pack_string(s: str) -> bytes:
    b = s.encode()
    if len(b) > 255:
        # Shorten the string to 255 bytes
        b = b[:255].decode('utf-8', 'ignore').encode()
    return len(b).to_bytes() + b


def pack_strings(values: list[str]) -> bytes:
    return b''.join(pack_string(s) for s in values)


def pack_1bit(values: list[bool]) -> bytes:
    result = b''
    for chunk in itertools.batched(values, 8):
        v = 0
        for i, bit in enumerate(chunk):
            v += (1 if bit else 0) << (7 - i)
        result += v.to_bytes()
    return result


def pack_1bit_to_uint(values: list[bool]) -> int:
    """Compresses a list of bools to an integer.
    Incompatible with pack_1bit because this one fills
    bits lowest to highest."""
    result = 0
    for i, bit in enumerate(values):
        result += (1 if bit else 0) << i
    return result


def pack_2bit(values: list[int]) -> bytes:
    result = b''
    for chunk in itertools.batched(values, 4):
        v = 0
        for i, bit in enumerate(chunk):
            v += bit << ((3 - i) * 2)
        result += v.to_bytes()
    return result


def pack_uint(value: int) -> bytes:
    if value < 0:
        raise ValueError(f'Value for pack_uint is negative: {value}')
    result = b''
    while value >= 128:
        result += (128 + (value & 127)).to_bytes()
        value >>= 7
    result += value.to_bytes()
    return result


def sint_to_uint(value: int) -> int:
    if value >= 0:
        return value << 1
    return ((-value - 1) << 1) + 1


def pack_sint(value: int) -> bytes:
    return pack_uint(sint_to_uint(value))


def pack_uints(values: list[int], add_len: bool = False) -> bytes:
    return (b'' if not add_len else pack_uint(len(values))) + b''.join(
        pack_uint(v) for v in values)


def pack_sints(values: list[int], add_len: bool = False) -> bytes:
    return (b'' if not add_len else pack_uint(len(values))) + b''.join(
        pack_sint(v) for v in values)


def pack_uints_delta(values: list[int], start: int = 0, add_len: bool = False
                     ) -> bytes:
    vcount = b'' if not add_len else pack_uint(len(values))
    return vcount + b''.join(
        pack_uint(values[i] - (start if i == 0 else values[i-1]))
        for i in range(len(values))
    )


def pack_sints_delta(values: list[int], start: int = 0, add_len: bool = False
                     ) -> bytes:
    vcount = b'' if not add_len else pack_uint(len(values))
    return vcount + b''.join(
        pack_sint(values[i] - (start if i == 0 else values[i-1]))
        for i in range(len(values))
    )


def pack_uints_rle(values: list[int]) -> bytes:
    """Same algorithm as ORC RLEv1."""
    result = b''
    rnd: list[int] = []
    i = 0
    while i < len(values):
        if (i + 2 < len(values) and values[i] == values[i+1]
                and values[i] == values[i+2]):
            if len(rnd) > 0:
                result += (-len(rnd)).to_bytes(1, signed=True) + pack_uints(
                    rnd)
                rnd = []
            # Start a run
            j = i + 2
            while j < len(values) and values[j] == values[i] and j - i < 130:
                j += 1
            result += (j - i - 3).to_bytes() + pack_uint(values[i])
            i = j
        else:
            if len(rnd) == 128:
                # reset the literal list
                result += (-len(rnd)).to_bytes(1, signed=True) + pack_uints(
                    rnd)
                rnd = []
            rnd.append(values[i])
            i += 1
    if len(rnd) > 0:
        result += (-len(rnd)).to_bytes(1, signed=True) + pack_uints(rnd)
    return result


def pack_bytes_rle(values: bytes) -> bytes:
    """Same algorithm as ORC."""
    result = b''
    rnd = b''
    i = 0
    while i < len(values):
        if (i + 2 < len(values) and values[i] == values[i+1]
                and values[i] == values[i+2]):
            if len(rnd) > 0:
                result += (-len(rnd)).to_bytes(1, signed=True) + rnd
                rnd = b''
            # Start a run
            j = i + 2
            while j < len(values) and values[j] == values[i] and j - i < 130:
                j += 1
            result += (j - i - 3).to_bytes() + values[i].to_bytes()
            i = j
        else:
            if len(rnd) == 128:
                # reset the literal list
                result += (-len(rnd)).to_bytes(1, signed=True) + rnd
                rnd = b''
            rnd += values[i].to_bytes()
            i += 1
    if len(rnd) > 0:
        result += (-len(rnd)).to_bytes(1, signed=True) + rnd
    return result
