from .helper import GtfsHelper
from zipfile import ZipFile
from . import gtfs_binary_pb2 as g
from .wrapper import IdReference


class AgencyReader:
    def __init__(self, zipfile: ZipFile, ids: IdReference):
        self.z = GtfsHelper(zipfile)
        self.ids = ids.agencies

    def prepare(self) -> list[g.Agency]:
        result: list[g.Agency] = []
        with self.z.open_table('agency') as f:
            for row, agency_id in self.z.table_reader(f, 'agency_id'):
                result.append(g.Agency(
                    name=row['agency_name'],
                    url=row['agency_url'],
                    timezone=row.get('agency_timezone'),
                    lang=row.get('agency_lang'),
                    phone=row.get('agency_phone'),
                    fare_url=row.get('agency_fare_url'),
                    email=row.get('agency_email'),
                ))
                self.ids[agency_id] = len(result) - 1
        return result
