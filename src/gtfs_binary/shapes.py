from .helper import GtfsHelper
from .wrapper import IdReference
from zipfile import ZipFile
from . import gtfs_binary_pb2 as g


SHAPE_SCALE = 100000


class ShapesReader:
    def __init__(self, zipfile: ZipFile, ids: IdReference):
        self.z = GtfsHelper(zipfile)
        self.ids = ids.shapes
        self.shapes: list[g.Shape] = []

    def prepare(self) -> list[g.Shape]:
        result: list[g.Shape] = []
        if not self.z.has_file('shapes'):
            return result
        with self.z.open_table('shapes') as f:
            for rows, shape_id in self.z.sequence_reader(
                    f, 'shape_id', 'shape_pt_sequence', max_overlapping=1):
                if len(rows) >= 2:
                    shape = g.Shape()
                    for row in rows:
                        coord = (float(row['shape_pt_lat']),
                                 float(row['shape_pt_lon']))
                        new_coord = (round(coord[0] * SHAPE_SCALE),
                                     round(coord[1] * SHAPE_SCALE))
                        shape.latitudes.append(new_coord[0])
                        shape.longitudes.append(new_coord[1])
                    result.append(shape)
                    self.ids[shape_id] = len(result) - 1
        self.shapes = result
        return result
