from enum import Enum


REQUEST_POLL = b'\x01'
FRAME_START = b'\x02'
FRAME_END = b'\n'


class CommandChar(Enum):
    POLL = b'P'
    ACK = b'A'
    NACK = b'N'
    MSG = b'M'


class ReportType(Enum):
    THERMO_CALIB = b'C'
    SENSORS = b'D'
    WETNESS_CALIB = b'K'
    THRESHOLD = b'T'
    WETNESS = b'W'


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
