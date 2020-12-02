import google.cloud.logging
from google.cloud._helpers import UTC
from google.cloud.logging_v2.handlers.handlers import CloudLoggingHandler
from google.cloud.logging_v2.handlers.transports import SyncTransport
from google.cloud.logging_v2 import Client
from google.cloud.logging_v2.resource import Resource
from google.cloud.logging_v2 import entries
from google.cloud.logging_v2._helpers import LogSeverity

from time import sleep
from datetime import datetime
from datetime import timezone
import os
import sys
from shlex import split
import subprocess
import signal


class ScriptInterface:

    def __init__(self, environment):
        run_dir = os.path.dirname(os.path.realpath(__file__))
        self.script_path = os.path.join(run_dir, f'test-code/{environment}.sh')
        print(self.script_path)
        if not os.path.exists(self.script_path):
            raise RuntimeError(f'environment {environment} does not exist')

    def _run_command(self, command, args=None):
        os.setpgrp()
        complete = False
        try:
            full_command = [self.script_path] + split(command)
            print(full_command)
            if args:
                full_command += split(args)
            result = subprocess.run(full_command, capture_output=True)
            complete=True
            return result.returncode, result.stdout.decode('utf-8')
        except Exception as e:
            print(e)
        finally:
            if not complete:
                # kill background process if script is terminated
                # os.killpg(0, signal.SIGTERM)
                return 1, None

    def trigger(self, function):
        self._run_command('trigger', function)
        # give the command time to be received
        sleep(30)



class TestCommon:
    _client = Client()
    # environment name must be set by subclass
    environment = None

    def _get_logs(self, timestamp=None):
        time_format = "%Y-%m-%dT%H:%M:%S.%f%z"
        if not timestamp:
            timestamp = datetime.now(timezone.utc) - timedelta(minutes=10)
        _, filter_str = self._script._run_command('filter-string')
        filter_str += ' AND timestamp > "%s"' % timestamp.strftime(time_format)
        iterator = self._client.list_entries(filter_=filter_str)
        entries = list(iterator)
        return entries

    @classmethod
    def setUpClass(cls):
        if not cls.environment:
            raise NotImplementedError('environment not set by subclass')
        cls._script = ScriptInterface(cls.environment)
        # check if already setup
        status, _ = cls._script._run_command('verify')
        if status == 0:
            if os.getenv("NO_CLEAN"):
                # ready to go
                return
            else:
                # reset environment
                status, _ = cls._script._run_command('destroy')
                self.assertEqual(status)
        # deploy test code to GCE
        status, _ = cls._script._run_command('deploy')
        self.assertTrue(status)
        # verify code is running
        status, _ = cls._script._run_command('verify')
        self.assertEqual(status, 0)

    @classmethod
    def tearDown_class(cls):
        # by default, destroy environment on each run
        # allow skipping deletion for development
        if not os.getenv("NO_CLEAN"):
            cls._script._run_command('destroy')

    def test_receive_log(self):
        timestamp = datetime.now(timezone.utc)
        self._script.trigger('test_1')
        log_list = self._get_logs(timestamp)
        self.assertTrue(log_list)
        self.assertEqual(len(log_list), 1)
        log = log_list[0]
        self.assertTrue(isinstance(log, entries.StructEntry))
        self.assertEqual(log.payload['message'], 'test_1')
        self.assertEqual(log.severity, LogSeverity.WARNING)
