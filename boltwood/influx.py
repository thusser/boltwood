import queue
import threading
from typing import Optional

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from boltwood.report import Report, SensorsReport


FIELDS = {
    "ambientTemperature": "temp",
    "relativeHumidityPercentage": "humid",
    "windSpeed": "windspeed",
    "skyMinusAmbientTemperature": "skytemp",
    "rainSensor": "rain",
}


class Influx:
    def __init__(
        self,
        url: Optional[str] = None,
        token: Optional[str] = None,
        org: Optional[str] = None,
        bucket: Optional[str] = None,
    ):
        # init db connection
        self._client: Optional[InfluxDBClient] = None
        self._bucket: Optional[str] = None
        if url is not None and token is not None and org is not None and bucket is not None:
            self._client = InfluxDBClient(url=url, token=token, org=org)
            self._bucket = bucket

        # init queue
        self._queue = queue.Queue()

        # thread
        self._closing = threading.Event()
        self._thread = threading.Thread(target=self._send_measurements)

    def start(self):
        """Start thread."""
        self._thread.start()

    def stop(self):
        """End thread."""
        self._closing.set()
        self._thread.join()

    def __call__(self, report: Report):
        """Put a new measurement in the send queue."""
        if isinstance(report, SensorsReport):
            self._queue.put(report)

    def _send_measurements(self):
        """Run until closing to send reports."""

        # get API
        write_api = self._client.write_api(SYNCHRONOUS)

        # run (almost) forever
        while not self._closing.is_set():
            # get next report to send
            report = self._queue.get()

            # get data
            time = report.time.strftime("%Y-%m-%dT%H:%M:%SZ")
            fields = {val: report.data[key] if key in report.data else None for key, val in FIELDS.items()}

            # send it
            write_api.write(bucket=self._bucket, record={"measurement": "boltwood", "fields": fields, "time": time})
