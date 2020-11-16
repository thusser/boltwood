import logging
from enum import Enum
import serial
import threading
import numpy as np
from datetime import datetime


REQUEST_POLL = b'\x01'
REPORT_SUFFIX = b'\n'


class ResponsePrefix(Enum):
    ACK = b'\x02A'
    THERMO_CALIB = b'\x02MC'
    REPORT = b'\x02MD'
    WETNESS_CALIB = b'\x02MK'
    NACK = b'\x02N'
    POLLING = b'\x02P'
    ECHO = b'\x02Q'
    ROOF = b'\x02R'
    THRESHOLD = b'\x02MT'
    WETNESS = b'\x02MW'


HT_CODES = {
    0: 'OK',
    1: 'humidity write failure',
    2: 'humidty measurement unfinished',
    3: 'temperature write failure',
    4: 'temperature measurement unfinished',
    5: 'humidity data line not high',
    6: 'temperature data line not high'
}

CLOUD_CODES = {
    0: 'unknown',
    1: 'clear',
    2: 'cloudy',
    3: 'very cloudy'
}

WIND_CODES = {
    0: 'unknown',
    1: 'OK',
    2: 'windy',
    3: 'very windy'
}

RAIN_CODES = {
    0: 'unknown',
    1: 'not raining',
    2: 'recently raining',
    3: 'raining'
}

SKY_CODES = {
    0: 'unknown',
    1: 'clear',
    2: 'cloudy',
    3: 'very cloudy',
    4: 'wet'
}

ROOF_CODES = {
    0: 'OK',
    1: 'close'
}

# Floats! Have to be used as limits: try sequentially:
# TSky >  999 means saturated hot
#      < -998 means saturated cold
#      < -999 means wet sensor
TSKY_CODES = {
    '999.9': 'saturated hot',
    '-999.9': 'saturated cold',
    '-998.9': 'wet sensor'
}

# Floats! Due to rounding errors, should be used as limits: try sequentially
# dTanemom_code < -0.5 means heating up
#               < -1.5 means wet
#               < -2.5 means bad A/D
#               < -3.5 means probe not heating
ANEMOMETER_CODES = {
    '-1.': 'heating up',
    '-2.': 'wet',
    '-3.': 'bad A/D',
    '-4.': 'probe not heating'
}

WETNESS_CODES = {
    'N': 'dry',
    'W': 'wet',
    'w': 'recently wet'
}

OTHER_RAIN_CODES = {
    'N': 'none',
    'R': 'rain',
    'r': 'recent rain'
}

# Floats! Due to rounding errors, should be used as limits: try sequentially
# code >  999 means saturated hot
#      < -999 means saturated cold
THERMOPILE_CODES = {
    '999.9': 'saturated hot',
    '-999.9': 'saturated cold'
}

# Floats! Due to rounding errors, should be used as limits: try sequentially
# code >  999 means saturated hot
#      < -999 means saturated cold
TCALIB_CODES = {
    '999.9': 'saturated hot',
    '-99.9': 'saturated cold'
}

# error if != '1'???? This appears to be wrong: should be != 0???? Switch codes 0 and 1 !!!!
HEATER_CODES = {
    1: 'too hot',
    0: 'OK',
    2: 'too cold',
    3: 'too cold',
    4: 'too cold',
    5: 'too cold',
    6: 'saturated case temperature',
    7: 'normal control'
}

DAYLIGHT_CODES = {
    0: 'unknown',
    1: 'night',
    2: 'twilight',
    3: 'daylight'
}


