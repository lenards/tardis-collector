#!/usr/bin/python26

#  Copyright (c) 2011, The Arizona Board of Regents on behalf of
#  The University of Arizona
#
#  All rights reserved.
#
#  Developed by: iPlant Collaborative as a collaboration between
#  participants at BIO5 at The University of Arizona (the primary hosting
#  institution), Cold Spring Harbor Laboratory, The University of Texas at
#  Austin, and individual contributors. Find out more at
#  http://www.iplantcollaborative.org/.
#
#  Redistribution and use in source and binary forms, with or without
#  modification, are permitted provided that the following conditions are
#  met:
#
# * Redistributions of source code must retain the above copyright
#   notice, this list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright
#   notice, this list of conditions and the following disclaimer in the
#   documentation and/or other materials provided with the distribution.
# * Neither the name of the iPlant Collaborative, BIO5, The University
#   of Arizona, Cold Spring Harbor Laboratory, The University of Texas at
#   Austin, nor the names of other contributors may be used to endorse or
#   promote products derived from this software without specific prior
#   written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
# IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED
# TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
#
# Author: Sangeeta Kuchimanchi (sangeeta@iplantcollaborative.org)
# Date: 10/11/2012
#

import sys
import MySQLdb
from webob import Request
import logging
import json

CONFIG_PATH = '/scripts'

sys.path.append(CONFIG_PATH)

from db_queries import OBJECT_QUERY_UUID_LOOKUP
from configs import (PROV_DB_HOST, PROV_DB_USERNAME, PROV_DB_PASSWORD,
                    PROV_DB_NAME, OBJECT_LOOKUP_LOGFILE)

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%a %Y-%m-%d %H:%M:%S',
                    filename=OBJECT_LOOKUP_LOGFILE)


def application(environ, start_response):
    """
    WSGI entry point for API endpoint 'object_lookup'
    This endpoint will lookup an object stored in provenance for a given
    service (each service must be assigned a `service_object_id`)
    """
    req = Request(environ)
    objid = req.params.get('service_object_id')

    try:
        conn = MySQLdb.connect(host=PROV_DB_HOST, user=PROV_DB_USERNAME,
                              passwd=PROV_DB_PASSWORD, db=PROV_DB_NAME)
        cursor = conn.cursor()
        cursor.execute(OBJECT_QUERY_UUID_LOOKUP % (objid))
        results = cursor.fetchall()

        if len(results) == 1:
            uid = str(results[0][0])
            info_msg = "Lookup Object Exists:" + " " + uid
            logging.info(info_msg)
            data_string = json.dumps({'UUID': uid}, indent=4)
            webstatus = '200 OK'
        elif len(results) > 1 :
            errmsg = ("More than one object was found: " + str(results))
            logging.error(errmsg)
            data_string = json.dumps({'Status': 'Exception',
                                'Details': 'Multiple objects found ' +
                                'with the same service_object_id. ' +
                                'Incident has been reported'}, indent=4)
            webstatus = '404 Not Found'
        else:
            err_msg = "Objuuid is null: " + objid
            logging.error(err_msg)
            data_string = json.dumps({'Status': 'Failed',
                                'Details': 'Object does not exist'},
                                indent=4)
            webstatus = '404 Not Found'

        cursor.close()
    except Exception, exc:
        err_msg = "MySQL DB Exception: " + " " + str(exc) + " " + objid
        logging.debug(err_msg)

        data_string = json.dumps({'Status': 'Failed',
                              'Details': 'MySQL Exception. Incident' +
                              ' has been reported'}, indent=4)
        webstatus = '500 Internal Server Error'

    response_headers = [('Content-type', 'application/json')]
    start_response(webstatus, response_headers)
    return (data_string)

