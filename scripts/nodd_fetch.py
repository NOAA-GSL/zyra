#!/usr/bin/env python3

# Copyright (c) 2021-2024 NOAA ESRL Global Systems Laboratory
# Distributed under the terms of the MIT License.
# SPDX-License-Identifier: MIT

'''
Description
###########
 
:synopsis: Fetch products from the NOAA Open Data Dissemination (NODD) Program, or other sources
:usage: >>> ./nodd_fetch.py <product> <product_type> <options>
        >>> ./nodd_fetch.py -h

============ =========================================================================
``product:`` product_type
============ =========================================================================
hrrr         subh or prs for: subhourly or pressure; - defaults to surface ('sfc')
gfs          half for: half degree; - defaults to .25 degree ('0p25')
rrfs         prs or test for: prslev, testbed; - defaults to natlev
blend        defaults to core
rap          defaults to prs
gefs         defaults to half degree (0p50)
============ =========================================================================

Dataset Information
###################

- https://www.noaa.gov/nodd/datasets#NWS # NWS products in the NOAA Open Data Dissemination Program
- https://registry.opendata.aws/noaa-hrrr-pds/    # HRRR - High-Resolution Rapid Refresh
- https://registry.opendata.aws/noaa-gfs-bdp-pds/ # GFS  - Global Forecast System
- https://registry.opendata.aws/noaa-rrfs/        # RRFS - Rapid Refresh Forecast System
- https://registry.opendata.aws/noaa-nbm/         # NBM  - National Blend of Models
- https://registry.opendata.aws/noaa-rap/         # RAP  - Rapid Refresh
- https://registry.opendata.aws/noaa-gefs/        # GEFS - Global Ensemble Forecast System
- https://registry.opendata.aws/noaa-mrms-pds/    # MRMS - Multi-Radar/Multi-Sensor System
- https://registry.opendata.aws/noaa-nws-hafs/    # HAFS - Hurricane Analysis and Forecast System
- https://registry.opendata.aws/noaa-ofs/         # OFS  - Operational Forecast System 
- https://github.com/awslabs/open-data-registry   # open data registry on AWS

- data available from other web or ftp sources (see nodd_data.py for extended datasets)
- https://data.nssl.noaa.gov/   # HREF - High Resolution Ensemble Forecast System - hiresw_conusarw files
- https://nomads.ncep.noaa.gov/ # Rap Obs via NOMADS https - wrfnat files
- ftp://ftp.ncep.noaa.gov/      # RAP Obs via NCEP ftp - awp130bgrb files

Command line examples 
#####################
Retrieve the current data (for the latest cycle/run)::

./nodd_fetch.py hrrr prs                                # pull the latest hrrr pressure files
./nodd_fetch.py gfs --dest /data/downloads/             # pull the latest 0p25 GFS, to my dest
./nodd_fetch.py blend --vars ''                         # pull the latest core blend, full files
./nodd_fetch.py hrrr subh --cleanup --vars 'DSWRF'      # pull just the dswrf var from the subhourly hrrr
./nodd_fetch.py hrrr --fcsts 0 1 12 --vars 'FRICV|HPBL' # just these vars and forecasts from the surface hrrr
./nodd_fetch.py gfs half --idx                          # pull the latest half deg GFS, plus the idx files
./nodd_fetch.py rrfs prs --dryrun                       # show which latest rrfs pressure files would be pulled

Go back a few cycles::

./nodd_fetch.py rrfs prs -b 1                           # pull from 1 cycle back to the latest
./nodd_fetch.py --conf nodd_data glofs lmhofs -b 3      # pull from 3 cycles back to the latest

Archive case (provide start and end datetimes - defaults to one cycle if no end)::

./nodd_fetch.py gfs half --start 2022-11-26-18          # --end defaults to the next cycle
./nodd_fetch.py hrrr subh --vars 'DSWRF' --start 2024-04-08-09 --end 2024-04-08-12
./nodd_fetch.py hrrr --vars 'FRICV|HPBL' --fcsts 0 1 12 --start 2023-01-01 --end 2023-12-31
./nodd_fetch.py gefs half --start 2023-07-05-12 --dest /data/archives/ --mems 1 2 3 --fcsts 63
./nodd_fetch.py rrfs prs --path conus --start 2024-05-07-00

Tool for exploring product options (and fetching idx for review)::

./nodd_fetch.py explore                                 # explore the default common datasets
./nodd_fetch.py --conf nodd_data explore # explore the default, plus some auxiliary datasets 

Supported Products
##################
**For HRRR**, the default product type is surface (sfc); 18th hr fcst arrives ~90 minutes past hourly runtime,
48th hr arrives ~115 minutes past

cron::

  35-55/5 * * * * /bin/nodd_fetch.py hrrr subh -l log/nodd_fetch.hrrr_subh.`date +\\%Y\\%m\\%d`.log

sample HRRR filename options below (sample dir: hrrr.20230508/conus/)::

  hrrr.t21z.wrfsfcf09.grib2  # default to surface levels
  hrrr.t02z.wrfsubhf15.grib2 # sub-hourly (every 15 minutes)
  hrrr.t04z.wrfprsf07.grib2  # pressure levels

**For GFS**, the default product type is .25 degree (0p25); 120th hr fcst arrives ~4:10 past 6-hourly runtime

cron::

  35-55/5 4,10,16,22 * * * /bin/nodd_fetch.py gfs -l log/nodd_fetch.gfs.`date +\\%Y\\%m\\%d`.log

sample GFS filename options below (sample dir: gfs.20211117/12/atmos/)::
  
  gfs.t12z.goessimpgrb2.0p25.f003
  gfs.t12z.pgrb2.0p25.f003     # default to quarter degree resolution
  gfs.t12z.pgrb2.0p50.f003     # half degree resolution
  gfs.t12z.pgrb2.1p00.f003     # one degree resolution
  gfs.t12z.pgrb2b.0p25.f003    # quarter degree part b
  gfs.t12z.pgrb2b.0p50.f003    # half degree part b
  gfs.t12z.pgrb2b.1p00.f003    # one degree part b
  gfs.t12z.pgrb2full.0p50.f003 # Concatenation of pgrb2.0p50 and pgrb2b.0p50

**For Blend**, the default product type is core; run at least 15 minutes past the hour

cron::

  35-45/5 * * * * /bin/nodd_fetch.py blend -l log/nodd_fetch/blend/`date +\\%Y\\%m\\%d`.core.log

sample BLEND filename options below::

  blend.20211117/04/core/blend.t04z.core.f242.co.grib2

**For RRFS**, the default product type is natlev; run hourly product at least 40 minutes past the hour

cron::

  41 * * * * /bin/nodd_fetch.py rrfs_hr prs -b 1 --dest /data -l log/nodd_fetch/rrfs_hr/`date +\\%Y\\%m\\%d_\\%H\\%M`.prs.log
  45 2,8,14,20 * * * /bin/nodd_fetch.py rrfs_ens test -b 1 --dest /data -l log/nodd_fetch/rrfs_ens/`date +\\%Y\\%m\\%d_\\%H\\%M`.test.log
  17 5,11,17,23 * * * /bin/nodd_fetch.py rrfs --dest /data -l log/nodd_fetch/rrfs/`date +\\%Y\\%m\\%d_\\%H\\%M`.nat.log

sample RRFS path options:: 

  rrfs_a/rrfs_a.20240510/05/control/ # default
  rrfs_a/rrfs_a.20240510/06/mem0001/ # ensemble member 1
  rrfs_a/rrfs_a.20240510/18/mem0005/ # ensemble member 5

sample RRFS filename options below::

  rrfs.t17z.natlev.f017.grib2       # default to native levels
  rrfs.t17z.prslev.f006.conus.grib2 # pressure levels for the conus domain
  rrfs.t17z.testbed.f004.ak.grib2   # testbed files for the Alaska domain
  rrfs.t00z.m05.prslev.f060.conus.grib2 # pressure levels for the conus domain, ensemble member 5
 
**For RAP**, the default product type is prs; run at least 15 minutes past the hour

sample RAP filename options below (sample dir: rap.20240415/)::

  rap.t16z.wrfprsf01.grib2 # default pressure levels

**For GEFS**, the default product type is half (see nodd_data.py for extended datasets)

sample GEFS filename options below (sample dir: gefs.20240512/12/atmos/pgrb2bp5/)::

  gep03.t12z.pgrb2b.0p50.f384

**For GLOFS**, the default product type is Lake Erie (leofs)
  fcsts arrive ~ 121-150 minutes past 6-hourly runtime
   (see nodd_data.py for extended datasets)

cron::

  30 2,8,14,20 * * * /bin/nodd_fetch.py glofs -b 3 --conf nodd_data --dest /data/glofs/ -l log/nodd_fetch/glofs/`date +\\%Y\\%m\\%d_\\%H\\%M`.leofs.log

sample GLOFS filename options below (sample dir: leofs.20240528/)::

  nos.leofs.fields.f023.20240528.t06z.nc  # Lake Erie, default
  nos.lmhofs.fields.f004.20240528.t00z.nc # Lake Michigan-Huron
  nos.lmhofs.fields.f098.20240528.t12z.nc # Lake Ontario
  nos.lsofs.fields.f047.20240528.t18z.nc  # Lake Superior

**For HAFS**, the default product type is hfsa (see nodd_data.py for extended datasets)

cron::

  5 */6 * * * bin/nodd_fetch.py --conf nodd_data hafs b -d /data/hafs -b 1 -l log/nodd_fetch/hafs/`date +\\%Y\\%m\\%d_\\%H\\%M`.hafs_b_hycom.log

Code
####
'''

