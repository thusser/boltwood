from __future__ import annotations

from typing import List

import numpy as np
from datetime import datetime
import logging

from . import api


class Report:
    """A report from the Boltwood II sensor."""

    def __init__(self, raw_data: bytearray = None, content: str = None, columns: list = None, req_columns: int = None):
        """Initialize new report.

        Args:
            raw_data: Raw data for report.
        """

        # init
        self.raw_data = raw_data
        self.content = content
        self.columns = columns
        self.req_columns = req_columns
        self.data = {}
        self.time = datetime.utcnow()

        # parse
        if content is not None:
            self._parse_content()

    def __getattr__(self, item):
        """Return value."""

        if item == 'time':
            return self.time
        else:
            return self.data[item]

    def format_string(self, item) -> str:
        """Format value as string.

        Args:
            item: Name of value.

        Returns:
            Formatted string.
        """

        if item == 'time':
            return self.time.strftime('%H:%M:%S')
        elif item in self.data:
            # special treatment for floats
            return '%.2f' % self.data[item] if isinstance(self.data[item], float) else str(self.data[item])
        else:
            return 'N/A'

    def _parse_content(self):
        """Parse report data."""

        # can currently only parse the normal weather report
        s = self.content.split()
        req_columns = len(self.data) if self.req_columns is None else self.req_columns
        if len(s) < req_columns:
            logging.warning('Boltwood II report too small! (%d < %d)', len(s), req_columns)
            return

        # loop columns
        for i, (name, typ) in enumerate(self.columns):
            # got value?
            if i < len(s):
                # get value, special treatment for bools
                self.data[name] = s[i] == 'Y' if typ == bool else typ(s[i])

    @staticmethod
    def parse_report(raw_data: bytearray) -> Report:
        # get type
        try:
            report_type = api.ReportType(raw_data[2:3])
        except ValueError:
            raise ValueError('Invalid report type found: %s' % raw_data[2:3])

        # decode bytes from Boltwood into a string
        try:
            # seems like last 4 bytes are always rubbish
            content = raw_data[4:-5].decode('utf-8')
        except UnicodeDecodeError as e:
            raise ValueError('Unicode decode error: %s' % str(e))

        # get report class
        report_class = {
            api.ReportType.THERMO_CALIB: ThermopileCalibReport,
            api.ReportType.SENSORS: SensorsReport,
            api.ReportType.WETNESS_CALIB: WetnessCalibReport,
            api.ReportType.THRESHOLD: ThresholdReport,
            api.ReportType.WETNESS: WetnessReport
        }[report_type]

        # parse report
        return report_class(raw_data, content)


class ThermopileCalibReport(Report):
    """A thermopile calibration report."""
    def __init__(self, *args, **kwargs):
        # define columns
        columns = [
            ('eThermopileCal', int),
            ('eBestK', float),
            ('eBestD', float),
            ('eBestOffs', float)
        ]

        # init report
        Report.__init__(self, columns=columns, *args, **kwargs)


class WetnessCalibReport(Report):
    """A wetness calibration report."""
    def __init__(self, *args, **kwargs):
        # define columns
        columns = [
            ('eWetCal', int),
            ('eWetOscFactor', float),
            ('eRawWetAvg', int),
            ('eCaseT', float),
            ('eshtAmbientT', float),
            ('enomOsc', int),
            ('oscDry', int),
            ('minWetAvg', int),
            ('dif', int),
            ('unknown1', str)
        ]

        # init report
        Report.__init__(self, columns=columns, req_columns=8, *args, **kwargs)


class ThresholdReport(Report):
    """A threshold report."""
    def __init__(self, *args, **kwargs):
        # define columns
        columns = [
            ('serialNumber', int),
            ('version', int),
            ('eSendErrs', int),
            ('eCloudyThresh', float),
            ('eVeryCloudyThresh', float),
            ('eWindyThresh', float),
            ('eVeryWindyThresh', float),
            ('eRainThresh', int),
            ('eWetThresh', int),
            ('eDaylightCode', int),
            ('eDayThresh', int),
            ('eVeryDayThresh', int),
            ('unknown1', int),
            ('unknown2', int),
            ('unknown3', int),
            ('unknown4', int),
            ('unknown5', int)
        ]

        # init report
        Report.__init__(self, columns=columns, *args, **kwargs)


class WetnessReport(Report):
    """A threshold report."""
    def __init__(self, *args, **kwargs):
        # define columns
        columns = [
            ('caseVal', float),
            ('ambT', float),
            ('wAvgW', int),
            ('wAvgC', float),
            ('nomos', float),
            ('rawWT', int),
            ('wetAvg', int)
        ]

        # init report
        Report.__init__(self, columns=columns, *args, **kwargs)


class SensorsReport(Report):
    """A sensor data report."""
    def __init__(self, *args, **kwargs):
        # define columns
        columns = [
            ('humidstatTempCode', int),
            ('cloudCond', int),
            ('windCond', int),
            ('rainCond', int),
            ('skyCond', int),
            ('roofCloseRequested', int),
            ('skyMinusAmbientTemperature', float),
            ('ambientTemperature', float),
            ('windSpeed', float),
            ('wetSensor', bool),
            ('rainSensor', bool),
            ('relativeHumidityPercentage', int),
            ('dewPointTemperature', float),
            ('caseTemperature', float),
            ('rainHeaterPercentage', int),
            ('blackBodyTemperature', float),
            ('rainHeaterState', int),
            ('powerVoltage', float),
            ('anemometerTemeratureDiff', float),
            ('wetnessDrop', int),
            ('wetnessAvg', int),
            ('wetnessDry', int),
            ('rainHeaterPWM', int),
            ('anemometerHeaterPWM', int),
            ('thermopileADC', int),
            ('thermistorADC', int),
            ('powerADC', int),
            ('blockADC', int),
            ('anemometerThermistorADC', int),
            ('davisVaneADC', int),
            ('dkMPH', float),
            ('extAnemometerDirection', int),
            ('rawWetnessOsc', int),
            ('dayCond', int),
            ('daylightADC', int)
        ]

        # init report
        Report.__init__(self, columns=columns, *args, **kwargs)

    @property
    def rain_status(self):
        return api.RAIN_CODES[self.data['rainCond']] if 'rainCond' in self.data else 'N/A'

    @property
    def sky_status(self):
        return api.SKY_CODES[self.data['skyCond']] if 'skyCond' in self.data else 'N/A'


class AverageSensorsReport(Report):
    """A sensor data report."""

    def __init__(self, reports: List[SensorsReport], *args, **kwargs):
        # define columns
        columns = [
            ('skyMinusAmbientTemperature', float),
            ('ambientTemperature', float),
            ('windSpeed', float),
            ('wetSensor', bool),
            ('rainSensor', bool),
            ('relativeHumidityPercentage', int),
        ]

        # init report
        Report.__init__(self, columns=columns, *args, **kwargs)

        # average
        data = {k: [] for k, _ in columns}
        for r in reports:
            for c, _ in columns:
                try:
                    data[c].append(r.data[c])
                except KeyError:
                    pass

        # calculate mean
        for c in ['skyMinusAmbientTemperature', 'ambientTemperature', 'windSpeed', 'relativeHumidityPercentage']:
            self.data[c] = np.mean(data[c])

        # rain
        self.data['rainSensor'] = any(data['rainSensor'])
