#!/usr/bin/env python3
import argparse
import asyncio
import datetime
import json
import logging
import ssl
import sys
import time
import urllib.parse
from typing import Optional, Union

import aiohttp
import aioinflux
from bleak.backends.device import BLEDevice

import radonpy

_logger = logging.getLogger(__name__)


async def run_measure(args, device: radonpy.RD200):
    measurement = await device.measurement
    print(json.dumps({
        'current_value': measurement.read_value,
        'day_value': measurement.day_value,
        'month_value': measurement.month_value,
        'pulse_count': measurement.pulse_count,
        'pulse_count_10_min': measurement.pulse_count_10_min
    }))


async def run_log(args, device: radonpy.RD200):
    print(json.dumps(await device.get_log()))


async def run_config(args, device: radonpy.RD200):
    if args.unit:
        await device.set_unit(radonpy.Unit.PCI_L if args.unit == 'pci' else radonpy.Unit.BQ_M3)


async def run_influxdb(args, device: radonpy.RD200):
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
        tags = {
            'model': await device.model_name,
            'serial': (await device.serial).serial,
            'address': device.address
        }

        if args.import_log:
            await run_influxdb_import_log(device, client, tags)
        else:
            await run_influxdb_normal(args, device, client, tags)


async def run_influxdb_import_log(device: radonpy.RD200, client: aioinflux.InfluxDBClient, tags: dict):
    log = await device.get_log()

    now = datetime.datetime.now(tz=datetime.timezone.utc)

    def map_point(item):
        i = item[0]
        value = item[1]
        delta = datetime.timedelta(hours=len(log) - i)
        return {
            'time': now - delta,
            'measurement': 'radon',
            'tags': tags,
            'fields': {
                'current_value': value,
            }
        }

    points = map(map_point, enumerate(log))
    await client.write(points)


async def run_influxdb_normal(args, device: radonpy.RD200, client: aioinflux.InfluxDBClient, tags: dict):
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
                    'tags': tags,
                    'fields': fields
                })
            except (aioinflux.InfluxDBWriteError, aiohttp.ClientError) as e:
                _logger.error("failed to write to InfluxDB", exc_info=e)

        next_time += args.interval
        await asyncio.sleep(next_time - time.time())


async def run():
    logging.basicConfig(level=logging.WARNING)

    parser = argparse.ArgumentParser()
    parser.add_argument('--adapter', default='hci0', help="Name or address of Bluetooth adapter")
    parser.add_argument('-a', '--address', help="Bluetooth address of RadonEye RD200 device")
    command_parsers = parser.add_subparsers(dest='command', required=True)

    measure_parser = command_parsers.add_parser('measure')

    log_parser = command_parsers.add_parser('log')

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
    influxdb_parser.add_argument('--import-log', action='store_true',
                                 help="Import device log into InfluxDB instead of logging real-time measurements")

    args = parser.parse_args()

    device_info: Optional[Union[BLEDevice, str]] = None
    if args.address is None:
        async for device_info in radonpy.RD200.discover(adapter=args.adapter):
            break
    else:
        device_info = args.address

    if device_info is None:
        _logger.critical("failed to find RadonEye RD200")
        sys.exit(1)

    async with radonpy.RD200(device_info, adapter=args.adapter) as device:
        _logger.info(f"found RadonEye RD200: {device.address}")

        if args.command == 'measure':
            await run_measure(args, device)
        elif args.command == 'log':
            await run_log(args, device)
        elif args.command == 'config':
            await run_config(args, device)
        elif args.command == 'influxdb':
            await run_influxdb(args, device)


def main():
    asyncio.run(run())