import os
import re
import sys
import time
import signal
import logging
import importlib
from io import BytesIO
from pathlib import Path
from functools import wraps
from typing import Iterable, Tuple
from collections import namedtuple
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from argparse import Action, ArgumentParser, Namespace

DESC = "Data retrieval tool for NODD (and other) products from aws (s3), http(s) or ftp"
DEFAULT_DEST = '/tmp/nodd_fetched' # default download destination, if not specified
SECS_TO_PURGE = 600 # purge files after they are this many seconds old, if '--clean' is used
PQINSERT_PATH = "/usr/local/ldm/bin/pqinsert"
# logger = logging.getLogger(Path(__file__).name) # default global logger

datasets_gsl = { # default metadata or configs for commonly fetched NODD datasets at GSL
  'hrrr': { 
    'name':            'NOAA High-Resolution Rapid Refresh (HRRR) Model',
    'source':          "noaa-hrrr-bdp-pds", # 'https://noaa-hrrr-bdp-pds.s3.amazonaws.com/'
    'types':           {'': 'sfc', 'subh': 'subh', 'prs': 'prs', 'nat': 'nat',},
    'last_run':        "{day:s}{prev_hr:s}",
    'key_pattern':     "hrrr.{day:s}/conus/hrrr.t{hr:02d}z.wrf{prod_type}f{fxx:02d}.grib2",
    'forecasts':       range(0,19), # range(49), # [0, 1, 12],
    'search_str':      'FRICV|HPBL', # Frictional velocity and Boundary layer height
    'search_str_subh': 'DSWRF', # Downward short-wave radiation flux (Solar Radiation)
    'search_str_prs':  'PRES:surface', # surface pressure
    'search_str_nat':  'GUST', # wind gust fields
  },
  'gfs': {
    'name':            'NOAA Global Forecast System (GFS)',
    'source':          "noaa-gfs-bdp-pds", # noaa-ndfd-pds
    'types':           {'': '0p25', 'half': '0p50'},
    'last_run':        "{day_sub3h:s}{last_gfs_run:s}",
    'key_pattern':     "gfs.{day:s}/{hr:02d}/atmos/gfs.t{hr:02d}z.pgrb2.{prod_type}.f{fxx:03d}",
    'ods_name':        '{day}_{hr:02d}00/{yyjjj}{hr:02d}000{fxx:03d}',
    'forecasts':       range(0,64), # range(0,119), # range(0,385),
    'search_str':      '(:TMP:surface|:PRATE:surface|:APCP:surface)',
  },
  'blend': {
    'name':         'NOAA National Blend of Models (NBM)',
    'source':       "noaa-nbm-grib2-pds",
    'types':        {'': 'core'},
    'last_run':     "{day:s}{prev_hr:s}",
    'key_pattern':  "blend.{day:s}/{hr:02d}/core/blend.t{hr:02d}z.core.f{fxx:03d}.co.grib2",
    'forecasts':    range(1,19),
    'search_str':   '(:TMP:surface|:WIND:surface|:WDIR:surface|:APCP:surface|:PTYPE:surface)',
  },
  'rrfs_hr': { # available to retrieve every hour
    'name':            'NOAA Rapid Refresh Forecast System (RRFS) - hourly runtimes',
    'source':          "noaa-rrfs-pds",
    'types':           {'': 'natlev', 'prs': 'prslev', 'test': 'testbed','fip': 'ififip',},
    'last_run':        "{two_hrs_back}",
    'path_def':        "ALTPATH", # the portion of the default path to replace if --path is specified
    'key_pattern':     "rrfs_a/rrfs_a.{day:s}/{hr:02d}/control/rrfs.t{hr:02d}z.{prod_type}.f{fxx:03d}.grib2",
    'key_pattern_alt': "rrfs_a/rrfs_a.{day:s}/{hr:02d}/control/rrfs.t{hr:02d}z.{prod_type}.f{fxx:03d}.ALTPATH.grib2",
    'forecasts':       range(0,19), # forecasts only go 18 hours out, usually
  },
  'rrfs': { # files are large, retrieve at the 6 hour mark
    'name':            'NOAA Rapid Refresh Forecast System (RRFS) - at 6 hour runtimes',
    'source':          "noaa-rrfs-pds",
    'types':           {'': 'natlev', 'prs': 'prslev', 'test': 'testbed','fip': 'ififip',},
    'last_run':        "{last_ofs_run}",
    'path_def':        "ALTPATH", # the portion of the default path to replace if --path is specified
    'key_pattern':     "rrfs_a/rrfs_a.{day:s}/{hr:02d}/control/rrfs.t{hr:02d}z.{prod_type}.f{fxx:03d}.grib2",
    'key_pattern_alt': "rrfs_a/rrfs_a.{day:s}/{hr:02d}/control/rrfs.t{hr:02d}z.{prod_type}.f{fxx:03d}.ALTPATH.grib2",
    'forecasts':       range(19,61), # rrfs control runs' forecasts go further every 6 hours
  },
  'rrfs_ens': { # only available at the 6 hour mark
    'name':            'NOAA Rapid Refresh Forecast System (RRFS) - Multi physics ensemble',
    'source':          "noaa-rrfs-pds",
    'types':           {'': 'prslev', 'test': 'testbed',},
    'last_run':        "{last_ofs_run}",
    'path_def':        "ALTPATH", # the portion of the default path to replace if --path is specified
    'key_pattern':     "rrfs_a/rrfs_a.{day:s}/{hr:02d}/mem{mem:04d}/rrfs.t{hr:02d}z.m{mem:02d}.{prod_type}.f{fxx:03d}.conus.grib2",
    'key_pattern_alt': "rrfs_a/rrfs_a.{day:s}/{hr:02d}/mem{mem:04d}/rrfs.t{hr:02d}z.m{mem:02d}.{prod_type}.f{fxx:03d}.ALTPATH.grib2",
    # ex: (6-hrly)     /rrfs_a/rrfs_a.20240530/18/mem0001/rrfs.t18z.m01.prslev.f001.conus.grib2.idx
    'forecasts':       range(0,61), # ensemble forecasts, every 6 hours
    'mems':            range(1,6),
  },
  'rap': { 
    'name':            'NOAA Rapid Refresh (RAP)',
    'source':          "noaa-rap-pds",
    'types':           {'': 'prs','nat': 'nat'},
    'last_run':        "{day:s}{prev_hr:s}", # "{two_hrs_back}",
    'key_pattern':     "rap.{day:s}/rap.t{hr:02d}z.wrf{prod_type}f{fxx:02d}.grib2",
    'forecasts':       range(0,19), # range(49),
    'search_str':      'REF', # radar reflectivity
  },
  'explore':           'Run a tool to explore available data sets',
}
'''Set the default metadata or configuration for commonly fetched NODD (or other) datasets.

A python dictionary stores our dataset information for a few default products\n

===================== ===============================================================================
``datasets``           a template for a product's configuration settings
===================== ===============================================================================
name                  the official product name
source                the product's source. An s3 bucket name. Or an http(s) or ftp URL
types                 define the possible types for this product
last_run              define this dataset's expected latest run time
key_pattern           the expected key/url format to generate for this day, hour, fcst
forecasts             the range of valid forecasts for this product and type
<optional below>      above info is required, below optional, when defining a new dataset
ods_name              the ODS path and file format to save files to (appended to dest)
search_str            a regular expression describing our variables and/or levels\n
                      Note that the command line argument for search_str is --vars
search_str_<type>     specify the variables and/or levels for the chosen product type
path_def              the portion of the default path to replace if --path is specified
key_pattern_alt       an alternate key_pattern with alternating (ALTPATH) sections
mems                  the range of ensemble members used (for GEFS and RRFS multi-physics)
===================== ===============================================================================

The search_str is what you'are looking for in each line of the grib index file. Focus on the variable and level fields.\n
Use regular expression syntax to customize your search.  Here are a few examples that can help you get started:\n
>>> wgrib2 <grib_file> -s | egrep <search_str> # a way to test / iterate

================ ===============================================
``search_str``   Messages that will be downloaded
================ ===============================================
':TMP:2 m'       Temperature at 2 m.
':TMP:'          Temperature fields at all levels.
':500 mb:'       All variables on the 500 mb level.
':APCP:'         All accumulated precipitation fields.
':UGRD:10 m:'    U wind component at 10 meters.
':(U|V)GRD:'     U and V wind component at all levels.
':.GRD:'         (Same as above)
':(TMP|DPT):'    Temperature and Dew Point for all levels .
':(TMP|DPT|RH):' TMP, DPT, and Relative Humidity for all levels.
':REFC:'         Composite Reflectivity
'',None,missing  Download the entire file, no subsetting
':surface:'      All variables at the surface.
================ ===============================================
'''

