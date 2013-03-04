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

import datetime
import re
import sys
import time
import MySQLdb
from webob import Request
import json

CONFIG_PATH = '/scripts'

sys.path.append(CONFIG_PATH)
from db_queries import (AUDIT_ALL, AUDIT_DATA, AUDIT_PROXY, AUDIT_NO_PROXY_DATA,
                        HIST_INSERT_QUERY_PARENT, HIST_INSERT_QUERY,
                        HIST_SELECT_QUERY, QUERY_ALL, QUERY_CATEGORY_ID,
                        QUERY_CHECK_UUID, QUERY_DATA, QUERY_EVENT_ID,
                        QUERY_NO_PROXY_DATA, QUERY_PROXY, QUERY_SERVICE_ID,
                        QUERY_SERVICE_VERSION_ID)
from configs import (PROV_DB_HOST, PROV_DB_USERNAME, PROV_DB_PASSWORD,
                     PROV_DB_NAME)
from prov_logging import log_errors, log_exception, log_info
from script_tracking import (failed_inserts_audit, get_history_code,
                             track_history_errors)


def application(environ, start_response):
    """Endpoint for creating provenance records given a service, a
    category, and an event.

    These elements must be added prior to registering an object and
    creating any provenance information.

    Also included for additional tracking and bookkeeping are:
    ``username`` - this may be a system or daemon account
    ``proxy_username`` - the user as system account is acting on behalf of
    ``event_data`` - any additional info associated with the event
    ``request_ipaddress`` - the IP address of the service posting data
    ``track_history`` - boolean-like code indicating to track history
    ``track_history_code`` - the association code for history tracking
    ``created_date`` - time in seconds since Epoch
    ``version`` - string identifier indicating version
    """
    req = Request(environ)

    if (req.method == 'POST'):
        json_data, webstatus = _handle_post(req)
    else:
        webstatus = '405 Method Not Allowed'
        json_data = json.dumps({'result': {'Status': 'Failed',
                                'Details': 'Incorrect HTTP METHOD'}},
                               indent=4)

    info_msg = "Request Processed: " + str(webstatus) + " Details: " + \
        str(json_data)
    log_info(info_msg)

    response_headers = [('Content-type', 'application/json')]
    start_response(webstatus, response_headers)
    return (json_data)


def _handle_post(req):
    """Private method for handling an HTTP POST to this endpoint."""
    uuid = req.params.get('uuid')
    service_name = req.params.get('service_name')
    category_name = req.params.get('category_name')
    event_name = req.params.get('event_name')
    username = req.params.get('username')
    proxy_username = req.params.get('proxy_username')
    event_data = req.params.get('event_data')
    request_ipaddress = req.remote_addr
    track_history = req.params.get('track_history')
    track_history_code = req.params.get('track_history_code')
    created_date = get_date_time()
    version = req.params.get('version')

    # if the above was an object, a json.dumps() call would create this
    # same string that is being contenated and it would include key names
    all_data = ("{" + str(uuid) + "," + str(service_name) + "," +
                str(category_name) + "," + str(event_name) + "," +
                str(username) + "," + str(proxy_username) + "," +
                str(event_data) + "," + str(request_ipaddress) + "," +
                str(created_date) + "," + str(version) + "," +
                str(track_history) + "," + str(track_history_code) + "}")
    info_msg = "Received provenance request: " + all_data
    log_info(info_msg)

    validated, details = validate(uuid, service_name, category_name,
                                  event_name, username, proxy_username,
                                  version)

    info_msg = "Validation:" + str(validated) + " Details: " + str(details)
    log_info(info_msg)

    if validated:
        json_data, webstatus = process_valid_request(uuid, service_name,
                                                     category_name, event_name,
                                                     username, proxy_username,
                                                     event_data,
                                                     request_ipaddress,
                                                     created_date, version,
                                                     track_history,
                                                     track_history_code)
    else:
        json_data = json.dumps({'result': {'Status': 'Failed',
                               'Details': 'Validation Failed',
                               'Report': details}}, indent=4)
        webstatus = '400 Bad Request'

    return (json_data, webstatus)


