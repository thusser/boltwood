# Web interface for Boltwood II cloud sensor
This package provides the serial connection and a web interface for the Boltwood II cloud sensor.


## Installation
Clone repository:

    https://github.com/thusser/boltwood.git
    
And install it:

    pip3 install .


## Usage
Simply run `bw2web` command to start with default settings. Use `-h` parameter to show command line parameters:

    usage: Boltwood II cloud sensor web interface [-h] [--http-port HTTP_PORT] [--port PORT] [--baudrate BAUDRATE] [--bytesize BYTESIZE] [--parity PARITY] [--stopbits STOPBITS] [--rtscts RTSCTS] [--log-file LOG_FILE]

    optional arguments:
      -h, --help            show this help message and exit
      --http-port HTTP_PORT
                            HTTP port for web interface
      --port PORT           Serial port to BWII
      --baudrate BAUDRATE   Baud rate
      --bytesize BYTESIZE   Byte size
      --parity PARITY       Parity bit
      --stopbits STOPBITS   Number of stop bits
      --rtscts RTSCTS       Use RTSCTS?
      --log-file LOG_FILE   Log file for average values


## Authors
* Tim-Oliver Husser <thusser@uni-goettingen.de>
* Frederic V. Hessman