class AwsServer:
    '''Our interface for fetching from an AWS s3 server, using boto3'''
    def __init__(self, bucket:str):
        self.name = bucket # our AWS s3 bucket name
        self.URL = 's3://' + bucket + '/'
        self.register_s3()

    def register_s3(self):
        '''Register our boto3 s3 client used for (finding and) downloading products / files'''
        import boto3
        import botocore
        self.s3 = boto3.client('s3', region_name='us-east-2') # instantiate our s3 client
        self.s3.meta.events.register('choose-signer.s3.*', botocore.handlers.disable_signing)

    def catch_aws_exception(f):
        '''A decorator to catch any aws exceptions in other functions'''
        @wraps(f)
        def func(self, *fargs, **kwargs):
            from botocore.exceptions import ClientError
            try:
                return f(self, *fargs, **kwargs)
            except ClientError as e:
                if e.response['Error']['Code'] in ['404','NoSuchKey']:
                    logger.warning('Warning!! Couldn\'t find s3 bucket key - skipping download.')
                    if 'Key' in e.response["Error"]: logger.error(f'\t{e.response["Error"]["Key"]}')
                else:
                    logger.error("Error!! botocore ClientError occurred within an AwsServer method!",
                        e.__class__.__name__, e)
                    raise e
        return func

    @catch_aws_exception
    def download(self, obj_key:str, range_header:str = '') -> bytes:
        '''Download our AWS served file, using the range header if provided'''
        resp = self.s3.get_object(Bucket=self.name, Key=obj_key, Range=range_header)
        return resp['Body'].read()

    @catch_aws_exception
    def get_size(self, obj_key:str) -> int:
        '''Retrieve the file size in bytes for a given object key'''
        response = self.s3.head_object(Bucket=self.name, Key=obj_key)
        return response['ContentLength']

    @catch_aws_exception
    def get_matches(self, prefix: str, pattern: str) -> list:
        '''Get a list of files at the given URI prefix that match the given pattern'''
        logger.info(f'get_matches() with prefix {prefix} and looking for files matching {pattern}')
        check_prefix = str(Path(prefix)) # , pattern[:12]))
        paginator = self.s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=self.name,
            Prefix=check_prefix)  # Left PaginationConfig MaxItems & PageSize off intentionally
        results = pages.search( f"Contents[?contains(Key, `{pattern}`)][]")
                              # f"Contents[?Size > `MINSIZE`][]")
        wanted = [
            obj['Key']
            for obj in results
            if obj is not None and not obj['Key'].endswith('.idx')
        ]
        logger.debug(f'returning matches found: {wanted}')
        return wanted