def process_valid_request(uuid, service_name, category_name, event_name,
                          username, proxy_username, event_data,
                          request_ipaddress, created_date, version,
                          track_history, track_history_code):

    if version == None:
        version = "Default"

    event_id = get_id(event_name, "EVENT", version)
    category_id = get_id(category_name, "CATEGORY", version)
    service_id = get_id(service_name, "SERVICE", version)

    if event_id != "EMPTY" and category_id != "EMPTY" and service_id != "EMPTY":

        all_data = ("{" + str(uuid) + "," + str(service_name) + "," +
                    str(category_name) + "," + str(event_name) + "," +
                    str(username) + "," + str(proxy_username) + "," +
                    str(event_data) + "," + str(request_ipaddress) + "," +
                    str(created_date) + "}")

        try:
            conn = MySQLdb.connect(
                host=PROV_DB_HOST, user=PROV_DB_USERNAME,
                passwd=PROV_DB_PASSWORD, db=PROV_DB_NAME)
            cursor = conn.cursor()

            cursor.execute(QUERY_CHECK_UUID % (uuid))
            check_results = cursor.fetchall()
            if len(check_results) == 1:

                if proxy_username is None and event_data is None:
                    insert_status = cursor.execute(
                        QUERY_NO_PROXY_DATA % (uuid, event_id,
                                               category_id, service_id,
                                               username, request_ipaddress,
                                               created_date))
                    if str(insert_status) == "1":
                        info_msg = "Success: " + all_data
                        log_info(info_msg)
                    else:
                        err_msg = "QUERY_NO_PROXY_DATA query failed" + all_data
                        log_errors(err_msg)
                        audit_insert = cursor.execute(AUDIT_NO_PROXY_DATA
                                                      % (uuid, event_id,
                                                         category_id,
                                                         service_id,
                                                         username,
                                                         request_ipaddress,
                                                         created_date))
                        if audit_insert != 1:
                            failed_inserts_audit(all_data)

                elif proxy_username != None:
                    insert_status = cursor.execute(QUERY_PROXY
                                                   % (uuid, event_id,
                                                      category_id, service_id,
                                                      username, proxy_username,
                                                      request_ipaddress,
                                                      created_date))
                    if str(insert_status) == "1":
                        info_msg = "Success: " + all_data
                        log_info(info_msg)
                    else:
                        err_msg = "QUERY_PROXY query failed" + all_data
                        log_errors(err_msg)
                        audit_insert = cursor.execute(AUDIT_PROXY
                                                      % (uuid, event_id,
                                                         category_id,
                                                         service_id, username,
                                                         proxy_username,
                                                         request_ipaddress,
                                                         created_date))
                        if audit_insert != 1:
                            failed_inserts_audit(all_data)

                elif event_data != None:

                    insert_status = cursor.execute(QUERY_DATA
                                                   % (uuid, event_id,
                                                      category_id, service_id,
                                                      username, event_data,
                                                      request_ipaddress,
                                                      created_date))
                    if str(insert_status) == "1":
                        info_msg = "Success: " + all_data
                        log_info(info_msg)
                    else:
                        err_msg = "QUERY_DATA query failed" + all_data
                        log_errors(err_msg)
                        audit_insert = cursor.execute(AUDIT_DATA
                                                      % (uuid, event_id,
                                                         category_id,
                                                         service_id, username,
                                                         event_data,
                                                         request_ipaddress,
                                                         created_date))
                        if audit_insert != 1:
                            failed_inserts_audit(all_data)

                else:
                    insert_status = cursor.execute(QUERY_ALL
                                                   % (uuid, event_id,
                                                      category_id, service_id,
                                                      username, proxy_username,
                                                      event_data,
                                                      request_ipaddress,
                                                      created_date))
                    if str(insert_status) == "1":
                        info_msg = "Success: " + all_data
                        log_info(info_msg)
                    else:
                        err_msg = "QUERY_ALL query failed" + all_data
                        log_errors(err_msg)
                        audit_insert = cursor.execute(AUDIT_ALL
                                                      % (uuid, event_id,
                                                         category_id,
                                                         service_id, username,
                                                         proxy_username,
                                                         event_data,
                                                         request_ipaddress,
                                                         created_date))
                        if audit_insert != 1:
                            failed_inserts_audit(all_data)

                if track_history == "1":

                    if track_history_code != None:

                        history_data = str(
                            track_history_code) + " " + str(all_data)

                        cursor.execute(HIST_SELECT_QUERY %
                                      (track_history_code))
                        results = cursor.fetchall()
                        if len(results) != 0:
                            hist_status = cursor.execute(HIST_INSERT_QUERY
                                                         % (track_history_code,
                                                            uuid, event_id,
                                                            category_id,
                                                            service_id,
                                                            username,
                                                            created_date))
                            if str(hist_status) == "1":
                                info_msg = ("History request recorded:" + " " +
                                            str(track_history_code) + " " +
                                            all_data)
                                log_info(info_msg)
                            else:
                                err_msg = "HIST_INSERT_QUERY failed" + \
                                    history_data
                                log_errors(err_msg)
                                track_history_errors(history_data)
                        else:
                            parent_query = "Y"
                            hist_status = cursor.execute(
                                HIST_INSERT_QUERY_PARENT % (
                                    track_history_code,
                                    uuid, event_id,
                                    category_id,
                                    service_id,
                                    username,
                                    created_date,
                                    parent_query))
                            if str(hist_status) == "1":
                                info_msg = ("History request recorded:" + " " +
                                            str(track_history_code) + " " +
                                            all_data)
                                log_info(info_msg)
                            else:
                                err_msg = "HIST_INSERT_QUERY_PARENT failed" + \
                                    history_data
                                log_errors(err_msg)
                                track_history_errors(history_data)

                    else:
                        history_data = str(username) + \
                            ":" + str(uuid) + ":" + str(created_date)
                        history_code = get_history_code(history_data)
                        info_msg = "History code generated: " + \
                            str(history_code) + " " + all_data
                        log_info(info_msg)
                else:
                    if track_history_code != None:
                        err_msg = ("Track History flag not set but history " +
                                   "code was sent. Please check history " +
                                   "tracking error logs. " +
                                   str(track_history_code))
                        log_errors(err_msg)
                        history_data = str(
                            track_history_code) + "," + str(all_data)
                        track_history_errors(history_data)

                cursor.close()

                webstatus = '200 OK'
                if track_history == "1" and track_history_code == None:
                    data = json.dumps({'result': {'Status': 'Success',
                                    'Details': 'Provenance recorded',
                                    'History code': history_code}},
                                    indent=4)
                elif track_history == None and track_history_code != None:
                    data = json.dumps({'result': {'Status': 'Success',
                                        'Details': 'Provenance recorded',
                                        'Warning': 'Track history flag is not' +
                                        'set but history code was sent'}},
                                      indent=4)
                else:
                    data = json.dumps({'result': {'Status': 'Success',
                                      'Details': 'Provenance recorded'}},
                                      indent=4)

                return (data, webstatus)

            else:
                cursor.close()
                webstatus = '500 Internal Server Error'
                data = json.dumps({'result': {'Status': 'Failed', 'Details':
                                'Provenance not recorded', 'Report':
                                'More than one record found for given ' +
                                ' UUID. Support has been notified'}},
                                indent=4)
                err_msg = "Duplicate UUID enery found: " + all_data
                # notify_support
                log_errors(err_msg)
                failed_inserts_audit(all_data)
                return (data, webstatus)

        except Exception as exc:
            err_msg = "EXCEPTION: " + str(exc) + ": " + all_data
            log_exception(err_msg)
            audit_insert = cursor.execute(
                AUDIT_ALL % (uuid, event_id, category_id, service_id, username,
                            proxy_username, event_data, request_ipaddress,
                            created_date))
            if audit_insert != 1:
                failed_inserts_audit(all_data)

            cursor.close()

            webstatus = '500 Internal Server Error'
            data = json.dumps({'result': {'Status': 'Failed', 'Details':
                              'Provenance was not recorded. Audit data ' +
                              'recorded.'}}, indent=4)
            return (data, webstatus)

    else:
        webstatus = '400 Bad Request'
        data = json.dumps({'result': {'Status': 'Failed', 'Details':
                          'Incorrect Service/Category/Event data.'}}, indent=4)
        return (data, webstatus)


