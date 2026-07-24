from .helper import GtfsHelper
from .wrapper import IdReference
from zipfile import ZipFile
from datetime import date, timedelta
from .wrapper import CalendarService


class CalendarReader:
    def __init__(self, zipfile: ZipFile, ids: IdReference):
        self.z = GtfsHelper(zipfile)
        self.ids = ids
        self.calendar: list[CalendarService] = []

    def prepare(self) -> list[CalendarService]:
        # We compress the calendar to contain just yesterday .. today + 365.
        yesterday = date.today() - timedelta(days=1)
        inayear = date.today() + timedelta(days=366)

        result: dict[str, CalendarService] = {}
        if self.z.has_file('calendar'):
            with self.z.open_table('calendar') as f:
                for row, service_id in self.z.table_reader(f, 'service_id'):
                    weekdays: list[bool] = []
                    for i, k in enumerate((
                            'monday', 'tuesday', 'wednesday', 'thursday',
                            'friday', 'saturday', 'sunday')):
                        weekdays.append(row[k] == '1')

                    start_date = max(yesterday, min(
                        inayear, self.int_to_date(row['start_date'])))
                    end_date = max(yesterday, min(
                        inayear, self.int_to_date(row['end_date'])))
                    operational = start_date < inayear or end_date > yesterday
                    result[service_id] = CalendarService(
                        start_date=start_date,
                        end_date=end_date,
                        weekdays=[False] * 7 if not operational else weekdays,
                    )

        if self.z.has_file('calendar_dates'):
            with self.z.open_table('calendar_dates') as f:
                for row, service_id in self.z.table_reader(f, 'service_id'):
                    excluded = row['exception_type'] == '2'
                    day = self.int_to_date(row['date'])
                    if day < yesterday or day > inayear:
                        continue
                    if excluded:
                        if service_id in result:
                            result[service_id].except_days.append(day)
                    else:
                        if service_id not in result:
                            result[service_id] = CalendarService(
                                start_date=day,
                                end_date=day,
                                weekdays=[False] * 7,
                            )
                        else:
                            if day < result[service_id].start_date:
                                result[service_id].start_date = day
                            if day > result[service_id].end_date:
                                result[service_id].end_date = day
                        result[service_id].including_days.append(day)

        # Filter and sort the calendar by start_date.
        calendar = list(result.items())
        calendar.sort(key=lambda s: s[1].start_date)
        self.ids.services = {s[0]: i for i, s in enumerate(calendar)}
        self.calendar = [s[1] for s in calendar]
        return self.calendar

    def int_to_date(self, s: str) -> date:
        d = int(s)
        return date(d // 10000, (d % 10000) // 100, d % 100)