class WebServer:
    '''Our interface for fetching from an HTTPS server, using urllib'''
    def __init__(self, server:str):
        self.name = server.split('/')[2] # strip off the protocol and any / uri path
        self.URL = server[:server.index('/') + 2] + self.name + '/'

    def catch_web_exception(f):
        '''A decorator to catch any web exceptions in other functions'''
        @wraps(f)
        def func(self, *fargs, **kwargs):
            from urllib.error import HTTPError
            try:
                return f(self, *fargs, **kwargs)
            except HTTPError as he:
                if he.code == 404:
                    logger.warning(f'Warning!! object url does not exist - skipping download for:\n\t{he.url}')
                else:
                    logger.error(f'Error!! urllib HTTPError occurred! code:{he.code}, errno:{he.errno}')
                    raise he
        return func

    @catch_web_exception
    def download(self, uri:str, range_header:str = '') -> bytes:
        '''Download our web served file, using the range header if provided'''
        from urllib.request import urlopen, Request
        req = Request(self.URL + uri)
        req.add_header('Range', range_header)
        with urlopen(req) as f:
            return f.read()

    @catch_web_exception
    def get_size(self, uri:str) -> int:
        '''Retrieve the file size in bytes for a given uri'''
        from urllib.request import urlopen
        with urlopen(self.URL + uri) as meta:
            return int(meta.info().get('Content-Length'))

class FtpServer(WebServer):
    '''Our interface for fetching from an FTP server, using pycurl'''
    def __init__(self, server:str):
        self.pycurl = __import__('pycurl')
        super().__init__(server)

    def download(self, uri:str, range_header:str = '') -> bytes:
        '''Download our ftp (or web) served file, using the range header if provided'''
        buffer = BytesIO()
        c = self.pycurl.Curl()
        c.setopt(c.URL, self.URL + uri)
        if range_header != '': # we have a byte range, let's use it
            c.setopt(c.RANGE, range_header.replace("bytes=",""))
        if args.verbose > 2: c.setopt(c.VERBOSE, True)
        c.setopt(c.WRITEDATA, buffer)
        try:
            c.perform()
        except self.pycurl.error as pe:
            error_code, message = pe.args
            if error_code in [9, 78]:
                logger.warning(f'Warning!! Could not retrieve ftp object. {message}. '
                      f'Skipping download for: \n\t{self.URL + uri}')
            else:
                logger.error(f'Error!! A pycurl error occurred! code:{error_code}, message: {message}')
                raise pe
        c.close()
        return buffer.getvalue()