def get_date_time():
    """Retrieves the current time in seconds."""
    currenttime = datetime.datetime.now()
    current_in_sec = time.mktime(currenttime.timetuple())

    return int(current_in_sec)


def get_id(name, key, version):
    """Retrieve the identifier for a Service or Event."""
    conn = MySQLdb.connect(host=PROV_DB_HOST, user=PROV_DB_USERNAME,
                           passwd=PROV_DB_PASSWORD, db=PROV_DB_NAME)
    cursor = conn.cursor()

    if key == "EVENT":
        cursor.execute(QUERY_EVENT_ID % (name))
        results = cursor.fetchone()
    elif key == "SERVICE" and version == "Default":
        cursor.execute(QUERY_SERVICE_ID % (name))
        results = cursor.fetchone()
    elif key == "SERVICE" and version != "Default":
        cursor.execute(QUERY_SERVICE_VERSION_ID % (name, version))
        results = cursor.fetchone()
    else:
        cursor.execute(QUERY_CATEGORY_ID % (name))
        results = cursor.fetchone()

    if results != None:
        id_ = int(results[0])
        cursor.close()
        return id_
    else:
        cursor.close()
        return "EMPTY"


def validate(uuid, service_name, category_name, event_name, username,
             proxy_username, version):
    """Determine the provided information from the request is
    acceptable."""
    # TODO: determine if a regex defined as r'^[0-9]+$', etc is
    # compiled or not... this could be improve in a number of ways
    if (uuid != None and service_name != None and category_name != None and
        event_name != None and username != None):

        if re.match(r'^[0-9]+$', uuid) != None:
            if re.match(r'^[A-Za-z0-9\-_]+$', service_name) != None:
                if re.match(r'^[A-Za-z0-9\-_]+$', category_name) != None:
                    if re.match(r'^[A-Za-z0-9\-_]+$', event_name) != None:
                        if re.match(r'^[A-Za-z0-9\-_]+$', username) != None:
                            if proxy_username != None:
                                if re.match(r'^[A-Za-z0-9\-_]+$', proxy_username) != None:
                                    if version != None:
                                        if re.match(r'^[A-Za-z0-9\-_]+$', version) != None:
                                            details = "Validation Passed"
                                            return (True, details)
                                        else:
                                            details = "version value is not in the correct format"
                                            return (False, details)
                                    else:
                                        details = "Validation Passed"
                                        return (True, details)

                                else:
                                    details = "proxy_username value is not in the correct format"
                                    return (False, details)
                            else:
                                if version != None:
                                    if re.match(r'^[A-Za-z0-9\-_]+$', version) != None:
                                        details = "Validation Passed"
                                        return (True, details)
                                    else:
                                        details = "version value is not in the correct format"
                                        return (False, details)
                                else:
                                    details = "Validation Passed"
                                    return (True, details)

                        else:
                            details = "username value is not in the correct format"
                            return (False, details)
                    else:
                        details = "event_name value is not in the correct format"
                        return (False, details)
                else:
                    details = "category_name value is not in the correct format"
                    return (False, details)
            else:
                details = "service_name value is not in the correct format"
                return (False, details)
        else:
            details = "uuid value is not in the correct format"
            return (False, details)
    else:
        details = "uuid/event_name/category_name/service_name/username cannot be empty"
        return (False, details)