class Report:
    """A weather report from the Boltwood II sensor."""

    def __init__(self, raw_data: bytearray = None):
        """Initialize new report.

        Args:
            raw_data: Raw data for report. If given, parse it.
        """

        # init
        self.raw_data = raw_data
        self.data = {}
        self.time = datetime.utcnow()
        self.errors = {}
        self.comments = {}

        # parse
        if raw_data is not None:
            self._parse_raw_data()

    def format(self, item) -> str:
        """Format a single value to string

        Args:
            item: Name of value to format.

        Returns:
            Formatted value.
        """

        # what is it?
        if item == 'time':
            return self.time.strftime('%H:%M:%S')
        elif item in self.data:
            return '%.2f' % self.data[item] if isinstance(self.data[item], float) else str(self.data[item])
        else:
            return 'N/A'

    def _parse_raw_data(self):
        """Parses Boltwood II data packet into a dictionary.

        An example of such a packet is:

        '\x02MD 0 3 1 1 3 1 -3.6 27.0 0.0 N N 31 8.6 41.6 0 -99.9 0 24.0 24.7 2 -81 -63 000 135 0130 0348 0942 1023 0148 0152 0.0 053 13996 3 06531097\n'

        The split structure is:

        \x02MD	: START PATTERN
        0-5		: 6x int	: HT_code,cloud_code,wind_code,rain_code,sky_code,roof_code
        6-8		: 3x float	: dT_sky(C),T_ambient(C),v_wind (km/h)
        9,10	: 2x char	: wet_code,rain_code
        11		: 1x int	: humidty (%)
        12,13	: 2x float	: T_dewpoint(C),T_case(C)
        14		: 1x int	: heater (%)
        15		: 1x float	: T_calib(C)
        16		: 1x int	: heater_code
        17,18	: 2x float	: sensor_voltage,dT_anemometer(C)
        19-21	: 3x int	: wetness_drop,wetness_avg,wetness_dry
        22-27	: 6x int	: heater_pwm,anemometer_pwm,thermopile_adc,thermister_adc,power_adc,block_adc
        28-31	: 4x int	: tip_adc,davis_adc,extern_adc,extern_dir
        32-34	: 3x int	: raw_wetness,day_code,day_adc
        \n		: END BYTE

        and returns a dictionary of values.

        Args:
            - report:dict	dictionary from polling thread.
        """

        # decode bytes from Boltwood into a string
        try:
            line = self.raw_data[len(ResponsePrefix.REPORT.value):-1].decode('utf-8')
        except UnicodeDecodeError as e:
            comment = 'unicode decode error : {0}'.format(str(e))
            logging.warning(comment)
            self.comments['decoding'] = comment
            return

        # can currently only parse the normal weather report
        s = line.split()
        if len(s) != 35:
            serr = 'Boltwood II report too small! ({0} != 35)'.format(len(s))
            logging.warning(serr)
            self.errors['packet'] = serr
            return

        wet = False
        raining = False
        try:
            # HUMIDITY-TEMPERATURE SENSORS
            self.data['T_ambient'] = float(s[7])
            self.data['humidity'] = float(s[11])
            status = HT_CODES[int(s[0])]
            if status != 'OK':
                self.errors['hT status'] = status
                logging.warning('Boltwood II humidity error:' + status)
            self.data['hT status'] = status

            # RAIN SENSOR
            rain = RAIN_CODES[int(s[3])]
            if rain == 'raining':
                raining = True
                wet = True
            self.data['rain status'] = rain
            self.data['rain code'] = OTHER_RAIN_CODES[s[10]]

            # SKY TEMPERATURE SENSOR
            dT_sky = float(s[6])
            ok = True
            w = False
            if dT_sky > 999.:
                self.errors['dT_sky'] = TSKY_CODES['999.9']
                logging.warning('Boltwood II sky temperature saturated:' + status)
                ok = False
            if dT_sky < -998.:
                self.comments['dT_sky'] = TSKY_CODES['-998.9']  # WET SENSOR
                logging.warning('Boltwood II sensor is wet:' + status)
                w = True
                ok = False
            if dT_sky < -999.:
                self.comments['dT_sky'] = TSKY_CODES['-999.9']
                w = False
                ok = False
            if ok:
                self.data['dT_sky'] = dT_sky
            if w:
                wet = True
            self.data['cloud status'] = CLOUD_CODES[int(s[1])]
            self.data['sky status'] = SKY_CODES[int(s[4])]

            # WIND SENSOR
            self.data['wind status'] = WIND_CODES[int(s[2])]
            self.data['windspeed'] = float(s[8])

            # WETNESS
            status = WETNESS_CODES[s[9]]
            self.data['wet status'] = status
            if status == 'wet':
                wet = True

            # MISC
            self.data['roof status'] = ROOF_CODES[int(s[5])]
            self.data['T_dewpoint'] = float(s[12])
            self.data['T_case'] = float(s[13])

            status = int(s[14])
            if status < 0 or status > len(HEATER_CODES):
                serr = 'heater code status = {0} = {1}?'.format(s[14], status)
                logging.error(serr)
                self.errors['unknown code'] = serr
            else:
                self.data['heater status'] = HEATER_CODES[status]
                if not (status == 0 or status == 7):  # status==1? SEE boltwood_py
                    self.errors['heater'] = HEATER_CODES[status]

            Tcalib = float(s[15])
            self.data['T_calib'] = Tcalib
            if Tcalib > 999.:
                self.comments['T_calib'] = TCALIB_CODES['999.9']
            elif Tcalib < -99.:
                self.comments['T_calib'] = TCALIB_CODES['-99.9']

            self.data['heater'] = int(s[16])
            self.data['sensor voltage'] = float(s[17])

            dT = float(s[18])
            self.data['dT_anemom'] = dT
            if dT < -0.5:
                self.errors['dT_anemom'] = ANEMOMETER_CODES['-1.']
            elif dT < -1.5:
                self.errors['dT_anemom'] = ANEMOMETER_CODES['-2.']
            elif dT < -2.5:
                self.errors['dT_anemom'] = ANEMOMETER_CODES['-3.']
            elif dT < -3.5:
                self.errors['dT_anemom'] = ANEMOMETER_CODES['-4.']

            self.data['wet drop'] = int(s[19])
            self.data['wet avg'] = int(s[20])
            self.data['wet dry'] = int(s[21])

            self.data['illumination'] = DAYLIGHT_CODES[int(s[33])]

            # compound results
            self.data['wet'] = wet
            self.data['raining'] = raining

        except IndexError:
            # an index error usually occurs, if the line is bad
            logging.error('Error parsing: %s', line)
            self.errors['packet'] = 'cannot completely parse packet'

        except ValueError:
            logging.error('Error parsing: %s', line)
            self.errors['packet'] = 'cannot completely parse packet'

    def __str__(self):
        """Creates a short version of a parsed weatherstation report """
        s = ''
        s += '{0}'.format(self.time)
        if 'T_ambient' in self.data:
            s += ',T_amb={0:.1f}'.format(self.data['T_ambient'])
        if 'humidity' in self.data:
            s += ',H={0}'.format(self.data['humidity'])
        if 'windspeed' in self.data:
            s += ',wind={0:.1f}'.format(self.data['windspeed'])
        if 'dT_sky' in self.data:
            s += ',dT_sky={0:.1f}'.format(self.data['dT_sky'])
        if 'cloud status' in self.data:
            s += ',clouds={0}'.format(self.data['cloud status'])
        if 'wet' in self.data:
            s += ',wet=' + str(self.data['wet'])
        if 'raining' in self.data:
            s += ',rain=' + str(self.data['raining'])
        return s

    @staticmethod
    def average(reports):
        """Average a list of reports

        Args:
            reports: Reports to average.

        Returns:
            New report with averaged values.
        """

        # create new report
        report = Report()

        # get data
        columns = ['T_ambient', 'humidity', 'windspeed', 'dT_sky', 'cloud status', 'wet', 'raining']
        data = {k: [] for k in columns}
        for r in reports:
            for c in columns:
                try:
                    data[c].append(r.data[c])
                except KeyError:
                    pass

        # calculate mean
        for c in ['T_ambient', 'humidity', 'windspeed', 'dT_sky']:
            report.data[c] = np.mean(data[c])

        # rain
        report.data['raining'] = any(data['raining'])

        # return it
        return report