class NoddServer:
    '''Provide some abstract server methods for Nodd (or other) served products'''
    def __init__(self, source:str, force_http:bool = False):
        '''Instantiate a server interface for our fetches, fall back to urllib, note if subsetting works'''
        if force_http and '://' not in source:
            source = 'https://' + source + '.s3.amazonaws.com/'
        try:
            if source.startswith('http'):
                self.server = WebServer(source)
            elif source.startswith('ftp'):
                self.server = FtpServer(source)
            else: # We're talking to an AWS server (or s3 bucket)
                self.server = AwsServer(source)
        except ModuleNotFoundError:
            self.logger.warning('!!WARNING!! The boto3 or pycurl module is missing, using urllib instead.')
            if not source.startswith('ftp'):
                source = 'https://' + source + '.s3.amazonaws.com/'
            self.server = WebServer(source)
        self.can_subset = True # enable grib field subsetting by default
        if (source.startswith('ftp') and not isinstance(self.server, FtpServer)):
            self.can_subset = False # only pycurl uses the range header for ftp sources

    def get_idx_lines(self, key:str, out_file:str = None, verbose:int = 0) -> list:
        '''Given an object key (assumed to be a grib file), retrieve and return its corresponding idx lines'''
        self.logger.debug(f'  getting idx from: {self.server.URL + key}.idx')
        idx_raw = self.server.download(key + '.idx')
        if idx_raw is None: return None # no idx found, no lines to return
        idx_content = idx_raw.decode()
        lines = idx_content.split("\n") # create a list of our grib idx text lines
        while '' in lines: lines.remove('') # remove any empty lines
        if out_file is not None: # we're writing the idx locally
            with open(str(out_file) + '.idx', 'w', encoding='utf8') as f:
                f.write("\n".join(lines))
        return lines

    def idx_to_byteranges(self, lines:list, search_str:str, verbose:int = 0) -> dict:
        '''Given the lines of a grib idx and our variable regex, return our wanted byte ranges
        
        Parameters
        ----------
        lines : list
            Our grib idx file, as a list of content lines
        search_str: str
            A regular expression that selects our desired grib fields (wgrib2 <grib_file> -s | egrep <search_str>)
        Returns
        -------
        byte_ranges : dict
            The byte ranges from the data file that contain our chosen variables, used for downloading
        '''
        expr = re.compile(search_str) # our grib variable Search (regular) expression
        byte_ranges = {} # initialize a dictionary # {byte-range-as-string: idx-line}
        for n, line in enumerate(lines, start=1): # read each line in our idx file
            if expr.search(line): # line matches the string we are looking for
                num, rangestart, date, var, level, forecast, _ = line.split(':')[0:7]
                rangeend = '' # go to the end of the file by default.
                if n+1 <= len(lines): # if there is a next line
                    rangeend = lines[n].split(':')[1] # the beginning byte of the next line is our end
                byte_ranges[f'bytes={rangestart}-{rangeend}'] = line # Store the byte-range string as our dictionary key
                if verbose > 1:
                    if args.dryrun:
                        self.logger.debug(f'  Dry Run: Found GRIB line [{num}]: date={date}, '
                                          f'variable={var}, level={level}, forecast={forecast}')
                    else:
                        self.logger.debug(f'  Downloading GRIB line [{num}]: date={date}, '
                                          f'variable={var}, level={level}, forecast={forecast}')
        if verbose > 2: self.logger.debug(f'  {len(byte_ranges)} byte_ranges: {list(byte_ranges.keys())}')
        return byte_ranges

    def get_chunks(self, obj_key:str, verbose:int = 0) -> list:
        '''Divide a large file into smaller bite size chunks, or byte ranges'''
        self.logger.debug('Splitting into chunks for faster large file transfers')
        chunk_size = 500 * 1024 * 1024 # keep our chunks under 500MB
        this_size = self.server.get_size(obj_key)
        if this_size is None: return None # punt if we have no size, we couldn't find the file we want
        chunk_list = range(0, this_size, chunk_size)[1:] # omit the first entry, 0
        byte_ranges = []
        start_byte = 0 # keep track of the start byte to request
        for next_byte in chunk_list:
            byte_ranges.append(f'bytes={start_byte}-{int(next_byte) - 1}')
            start_byte = next_byte
        byte_ranges.append(f'bytes={start_byte}-{this_size}')
        self.logger.debug(f'file size: {human_size(this_size)} or {this_size} raw bytes, chunks are: '
            f'{human_size(chunk_size)} or {chunk_size} raw\n{len(byte_ranges)} byte_ranges: {byte_ranges}')
        return byte_ranges

    def get_byteranges(self, obj_key:str, byte_ranges:Iterable) -> bytes:
        '''Use parallel transfers to download the specified byte ranges of a file'''
        from concurrent.futures import ThreadPoolExecutor

        def ranged_get(get_args:Tuple[str, str]) -> bytes:
            '''Accept args list as a tuple for multithreading'''
            key, range_header = get_args
            return self.server.download(key, range_header)

        with ThreadPoolExecutor(max_workers = 10) as executor:
            args_list = [(obj_key, byte_range) for byte_range in byte_ranges]
            results = executor.map(ranged_get, args_list)

        buffer = BytesIO()
        for r in results:
            if r: buffer.write(r)
        return buffer.getvalue()

    def get_full(self, obj_key:str, use_chunks:bool = False, verbose:int = 0) -> bytes:
        '''Download the full file, no subsetting. Conditionally retrieve chunks for large files'''
        self.logger.debug(f"downloading full file from {self.server.URL + obj_key}")
        if use_chunks:
            chunks = self.get_chunks(obj_key, verbose)
            if chunks is None: return None # punt if we have no chunks, our file doesn't exist
            return self.get_byteranges(obj_key, chunks)
        return self.server.download(obj_key)

    def subset_grib(self, obj_key:str, out_file:str, search_str:str = None, verbose:int = 0) -> bytes:
        '''Download a subset of GRIB fields from a GRIB2 file.

        This assumes there is an index (.idx) file available for the corresponding grib file.

        `Subsetting by variable or level follows the same principles described here
        <https://www.cpc.ncep.noaa.gov/products/wesley/fast_downloading_grib.html>`_

        Parameters
        ----------
        obj_key : str
            The URL for the GRIB2 file we are trying to download
        out_file: str
            Out (full path) filename that we will write the (idx and/or) subsetted grib to
        search_str: str
            A regular expression that selects our desired grib fields (wgrib2 <grib_file> -s | egrep <search_str>)
        '''
        if verbose > 1: self.logger.debug(f"  getting grib subset for {self.server.URL + obj_key}, "
                          f"vars: {search_str}")
        lines = self.get_idx_lines(obj_key, out_file, verbose) # Read the text lines of the grib index
        if lines is None: return None
        byte_ranges = self.idx_to_byteranges(lines, search_str, verbose) # produce our byteranges
        if args.dryrun:
            self.logger.info(f'  Dry Run: Success! Searched for [{search_str}] '
                             f'and found [{len(byte_ranges)}] GRIB fields.')
            return None
        content = self.get_byteranges(obj_key, byte_ranges)
        self.logger.debug(f'  Success! Searched for [{search_str}] and found [{len(byte_ranges)}] GRIB fields.')
        return content

