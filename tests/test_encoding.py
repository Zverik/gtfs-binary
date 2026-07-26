import unittest
from gtfs_binary import encoding as e
from gtfs_binary import decoding as d


class TestEncoding(unittest.TestCase):
    def test_encode(self):
        self.assertEqual(e.pack_string('abc'), b'\x03abc')
        self.assertEqual(e.pack_string(''), b'\x00')
        self.assertEqual(
            e.pack_strings(['abc', '12']), b'\x03abc\x0212')
        self.assertEqual(
            e.pack_1bit([True] * 4 + [False] * 4 + [True]),
            b'\xF0\x80')
        self.assertEqual(
            e.pack_2bit([3, 2, 1, 0, 2]), b'\xE4\x80')

        self.assertEqual(e.pack_uint(0), b'\x00')
        self.assertEqual(e.pack_uint(127), b'\x7f')
        self.assertEqual(e.pack_uint(128), b'\x80\x01')
        self.assertEqual(e.pack_uint(129), b'\x81\x01')

        self.assertEqual(e.pack_sint(0), b'\x00')
        self.assertEqual(e.pack_sint(-1), b'\x01')
        self.assertEqual(e.pack_sint(1), b'\x02')
        self.assertEqual(e.pack_sint(64), b'\x80\x01')
        self.assertEqual(e.pack_sint(-65), b'\x81\x01')

        self.assertEqual(e.pack_uints([1, 2, 129]), b'\x01\x02\x81\x01')
        self.assertEqual(e.pack_uints([1, 2, 129], add_len=True),
                         b'\x03\x01\x02\x81\x01')
        self.assertEqual(e.pack_sints([1, 2, -65]), b'\x02\x04\x81\x01')
        self.assertEqual(e.pack_sints([1, 2, -65], add_len=True),
                         b'\x03\x02\x04\x81\x01')

        self.assertEqual(e.pack_uints_delta([100, 102, 120, 300]),
                         b'\x64\x02\x12\xb4\x01')
        self.assertEqual(e.pack_uints_delta([100, 102, 120, 300], start=99),
                         b'\x01\x02\x12\xb4\x01')
        self.assertEqual(e.pack_sints_delta([100, 98, 120, -60]),
                         b'\xc8\x01\x03\x2c\xe7\x02')
        self.assertEqual(e.pack_sints_delta([100, 98, 120, -60], start=99),
                         b'\x02\x03\x2c\xe7\x02')

        self.assertEqual(e.pack_bytes_rle(b''), b'')
        self.assertEqual(e.pack_bytes_rle(b'112'), b'\x001\xff2')
        # TODO: tests for uints and strings, I'm bored.

    def test_encode_decode(self):
        p1 = e.pack_string('abc')
        self.assertEqual(d.unpack_string(p1, 0), ('abc', len(p1)))
        self.assertEqual(d.unpack_string(b'1' + p1, 1), ('abc', len(p1)+1))
        p2 = e.pack_strings(['abc', '12'])
        self.assertEqual(d.unpack_strings(p2, 0, 2), (['abc', '12'], len(p2)))

        bits = [True] * 4 + [False] * 4 + [True]
        p3 = e.pack_1bit(bits)
        self.assertEqual(d.unpack_1bit(p3, 0, 9), (bits, len(p3)))
        bits2 = [3, 2, 1, 0, 2]
        p4 = e.pack_2bit(bits2)
        self.assertEqual(d.unpack_2bit(p4, 0, 5), (bits2, len(p4)))

        self.assertEqual(d.unpack_uint(e.pack_uint(0), 0), (0, 1))
        self.assertEqual(d.unpack_uint(e.pack_uint(127), 0), (127, 1))
        self.assertEqual(d.unpack_uint(e.pack_uint(128), 0), (128, 2))

        self.assertEqual(d.unpack_sint(e.pack_sint(0), 0), (0, 1))
        self.assertEqual(d.unpack_sint(e.pack_sint(-1), 0), (-1, 1))
        self.assertEqual(d.unpack_sint(e.pack_sint(1), 0), (1, 1))
        self.assertEqual(d.unpack_sint(e.pack_sint(64), 0), (64, 2))
        self.assertEqual(d.unpack_sint(e.pack_sint(-65), 0), (-65, 2))


if __name__ == '__main__':
    unittest.main()