class BoltwoodII:
    """Class that operates a Boltwood II cloud sensor weather station."""

    def __init__(self, port: str = '/dev/ttyUSB0', baudrate: int = 4800, bytesize: int = 8, parity: str = 'N',
                 stopbits: int = 1, rtscts: bool = False, timeout: int = 10, *args, **kwargs):
        """

        Args:
            port: Serial port to use.
            baudrate: Baud rate.
            bytesize: Size of bytes.
            parity: Parity.
            stopbits: Stop bits.
            rtscts: RTSCTS.
            timeout: Timeout for reading [s].
            *args:
            **kwargs:
        """

        # serial connection
        self._conn = None
        self._port = port
        self._baudrate = baudrate
        self._bytesize = bytesize
        self._parity = parity
        self._stopbits = stopbits
        self._rtscts = rtscts
        self._serial_timeout = timeout

        # poll thread
        self._closing = None
        self._thread = None
        self._thread_sleep = 1
        self._max_thread_sleep = 900

        # callback function
        self._callback = None

    def start_polling(self, callback):
        """Start polling the Boltwood II sensor.

        Args:
            callback: Callback function to be called with new data.
        """

        # set callback
        self._callback = callback

        # start thread
        self._closing = threading.Event()
        self._thread = threading.Thread(target=self._poll_thread)
        self._thread.start()

    def stop_polling(self):
        """Stop polling of Boltwood II sensor."""

        # close and wait for thread
        self._closing.set()
        self._thread.join()

    def _poll_thread(self):
        """Thread to poll and respond to the serial output of the Boltwood II sensor head.

        The operation of the Boltwood is somewhat strange, in that the sensor sometimes reports when
        it is ready to be polled rather than simply waiting for a poll-request.

        The thread places output into a circular list of parsed messages stored as
        dictionaries containing the response itself, the datetime of the response
        and the type of response.  The other methods normally only access the most current report.
        """

        # init
        serial_errors = 0
        sleep_time = self._thread_sleep

        # loop until closing
        while not self._closing.is_set():
            # get serial connection
            if self._conn is None:
                logging.info('connecting to Boltwood II sensor')
                try:
                    # connect
                    self._connect_serial()

                    # reset sleep time
                    serial_errors = 0
                    sleep_time = self._thread_sleep

                except serial.SerialException as e:
                    # if no connection, log less often
                    serial_errors += 1
                    if serial_errors % 10 == 0:
                        if sleep_time < self._max_thread_sleep:
                            sleep_time *= 2
                        else:
                            sleep_time = self._thread_sleep

                    # do logging
                    logging.critical('%d failed connections to Boltwood II: %s, sleep %d',
                                     serial_errors, str(e), sleep_time)

            # actually read next line and process it
            if self._conn is not None:
                # read data
                raw_data = self._conn.readline()

                # sometimes the response starts with '/x00', cut that away
                if raw_data.startswith(b'\x00'):
                    raw_data = raw_data[1:]

                # analyse it
                self._analyse_message(raw_data)

            # sleep a little
            self._closing.wait(sleep_time)

        # close connection
        self._conn.close()

    def _connect_serial(self):
        """Open/reset serial connection to sensor."""

        # close first?
        if self._conn is not None and self._conn.is_open:
            self._conn.close()

        # create serial object
        self._conn = serial.Serial(self._port, self._baudrate,
                                   bytesize=self._bytesize, parity=self._parity,
                                   stopbits=self._stopbits, timeout=self._serial_timeout,
                                   rtscts=self._rtscts)

        # open it
        if not self._conn.is_open:
            self._conn.open()

        # ask for data
        self._send_poll_request()

    def _analyse_message(self, raw_data):
        """Analyse raw message.

        Args:
            raw_data: Raw data.

        Returns:

        """

        # no data?
        if len(raw_data) == 0 or raw_data == b'\n':
            # resend poll request
            self._send_poll_request()
            return

        # get response type
        tmp = raw_data.split()[0]
        try:
            response_type = ResponsePrefix(tmp)
        except ValueError:
            logging.critical('Could not determine response type %s.', tmp)
            return

        # what type is it?
        if response_type == ResponsePrefix.POLLING:
            # resend polling request
            self._send_poll_request()

        elif response_type == ResponsePrefix.REPORT:
            # create report
            report = Report(raw_data)

            # send it?
            if self._callback is not None:
                self._callback(report)

    def _send_poll_request(self):
        """Ask sensor for data."""
        self._conn.write(REQUEST_POLL)


__all__ = ['BoltwoodII', 'Report']