class Nodd(NoddServer):
    '''A class that represents a NODD dataset and methods for fetching data files'''
    def __init__(self, product:str, product_type:str='', datasets:dict=None, args=None, logger=None):
        '''Initialize our data set attributes with our chosen product options'''
        if not args: # api method used, let's set up the args Namespace
            args = parse_args(DESC).parse_args([product, product_type])
        self.verbose = args.verbose
        # if 'logger' not in [globals(), locals()] or logger is None: logger = get_logger(verbose=self.verbose)
        self.logger = logger
        source = self.set_product(product, product_type, datasets, args)
        super().__init__(source, args.http)
        self.out_dir = args.dest or str(Path(DEFAULT_DEST, self.server.name))
        self.post = args.post
        self.cycles_back = args.cycles_back

    def __repr__(self):
        return f'Nodd("{self.product}", "{self.product_type}", datasets={self.datasets}, args={self.args})'

    def __str__(self):
        nodd_info = (
            f'Nodd dataset:\t{self.name}\nproduct:\t{self.product} {self.product_type} {self.server.URL}\n'
            f'key_pattern:\t{self.key_pattern}\nods_name:\t{self.ods_name}\nlast run:\t{self.last_run}\n'
            f'forecasts:\t{self.forecasts}\nsearch_str:\t{self.search_str}\nout_dir:\t{self.out_dir}\n'
        )
        if self.verbose: nodd_info += (
            f'mems:\t\t{self.mems}\nverbose:\t{self.verbose}\ncan_subset:\t{self.can_subset}'
        )
        return nodd_info

    def set_product(self, product:str, product_type:str, datasets:dict = None, args:Namespace = None) -> str:
        '''Use the available datasets and the provided arguments to set our product options and specs'''
        self.product      = product
        self.args         = args
        self.datasets     = datasets or datasets_gsl
        prod_info         = self.datasets[product]
        self.name         = prod_info['name']
        self.product_type = prod_info['types'][product_type]
        self.last_run     = prod_info['last_run']
        self.key_pattern  = self.ods_name = prod_info['key_pattern']
        self.forecasts    = args.fcsts or prod_info["forecasts"]
        if 'ods_name' in prod_info:
            self.ods_name = prod_info['ods_name']
        else:
            if args.ods and not args.post: self.logger.warning(f'Warning: No ods_name defined for {self.product}!')
        this_search_str = ('search_str_' + product_type).rstrip('_') # the product specific vars
        if this_search_str not in prod_info: this_search_str = 'search_str' # std product vars
        if args.vars == '' or (args.vars is None and this_search_str not in prod_info):
            self.search_str = '' # default if not specified by args or config
        else:
            self.search_str = args.vars or prod_info[this_search_str]
        if args.path:    # an alternate path was requested as an arg, use it if known case
            self.key_pattern = prod_info['key_pattern_alt']
            self.key_pattern = self.key_pattern.replace(prod_info['path_def'], args.path)
        self.mems = args.mems or prod_info['mems'] if 'mems' in prod_info else None
        config_match = prod_info['match_pattern'] if 'match_pattern' in prod_info else None
        self.match_pattern = args.match or config_match
        return prod_info['source']

    def get_latest_run(self) -> datetime:
        '''Derive some dates and times relative to now, to help determine the latest runtime for a given dataset'''
        LatestRun = namedtuple('TheLatestRuntimes', 'year prev_hr two_hrs_back '
                     'last_gfs_run last_ofs_run day day_sub3h prod_type')
        now = datetime.now(timezone.utc)
        last_hr = now - timedelta(hours=1)
        year = f'{last_hr:%Y}'
        day = f'{last_hr:%Y%m%d}' # define the day string / directory for an hour ago
        prev_hr = str(last_hr.hour).zfill(2)
        day_sub3h = f'{now - timedelta(hours=3.6):%Y%m%d}' # define the day string / dir for 3 hours ago
        two_hrs_back = (now - timedelta(hours=2)).strftime('%Y%m%d%H')
        last_gfs_run = ['00','06','12','18'][ int((now - timedelta(hours=3.6)).hour / 6) ]
        last_ofs_hr = ['00','06','12','18'][ int((now - timedelta(hours=2.1)).hour / 6) ]
        last_ofs_run = two_hrs_back[:8] + last_ofs_hr
        latest_info = LatestRun(year, prev_hr, two_hrs_back, last_gfs_run,
                        last_ofs_run, day, day_sub3h, self.product_type)._asdict()
        latest_run = datetime.strptime(self.last_run.format(**latest_info), '%Y%m%d%H')
        if not self.post: self.logger.info(f"Getting the latest run time: {latest_run.strftime('%Y-%m-%d-%H')}")
        return latest_run

    def adjust_start_end(self, start:datetime = None, end:datetime = None, step_hrs:int = 1) -> Tuple[datetime, datetime]:
        '''Adjust our start and end times for retrieval, in the context of our dataset and cycles back'''
        if not start: # live case is assumed, set up our latest run start
            start = self.get_latest_run()
        if not end: # end datetime is not defined, assume it's one cycle past start
            end = start + timedelta(hours = step_hrs)
        if self.cycles_back: # let's start a few cycles back if asked to
            start = start - timedelta(hours = step_hrs * args.cycles_back)
        return start, end

    def source_keys(self, start:datetime, end:datetime, step_hrs:int = 1) -> Iterator:
        '''Generator of our file keys and ods_names that support our data retrievals. Yields back an
        iterator, from start to end, of each file available, for each cycle, forecast (and ensemble
        member) in between.

        Parameters
        ----------
        start: datetime
            For data retrieval, what day/hour are we starting the downloads
        end: datetime
            For data retrieval, when are we ending the downloads
        Returns
        -------
        source_key: str
            the source_key (or object url), and
        ods_name: str
            our preferred ods_name to write to '''
        pt = self.product_type
        mems = self.mems or [None]
        if self.product in ['gfs','gefs','glofs','hafs','rrfs','rrfs_ens',]:
            step_hrs = 6
        start, end = self.adjust_start_end(start, end, step_hrs)
        current = start
        while current < end:
            day = current.strftime("%Y%m%d")
            yyjjj = current.strftime("%y%j")
            for mem in mems:
                for fxx in self.forecasts:
                    source_key = self.key_pattern.format(year=current.year, hr=current.hour,
                      day=day, prod_type=pt, fxx=fxx, mem=mem)
                    ods_name = self.ods_name.format(day=day, hr=current.hour, yyjjj=yyjjj,
                                 mem=mem, fxx=fxx, prod_type=pt, year=current.year)
                    yield (source_key, ods_name)
            current = current + timedelta(hours = step_hrs) # iterate over product cycle times

    def source_matches(self, start:datetime, end:datetime, step_hrs:int = 1) -> Iterator:
        '''Generator of file keys or urls that match our pattern for the time period provided.'''
        if self.product in ['gfs','gefs','glofs','hafs','rrfs','rrfs_ens',]:
            step_hrs = 6
        start, end = self.adjust_start_end(start, end, step_hrs)
        current = start
        while current < end:
            day = current.strftime("%Y%m%d")
            key_path = self.key_pattern.format(year=current.year, hr=current.hour, day=day,
                   prod_type=self.product_type, fxx=0, mem=0)
            key_dir = str(Path(key_path).parent)
            logger.info(f'Looking for live data under {key_dir} that matches the pattern {self.match_pattern}')
            for obj_key in self.server.get_matches(key_dir, self.match_pattern):
                yield (obj_key, obj_key) # second obj_key is really the output filename or out_file
            current = current + timedelta(hours = step_hrs)

    def fetch_file(self, obj_key:str, out_file:str) -> bytes:
        '''Fetch the given file url or object key, using the output filename when saving the idx'''
        write_idx = out_file if args.idx else None
        if self.search_str == '' or not self.can_subset:
            if args.idx: self.get_idx_lines(obj_key, write_idx, self.verbose)
            if args.dryrun:
                self.logger.info('  Dry Run: Success! Would save.')
                return None
            use_chunks = self.product.startswith('rrfs') and self.product_type in ['natlev','prslev'] and not args.path
            return self.get_full(obj_key, use_chunks, self.verbose)
        this_search_str = self.search_str
        if self.product == "blend": # for the blend, let's only download the 1hr accum (not the 6hr which decodes incorrectly)
            fcst_hr = re.search('f[0-9][0-9][0-9]', Path(obj_key).name).group(0)[1:]
            prev_fcst_hr = str(int(fcst_hr) - 1) # derive the previous hr to prevent other accums
            this_search_str = self.search_str.replace("APCP:surface", "APCP:surface:" + prev_fcst_hr)
        return self.subset_grib(obj_key, write_idx, this_search_str, self.verbose)

    def fetch(self, start:datetime = None, end:datetime = None):
        '''Perform our fetch of all expected data files for the time period provided.'''
        if not args.post: self.logger.info(f"Processing a data request for.. {self.product} {self.product_type} "
                              f"(path:{args.path}, cycles_back:{args.cycles_back}, vars:{self.search_str})")
        if self.match_pattern is not None:
            file_iter = self.source_matches(start, end)
        else:
            file_iter = self.source_keys(start, end)
        for obj_key, ods_name in file_iter: # iterate over file urls, and output filenames
            out_file = Path(self.out_dir, obj_key)
            if args.ods:
                out_file = Path(self.out_dir, ods_name)
            if Path(out_file).exists():
                self.logger.debug(f'skipping existing file: {out_file}')
                continue # the file we want already exists, skipping it
            if not args.post: self.logger.info(f'downloading to {out_file}')
            if args.post: print(out_file) # this filename only is bare minimum, used for --post processing steps
            Path(out_file).parent.mkdir(parents=True, exist_ok=True)
            content = self.fetch_file(obj_key, out_file)
            if content and len(content) > 0: # if content != b'':
                with Path(out_file).open(mode='wb') as f:
                    f.write(content)

    def _pqinsert_file(self, filename:str):
        '''If the "--pq" option is used, produce a pqinsert for downstream LDM consumption via a pqact pattern of the form\n
        >>> pqinsert -f EXP -p DSG_nodd_fetched_rrfs_prs_single_20230512_rrfs.t18z.prslev.f016.grib2'''
        # if args.pq: # run a pqinsert to share with subscribed downstream LDM hosts
        #     ldm_product_pre = '_'.join(['DSG_nodd_fetched', self.product, self.product_type or 'none', filename]) + '_'
        #     # if self.product_type == "subh": # for subhourly (15 minute) HRRR product type only
        #     #     ldm_product_pre = 'AQPI_BDP.NCEP15===' # prepend 'NCEP15===' (Grib2) identifier
        #     pqinsert_cmd = PQINSERT_PATH + ' -f EXP -p ' + ldm_product_pre + filename + ' ' + Path(filename).name
        #     if self.verbose >= 2: self.logger.debug("pqinserting: " + pqinsert_cmd)
        #     os.system(pqinsert_cmd)

