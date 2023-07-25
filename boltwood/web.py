import argparse
import asyncio
import datetime
import json
import os
from typing import Optional

import aiohttp_jinja2
import jinja2
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
from aiohttp import web

from boltwood.report import (
    AverageSensorsReport,
    SensorsReport,
    ThresholdReport,
    WetnessReport,
    WetnessCalibReport,
    ThermopileCalibReport,
)
from boltwood.boltwood2 import BoltwoodII, Report


class Application:
    def __init__(self, log_file: str = None, *args, **kwargs):
        # static path
        static_path = os.path.join(os.path.dirname(__file__), "static_html/")

        # define web server
        self._app = web.Application()
        self._app.add_routes(
            [
                web.get("/", self.main_handler),
                web.get("/{filename}.json", self.json_handler),
                web.static("/static", static_path),
            ]
        )
        aiohttp_jinja2.setup(
            self._app, loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates"))
        )
        self._runner = web.AppRunner(self._app)
        self._site: Optional[web.TCPSite] = None

        # init other stuff
        self.current = None
        self.reports = []
        self.history = []
        self.log_file = log_file
        self.thresholds = None
        self.wetness = None
        self.wetness_calib = None
        self.thermo_calib = None

        # load history
        self._load_history()

    async def start_listening(self, port: int):
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", port)
        await self._site.start()

    @aiohttp_jinja2.template("template.jinja2")
    async def main_handler(self, request: web.Request) -> dict:
        return dict(
            current=self.current,
            history=self.history,
            thresholds=self.thresholds,
            wetness=self.wetness,
            wetness_calib=self.wetness_calib,
            thermo_calib=self.thermo_calib,
        )

    async def json_handler(self, request: web.Request) -> web.Response:
        """JSON output of data.

        Args:
            which: "current" or "average".

        Returns:
            JSON output.
        """

        # get record
        which = "a"
        if which == "current":
            record = self.current
        elif which == "average":
            record = self.average
        else:
            raise web.HTTPNotFound

        # get data
        data = {"time": record.time.strftime("%Y-%m-%d %H:%M:%S")}
        for c in [
            "ambientTemperature",
            "relativeHumidityPercentage",
            "windSpeed",
            "skyMinusAmbientTemperature",
            "rainSensor",
        ]:
            data[c] = record.data[c] if c in record.data else "N/A"

        # send to client
        return web.Response(text=json.dumps(data), content_type="application/json")

    @property
    def average(self):
        return self.history[0] if len(self.history) > 0 else Report()

    def bw2_callback(self, report):
        # store report
        if isinstance(report, SensorsReport):
            self.current = report
            self.reports.append(report)
        elif isinstance(report, ThresholdReport):
            self.thresholds = ThresholdReport
        elif isinstance(report, WetnessReport):
            self.wetness = report
        elif isinstance(report, WetnessCalibReport):
            self.wetness_calib = report
        elif isinstance(report, ThermopileCalibReport):
            self.thermo_calib = report

    def _load_history(self):
        """Load history from log file"""

        # no logfile?
        if self.log_file is None or not os.path.exists(self.log_file):
            return

        # open file
        with open(self.log_file, "r") as csv:
            # check header
            if csv.readline() != "time,T_ambient,humidity,windspeed,dT_sky,raining\n":
                logging.error("Invalid log file format.")
                return

            # read lines
            for line in csv:
                # split and check
                s = line.split(",")
                if len(s) != 6:
                    logging.error("Invalid log file format.")
                    continue

                # create report and fill it
                report = AverageSensorsReport([])
                report.time = datetime.datetime.strptime(s[0], "%Y-%m-%dT%H:%M:%S")
                report.data = {
                    "ambientTemperature": float(s[1]),
                    "relativeHumidityPercentage": float(s[2]),
                    "windSpeed": float(s[3]),
                    "skyMinusAmbientTemperature": float(s[4]),
                    "rainSensor": s[5] == "True",
                }
                self.history.append(report)

        # crop
        self._crop_history()

    def _crop_history(self):
        # sort history
        self.history = sorted(self.history, key=lambda h: h.time, reverse=True)

        # crop to 10 entries
        if len(self.history) > 10:
            self.history = self.history[:10]

    def sched_callback(self):
        # average reports
        average = AverageSensorsReport(self.reports)
        self.history.append(average)
        self._crop_history()

        # write to log file?
        if self.log_file is not None:
            # does it exist?
            if not os.path.exists(self.log_file):
                # write header
                with open(self.log_file, "w") as csv:
                    csv.write("time,T_ambient,humidity,windspeed,dT_sky,raining\n")

            # write line
            with open(self.log_file, "a") as csv:
                fmt = (
                    "{time},"
                    "{ambientTemperature:.2f},"
                    "{relativeHumidityPercentage:.2f},"
                    "{windSpeed:.2f},"
                    "{skyMinusAmbientTemperature:.2f},"
                    "{rainSensor}\n"
                )
                csv.write(fmt.format(time=average.time.strftime("%Y-%m-%dT%H:%M:%S"), **average.data))

        # reset reports
        self.reports = []


async def main():
    # parser
    parser = argparse.ArgumentParser("Boltwood II cloud sensor web interface")
    parser.add_argument("--http-port", type=int, help="HTTP port for web interface", default=8888)
    parser.add_argument("--port", type=str, help="Serial port to BWII", default="/dev/ttyUSB0")
    parser.add_argument("--baudrate", type=int, help="Baud rate", default=4800)
    parser.add_argument("--bytesize", type=int, help="Byte size", default=8)
    parser.add_argument("--parity", type=str, help="Parity bit", default="N")
    parser.add_argument("--stopbits", type=int, help="Number of stop bits", default=1)
    parser.add_argument("--rtscts", type=bool, help="Use RTSCTS?", default=False)
    parser.add_argument("--log-file", type=str, help="Log file for average values")
    args = parser.parse_args()

    # create Boltwood II sensor object
    bw2 = BoltwoodII(**vars(args))

    # init app
    application = Application(args.log_file)
    await application.start_listening(args.http_port)

    # start polling
    await bw2.start_polling(application.bw2_callback)

    # scheduler
    sched = AsyncIOScheduler()
    trigger = CronTrigger(minute="*/5")
    sched.add_job(application.sched_callback, trigger)
    sched.start()

    # start loop
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.exceptions.CancelledError:
        pass

    # stop polling
    await bw2.stop_polling()
    sched.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
