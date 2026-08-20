from ..helpers import GtfsHelper, IdReference, g
from zipfile import ZipFile


class RoutesReader:
    def __init__(self, zipfile: ZipFile, ids: IdReference):
        self.z = GtfsHelper(zipfile)
        self.ids = ids

    def prepare(self) -> list[g.Route]:
        result: list[g.Route] = []
        with self.z.open_table('routes')as f:
            for row, route_id in self.z.table_reader(f, 'route_id'):
                route = g.Route(
                    agency_id=self.ids.agencies[row['agency_id']],
                    gtfs_id=route_id,
                    type=self.route_type_to_enum(row['route_type']),
                    short_name=row.get('route_short_name'),
                    long_name=row.get('route_long_name'),
                    desc=row.get('route_desc'),
                )
                if row.get('route_color') and row['route_color'].upper() != 'FFFFFF':
                    route.color = int(row['route_color'], 16)
                if route.color == 0:
                    route.color = 0xFFFFFF
                if row.get('route_text_color', '') and row['route_text_color'] != '000000':
                    route.text_color = int(row['route_text_color'], 16)
                result.append(route)
                self.ids.routes[route_id] = len(result) - 1
        return result

    def route_type_to_enum(self, value: str) -> int:
        t = int(value)
        if t == 0 or t // 100 == 9:
            return g.RouteType.T_TRAM
        if t in (1, 401, 402):
            return g.RouteType.T_SUBWAY
        if t == 2 or t // 100 == 1:
            return g.RouteType.T_RAIL
        if t == 3 or t // 100 == 7:
            return g.RouteType.T_BUS
        if t == 4 or t == 1200:
            return g.RouteType.T_FERRY
        if t == 5 or t == 1302:
            return g.RouteType.T_CABLE_TRAM
        if t == 6 or t // 100 == 13:
            return g.RouteType.T_AERIAL
        if t == 7 or t == 1400:
            return g.RouteType.T_FUNICULAR
        if t == 1501:
            return g.RouteType.T_COMMUNAL_TAXI
        if t // 100 == 2:
            return g.RouteType.T_COACH
        if t == 11 or t == 800:
            return g.RouteType.T_TROLLEYBUS
        if t == 12 or t == 405:
            return g.RouteType.T_MONORAIL
        if t in (400, 403, 403):
            return g.RouteType.T_URBAN_RAIL
        if t == 1000:
            return g.RouteType.T_WATER
        if t == 1100:
            return g.RouteType.T_AIR
        if t // 100 == 15:
            return g.RouteType.T_TAXI
        if t // 100 == 17:
            return g.RouteType.T_MISC
        raise ValueError(f'Wrong route type {t}')
