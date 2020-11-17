import logging
import time
import serial
import threading

from . import api
from .report import Report, SensorsReport


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
        last_report = None
        raw_data = b''

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
                    self._closing.wait(sleep_time)

            # actually read next line and process it
            if self._conn is not None:
                # read data
                raw_data += self._conn.read()

                # extract messages
                msgs, raw_data = self._extract_messages(raw_data)

                # analyse it
                for msg in msgs:
                    self._analyse_message(msg)
                    last_report = time.time()

                # no report in a long time?
                if last_report is not None:
                    # TODO: This doesn't seem to be a perfect solution, since we now always get a wait time
                    #       after MT/MK/MW/MC packages
                    if time.time() - last_report > 10:
                        self._send_poll_request()

        # close connection
        self._conn.close()

    def _extract_messages(self, raw_data) -> (list, bytearray):
        """ Extract all complete messages from the raw data from the Boltwood.

        Args:
            raw_data: bytearray from Boltwood (via serial.readline())

        Returns:
            List of messages and remaining raw data.

        Normally, there should just be a single message per readline, but....
        """

        # nothing?
        if not raw_data:
            return [], b''

        # find complete messages
        msgs = []
        while api.FRAME_END in raw_data:
            # get message
            pos = raw_data.index(b'\n')
            msg = raw_data[:pos + 1]

            # sometimes the response starts with '/x00', cut that away
            if msg.startswith(b'\x00'):
                msg = msg[1:]

            # store it
            msgs.append(msg)

            # remove from raw_data
            raw_data = raw_data[pos + 1:]

        # return new raw_data and messages
        return msgs, raw_data

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

        # get frame
        # need to compare ranges, because an index into a bytesarray gives an integer, not a byte!
        if raw_data[:1] != api.FRAME_START or raw_data[-1:] != api.FRAME_END:
            logging.warning('Invalid frame found.')
            return
        frame = raw_data[1:-1]

        # get command
        try:
            command = api.CommandChar(frame[:1])
        except ValueError:
            logging.error('Invalid command character found: %s', frame[:1])
            return

        # what do we do with this?
        if command == api.CommandChar.POLL:
            # acknowledge it
            self._send_ack()

        elif command == api.CommandChar.ACK:
            # do nothing
            pass

        elif command == api.CommandChar.NACK:
            # do nothing
            pass

        elif command == api.CommandChar.MSG:
            # parse report
            try:
                report = Report.parse_report(raw_data)
            except ValueError as e:
                logging.error(str(e))
                return

            # send it?
            if self._callback is not None:
                self._callback(report)

    def _send_ack(self):
        """Send ACK."""

        # send ACK + new poll request
        self._conn.write(api.FRAME_START + api.CommandChar.ACK.value + api.FRAME_END + api.REQUEST_POLL)

    def _send_poll_request(self):
        """Ask sensor for data."""
        self._conn.write(api.REQUEST_POLL)


__all__ = ['BoltwoodII', 'Report']