def explore(datasets:dict):
    '''Allow for the open ended exploration of our datasets'''
    print('Here are some available nodd_fetch\'able products:')
    for prod, val in datasets.items():
        if prod == 'explore': continue
        print(f'  {prod:8s}: {val["name"]}')
    print('Which product are you interested in? ', end='')
    product = str(input())
    # my_types = [k[11:] for k in datasets[product].keys() if k.startswith('search_str')]
    my_types = list(datasets[product]['types'].keys())
    product_type = '' # = product_path
    if len(my_types) > 1:
        print(f'available product types: {my_types}. Which are you interested in? ', end='')
        product_type = str(input())
    my_paths = [k[5:] for k in datasets[product].keys() if k.startswith('path')]
    if len(my_paths) > 1:
        print(f'available product paths: {my_paths}. Which are you interested in? ', end='')
        # product_path = str(input())
    this_dataset = Nodd(product, product_type, datasets)
    print(f'\n{this_dataset}\nEnter a grib field search string (or keep the current one)? ', end='')
    new_search = str(input())
    if new_search == '': new_search = this_dataset.search_str
    if new_search == "''": new_search = ''
    print(f'  new_search: {new_search}')
    expr = re.compile(new_search, re.I) # our grib variable Search expression
    start, end = this_dataset.adjust_start_end()
    args.dryrun = args.idx = True
    print(f'Ok, here are some grib fields available for recent {product} data that match "{new_search}":')
    for i, (f, ods) in zip(range(3), this_dataset.source_keys(start, end)): # iterate over a few urls
        print(f'checking grib index for: {f}')
        out_file = Path(this_dataset.out_dir, f)
        Path(out_file).mkdir(parents=True, exist_ok=True)
        lines = this_dataset.get_idx_lines(f, Path(this_dataset.out_dir, f), this_dataset.verbose)
        if lines is None: continue
        while '' in lines: lines.remove('') # remove any empty lines
        for line in lines:
            # print(line)
            no, startbyte, runtime, field, unit_lev, fcst_hr, _ = line.split(':')[0:7]
            if expr.search(line): print('  ', no, startbyte, runtime, field, unit_lev, fcst_hr, line.split(':')[7:])
    print(f'Try grepping the downloaded grib idx files (at {this_dataset.out_dir}/) using your search string.')

def catch_signals():
    '''Sets up signal handling. This function catches all signals that can be caught,
    and sets up a signal handler for them.

    The signal handler logs the signal, closes all sockets, and exits the program.'''
    def sig_handler(signum:int, frame:'signal.Frame'):
        '''Set up signal handling - to gracefully exit on any catchable signal '''
        signame = signal.Signals(signum).name
        logger.info(f'Signal handler called with signal {signame} {signum}')
        # logger.debug(f'Signal handler called with local namespace:\n  {frame.f_lasti} {frame.f_locals}')
        # if args.verbose >= 2: logger.debug(f'Signal handler caller namespace: {frame.f_back.f_locals}')
        if not args.post: logger.info(f'Ending run at {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}')
        os._exit(0)

    catchable_sigs = set(signal.Signals) - {signal.SIGKILL, signal.SIGSTOP, signal.SIGWINCH}
    for sig in catchable_sigs: signal.signal(sig, sig_handler) # set up signal handling

def human_size(size:str, units:list = None) -> str:
    if units is None: units = [' bytes','KB','MB','GB','TB', 'PB', 'EB']
    return f"{float(size):.1f}{units[0]}" if float(size)<1024 else human_size(size/1024, units[1:])

