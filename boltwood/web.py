import argparse
import datetime
import json
import os
import tornado.ioloop
import tornado.web
import tornado.httpserver
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

from boltwood.report import AverageSensorsReport, SensorsReport, ThresholdReport, WetnessReport, WetnessCalibReport, \
    ThermopileCalibReport
from .boltwood import BoltwoodII, Report


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        app: Application = self.application
        self.render(os.path.join(os.path.dirname(__file__), 'template.html'),
                    current=app.current, history=app.history, thresholds=app.thresholds, wetness=app.wetness,
                    wetness_calib=app.wetness_calib, thermo_calib=app.thermo_calib)


class JsonHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header('Content-Type', 'application/json')

    def get(self, which):
        """JSON output of data.

        Args:
            which: "current" or "average".

        Returns:
            JSON output.
        """

        # get record
        if which == 'current':
            record = self.application.current
        elif which == 'average':
            record = self.application.average
        else:
            raise tornado.web.HTTPError(404)

        # get data
        data = {'time': record.time.strftime('%Y-%m-%d %H:%M:%S')}
        for c in ['T_ambient', 'humidity', 'windspeed', 'dT_sky', 'raining']:
            data[c] = record.data[c] if c in record.data else 'N/A'

        # send to client
        self.write(json.dumps(data))


class Application(tornado.web.Application):
    def __init__(self, log_file: str = None, *args, **kwargs):
        # static path
        static_path = os.path.join(os.path.dirname(__file__), 'static_html/')

        # init tornado
        tornado.web.Application.__init__(self, [
            (r'/', MainHandler),
            (r'/(.*).json', JsonHandler),
            (r'/static/(.*)', tornado.web.StaticFileHandler, {'path': static_path})
        ])

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
        if self.log_file is None:
            return

        # open file
        with open(self.log_file, 'r') as csv:
            # check header
            if csv.readline() != 'time,T_ambient,humidity,windspeed,dT_sky,raining\n':
                logging.error('Invalid log file format.')
                return

            # read lines
            for line in csv:
                # split and check
                s = line.split(',')
                if len(s) != 6:
                    logging.error('Invalid log file format.')
                    continue

                # create report and fill it
                report = AverageSensorsReport([])
                report.time = datetime.datetime.strptime(s[0], '%Y-%m-%d %H:%M:%S')
                report.data = {
                    'ambientTemperature': float(s[1]),
                    'relativeHumidityPercentage': float(s[2]),
                    'windSpeed': float(s[3]),
                    'skyMinusAmbientTemperature': float(s[4]),
                    'rainSensor': bool(s[5]),
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

        # write to log file?
        if self.log_file is not None:
            # does it exist?
            if not os.path.exists(self.log_file):
                # write header
                with open(self.log_file, 'w') as csv:
                    csv.write('time,T_ambient,humidity,windspeed,dT_sky,raining\n')

            # write line
            with open(self.log_file, 'a') as csv:
                fmt = '{time},' \
                      '{ambientTemperature:.2f},' \
                      '{relativeHumidityPercentage:.2f},' \
                      '{windSpeed:.2f},' \
                      '{skyMinusAmbientTemperature:.2f},' \
                      '{rainSensor}\n'
                csv.write(fmt.format(time=average.time.strftime('%Y-%m-%d %H:%M:%S'), **average.data))

        # reset reports
        self.reports = []


def main():
    # parser
    parser = argparse.ArgumentParser('Boltwood II cloud sensor web interface')
    parser.add_argument('--http-port', type=int, help='HTTP port for web interface', default=8888)
    parser.add_argument('--port', type=str, help='Serial port to BWII', default='/dev/ttyUSB0')
    parser.add_argument('--baudrate', type=int, help='Baud rate', default=4800)
    parser.add_argument('--bytesize', type=int, help='Byte size', default=8)
    parser.add_argument('--parity', type=str, help='Parity bit', default='N')
    parser.add_argument('--stopbits', type=int, help='Number of stop bits', default=1)
    parser.add_argument('--rtscts', type=bool, help='Use RTSCTS?', default=False)
    parser.add_argument('--log-file', type=str, help='Log file for average values')
    args = parser.parse_args()

    # create Boltwood II sensor object
    bw2 = BoltwoodII(**vars(args))

    # init app
    application = Application(**vars(args))

    # start polling
    bw2.start_polling(application.bw2_callback)

    # init tornado web server
    http_server = tornado.httpserver.HTTPServer(application)
    http_server.listen(8888)

    # scheduler
    sched = BackgroundScheduler()
    trigger = CronTrigger(minute='*/5')
    sched.add_job(application.sched_callback, trigger)
    sched.start()

    # start loop
    try:
        tornado.ioloop.IOLoop.current().start()
    except KeyboardInterrupt:
        pass

    # stop polling
    bw2.stop_polling()
    sched.shutdown()


if __name__ == '__main__':
    main()
