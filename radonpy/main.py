#!/usr/bin/env python3
import argparse
import asyncio
import logging
import sys
import time
import urllib.parse
from typing import Optional
import json

import aiohttp
import aioinflux
import ssl

import radonpy

_logger = logging.getLogger(__name__)


async def run_measure(args, device):
    measurement = await device.measurement
    print(json.dumps({
        'current_value': measurement.read_value,
        'day_value': measurement.day_value,
        'month_value': measurement.month_value,
        'pulse_count': measurement.pulse_count,
        'pulse_count_10_min': measurement.pulse_count_10_min
    }))


async def run_config(args, device):
    if args.unit:
        await device.set_unit(radonpy.Unit.PCI_L if args.unit == 'pci' else radonpy.Unit.BQ_M3)


async def run_influxdb(args, device):
    url = urllib.parse.urlsplit(args.url, scheme='', allow_fragments=False)

    if url.scheme == 'http':
        use_tls = False
    elif url.scheme == 'https':
        use_tls = True
    else:
        _logger.critical("invalid URL scheme: %s", url.scheme)
        sys.exit(2)

    kwargs = {}

    if args.tls_certificate is not None or args.tls_key is not None:
        if args.tls_certificate is None or args.tls_key is None:
            _logger.critical(
                "--tls-certificate and --tls-key must all be specified to use client certificate "
                "authentication")
            sys.exit(2)
        ssl_context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(args.tls_certificate, args.tls_key)
        kwargs.update(connector=aiohttp.TCPConnector(ssl_context=ssl_context))

    url_path = url.path
    if url_path == '':
        url_path = '/'
    async with aioinflux.client.InfluxDBClient(host=url.hostname, port=url.port, path=url_path, ssl=use_tls,
                                               database=args.database, username=args.username, password=args.password,
                                               **kwargs) as client:
        next_time = time.time()
        while True:
            measurement = None
            try:
                if not await device.connected:
                    # Needed to clean up some things from the previous connection
                    await device.disconnect()
                    await device.connect()
                measurement = await device.measurement
            # bleak has poor exception handling, so pretty much anything can be thrown
            except BaseException as e:
                _logger.error("failed to read radon measurement", exc_info=e)

            if measurement is not None:
                fields = {
                    'current_value': measurement.read_value,
                    'day_value': measurement.day_value,
                    'month_value': measurement.month_value,
                    'pulse_count': measurement.pulse_count,
                    'pulse_count_10_min': measurement.pulse_count_10_min
                }
                for field in args.exclude_field:
                    fields.pop(field, None)
                try:
                    await client.write({
                        'time': '',
                        'measurement': 'radon',
                        'tags': {
                            'model': await device.model_name,
                            'serial': (await device.serial).serial,
                            'address': device.address
                        },
                        'fields': fields
                    })
                except aioinflux.InfluxDBWriteError as e:
                    _logger.error("failed to write to InfluxDB", exc_info=e)

            next_time += args.interval
            await asyncio.sleep(next_time - time.time())


async def run():
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser()
    parser.add_argument('--adapter', help="Name or address of Bluetooth adapter")
    parser.add_argument('-a', '--address', help="Bluetooth address of RadonEye RD200 device")
    command_parsers = parser.add_subparsers(dest='command', required=True)

    measure_parser = command_parsers.add_parser('measure')

    config_parser = command_parsers.add_parser('config')
    config_parser.add_argument('--unit', choices=['pci', 'bq'], help="Radon unit shown on device screen")

    influxdb_parser = command_parsers.add_parser('influxdb')
    influxdb_parser.add_argument('--interval', type=float, default=10 * 60,
                                 help="Interval between measurements in seconds")
    influxdb_parser.add_argument('--exclude-field', action='append', default=[],
                                 help="Exclude a field from the InfluxDB measurement")
    influxdb_parser.add_argument('--url', required=True, help="InfluxDB server URL")
    influxdb_parser.add_argument('--database', default='radoneye', help="InfluxDB database")
    influxdb_parser.add_argument('--username', default='radoneye', help="InfluxDB username")
    influxdb_parser.add_argument('--password', default='', help="InfluxDB password")
    influxdb_parser.add_argument('--tls-certificate', help="InfluxDB client authentication certificate")
    influxdb_parser.add_argument('--tls-key', help="InfluxDB client authentication key")

    args = parser.parse_args()

    device: Optional[radonpy.RD200] = None
    if args.address is None:
        async for device in radonpy.RD200.discover(adapter=args.adapter):
            break
    else:
        device = radonpy.RD200(args.address, adapter=args.adapter)

    if device is None:
        _logger.critical("failed to find RadonEye RD200")
        sys.exit(1)

    _logger.info(f"found RadonEye RD200: {device.address}")

    await device.connect()

    if args.command == 'measure':
        await run_measure(args, device)
    if args.command == 'config':
        await run_config(args, device)
    elif args.command == 'influxdb':
        await run_influxdb(args, device)


def main():
    asyncio.run(run())