def cleanup(dest:str, confirm:bool = False):
    '''Clean up old downloads if asked to (via --cleanup)'''
    if not confirm:
        if not args.post: logger.debug("..skipping cleanup")
        return

    if not args.post: logger.info(f"running cleanup of previous files in {dest} older than {SECS_TO_PURGE/60} minutes")
    for f in Path(dest).rglob('*'):
        if Path(f).is_file(): # and "grib2" in f # f.endswith("grib2")
            age = time.time() - Path(f).lstat().st_mtime
            if age > SECS_TO_PURGE:
                logging.debug(f"purging old file: {f}")
                Path(f).unlink()

def get_logger(logfile:str = None, verbose:int = 0, no_console:bool = False) -> logging.Logger:
    '''Set up our logger to capture our fetch actions and output'''
    this_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=this_level, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger()
    for name in ['botocore','boto3','urllib','urllib3','pycurl','s3transfer']:
        logging.getLogger(name).setLevel(logging.WARNING)
    if logfile is not None:
        if not Path(logfile).parent.exists(): logger.info(f'creating log directory {Path(logfile).parent}')
        Path(logfile).parent.mkdir(exist_ok=True, parents=True)
        file_handler = logging.FileHandler(filename=logfile)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)
        # logger.addHandler(TimedRotatingFileHandler(logfile, when='d', interval=1, backupCount=30))
    lhStdout = logger.handlers[0]  # stdout is the only handler initially
    # print(f'handlers:{logger.handlers}, lhStdout:{lhStdout}')
    if no_console or not sys.stderr.isatty(): # we're running from cron
        logger.removeHandler(lhStdout)
        for name in ['botocore','boto3','urllib','urllib3','pycurl','s3transfer']:
            logging.getLogger(name).removeHandler(lhStdout)
        logger.propagate = False # prevent sending to the upper logger that includes the console
    return logger

def parse_args(description) -> ArgumentParser:
    '''Set up command line argument parsing.'''
    class DateParser(Action):
        '''Allow flexibility when setting start and end datetimes - optionally specify an hour'''
        def __call__(self, parser, namespace, values, option_strings=None):
            dateformat = '%Y-%m-%d' # default to only the date specified, no hour
            if len(values) >= 13: # if we have enough in the provided string
                values = values[:10] + '-' + values[11:] # allow any, but override day / hour separator
                dateformat = '%Y-%m-%d-%H' # update our datetime format, with the hour, if we've got it
            setattr(namespace, self.dest, datetime.strptime(values, dateformat))

    parser = ArgumentParser(description=description)
    parser.add_argument('product', help=f'Specify the product dataset we\'re interested in')
    parser.add_argument('product_type', help='Optionally specify the product type we want',
                        default='', nargs='?',)
    parser.add_argument('-v', '--verbose', help='Make output more verbose. Can be used '
                        'multiple times.', action='count', default=0)
    parser.add_argument('-l', '--log', help='Specify the path to our log file', type=str)
    parser.add_argument('-d', '--dest', help='Specify the destination directory for downloads',
                        type=str)
    parser.add_argument('--start', help='Specify a start date for our fetch <YYYY-MM-DD[-HH]>',
                        action=DateParser, )
    parser.add_argument('--end', help='Specify the end date for our fetch <YYYY-MM-DD[-HH]>',
                        action=DateParser, )
    parser.add_argument('--vars', help='Specify a variable regular expression to subset your '
                        'downloads', type=str, default=None)
    parser.add_argument('--idx', action="store_true",
                        help='Preserve all grib idx metadata (as files on disk alongside data)')
    parser.add_argument( "--fcsts", help='Specify a set of forecast hours to retrieve', nargs="*",
                        type=int)
    parser.add_argument( "--mems", help='Specify a set of ensemble members to retrieve', nargs="*",
                        type=int)
    parser.add_argument('--path', help='Specify an alternate path / uri to our product (hi, ak, pr)',
                        type=str, default=None) # RRFS formats in flux
    parser.add_argument('--conf', help='Specify a config file with your preferred datasets',
                        type=str, default=None)
    parser.add_argument('-b', '--cycles-back', help='How many cycles back should we start? Used to '
                        'backfill missing files for previous time periods', type=int, default=None)
    parser.add_argument('--ods', action='store_true',
                        help='Use ODS file naming conventions (default is to mirror the source)')
    parser.add_argument('--dryrun', action="store_true", help='Only show what would be downloaded.'
                        ' (will still retrieve idx files with --idx)')
    parser.add_argument('--cleanup', action="store_true",
                        help='Cleanup previous downloads older than SECS_TO_PURGE')
    parser.add_argument('--pq', action="store_true",
                        help='produce LDM notifications with pattern "DSG_nodd_fetched*"')
    parser.add_argument('--http', action="store_true", help='Try https fetch method (rather than s3)')
    parser.add_argument('--post', action="store_true",
                        help='Only output downloaded filename. For use when post-processing')
    parser.add_argument('--match', help='filename pattern matching expression', type=str, default=None)
    parser.add_argument('--iscron', action="store_true", help='Are we (simulating or) running from cron?')
    return parser

def main():
    '''Our main method to set our product specs, and fetch our data'''
    global args, logger
    args = parse_args(DESC).parse_args() # process command line args
    logger = get_logger(args.log, args.verbose, args.iscron)
    if args.conf: # append some additonal datasets from an auxiliary config
        datasets_gsl.update(importlib.__import__(args.conf).datasets)
    if args.verbose > 1: logger.debug(f"args: {args}")
    start_time = datetime.now(timezone.utc)
    catch_signals()
    if args.product =='explore': # explore dataset options # execution ends with explore()
        while True: # not signal.KeyboardInterrupt
            explore(datasets_gsl)
    this_dataset = Nodd(args.product, args.product_type, datasets_gsl, args, logger)
    if not args.post:
        logger.info(f'Run started at {start_time.strftime("%Y-%m-%d %H:%M:%S")}, source: '
              f'{this_dataset.server.URL} can_subset:{this_dataset.can_subset}')

    this_dataset.fetch(args.start, args.end) # fetch our data files, subsettting as specified, or not
    cleanup(this_dataset.out_dir, args.cleanup) # purge old files if requested

    if not args.post:
        end_time = datetime.now(timezone.utc)
        elapsed = timedelta(seconds = (end_time - start_time).seconds)
        logger.info(f'This run completed at {end_time.strftime("%Y-%m-%d %H:%M:%S")} with an elapsed time of {elapsed}')

if __name__ == '__main__':
    main()
