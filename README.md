# GTFS Binary Packaging

This tool packages a GTFS feed into a compact binary file that can be
processed without unpacking. In a way, it's a database tailored for one
specific purpose: showing stops, route shapes, and listing nearest departures
for any stop. It does not accomodate for routing (yet?).

The binary format was envisioned as an alternative to [GTFS Proto](https://github.com/Zverik/gtfs-proto).
Alas, unpacking a proto file takes some time, and the resulting SQLite
database is slightly bigger than the original GTFS.

## Installation and Usage

Install the `gtfs-binary` package the same way you install other Python packages. For example:

    pip install gtfs-binary

There are two operations it can do:

    gtfs-binary feed.zip -o feed.gtb

And information:

    gtfs-binary feed.gtb
