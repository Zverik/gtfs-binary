# GTFS Binary Packaging

This tool packages a GTFS feed into a compact binary file that can be
processed without unpacking. In a way, it's a database tailored for one
specific purpose: showing stops, route shapes, and listing nearest departures
for any stop. It does not accomodate for routing (yet?).

The binary format was envisioned as an alternative to [GTFS Proto](https://github.com/Zverik/gtfs-proto).
Alas, unpacking a proto file takes some time, and the resulting SQLite
database is slightly bigger than the original GTFS.

Experiments have shown that not only binary files are smaller than protobufs,
but also bsdiff-ed deltas are also ~1.5 times smaller. On the other hand, this
format has a very narrow purpose which prevents using it for routing, for example.

Please refer to [the proto spec](protobuf/gtfs_binary.proto) for the format details,
and use the code to understand the encoding.

## Installation and Usage

Install the `gtfs-binary` package the same way you install other Python packages. For example:

    pip install gtfs-binary

To prepare a binary feed out of zipped GTFS:

    gtfs_binary feed.zip -o feed.gtb

(add `--raw` to skip compression.)

To compress/decompress a binary feed (compressed one needs zstd to read):

    gtb_compress c feed.gtb feed-compressed.gtb
    gtb_compress d feed.gtb feed-decompressed.gtb

To inspect a feed contents:

    gtb_inspect feed.gtb
    gtb_inspect feed.gtb -b stops
    gtb_inspect feed.gtb -b lookup -q stopname

## Incomplete parts

**Note that the format is to have significant changes, including renumbering
of fields, until version 1.0 is published.**

The tool has successfully processed 200 MB feeds, and the inspection tool
shows queries are possible. But there are some feeds and some use-cases not
yet addressed. What is left to do:

* Normalize the unicode in building the stop name index.
* Correctly process a missing first stop departure time (now it just throws an exception).
* Fill in missing departure times based on `shape_dist_traveled` and stop locations.

When the format is stable this all obviously needs to be rewritten in Rust
to save memory and increase speed.

## Author and License

The code was written by Ilya Zverev © 2026 and published under the terms
of the ISC license.

The NLNet Foundation has [sponsored](https://nlnet.nl/project/EasyTransit2/)
the initial development through the [NGI Mobifree Fund](https://nlnet.nl/mobifree)
with financial support from the European Commission.
