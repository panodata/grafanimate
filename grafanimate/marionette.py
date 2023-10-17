# -*- coding: utf-8 -*-
# (c) 2018-2021 Andreas Motl <andreas.motl@panodata.org>
# License: GNU Affero General Public License, Version 3
import atexit
import json
import logging
import time
from collections import OrderedDict

import where
from marionette_driver import Wait
from marionette_driver.errors import NoSuchElementException
from marionette_driver.marionette import Marionette

from grafanimate.util import check_socket, find_program_candidate

logger = logging.getLogger(__name__)


class FirefoxMarionetteBase(object):
    """
    Wrap Marionette/Firefox into convenient interface.

    - https://marionette-client.readthedocs.io/
    - https://marionette-client.readthedocs.io/en/master/reference.html
    - https://marionette-client.readthedocs.io/en/master/interactive.html
    """

    def __init__(self):
        logger.info("Starting Marionette Gecko wrapper")

        # Configuration
        self.firefox_bin = self.find_firefox()
        self.firefox_host = "localhost"
        self.firefox_port = 2828
        # TODO: Make configurable
        self.firefox_verbosity = 1
        # self.firefox_verbosity = 2

        # Timeout configuration
        self.startup_timeout = 20.0
        self.socket_timeout = 32.0
        self.page_timeout = 30.0
        self.script_timeout = 20.0
        self.shutdown_timeout = 10.0

        # Instance state defaults
        self.marionette = None
        self.firefox_run_headless = True
        self.firefox_do_shutdown = False
        self.firefox_already_started = False

    def enable_headless(self, run_headless=True):
        self.firefox_run_headless = run_headless

    def enable_shutdown(self, do_shutdown=True):
        self.firefox_do_shutdown = do_shutdown

    def boot_firefox(self, headless=True):

        # Indicate whether to run in headless mode
        self.enable_headless(headless)

        # Optionally shut down Marionette/Firefox after performing work
        # This will just be called if Python exits normally
        atexit.register(self.shutdown)

        # Check whether Firefox is already running
        logger.info(
            "Check for running instance of Marionette/Firefox at {}:{}".format(self.firefox_host, self.firefox_port)
        )

        if check_socket(self.firefox_host, self.firefox_port):
            logger.info("Will reuse running Marionette/Firefox")
            self.firefox_bin = None
            self.firefox_already_started = True
        else:
            logger.info("Will launch new Marionette/Firefox instance")

        # Connect to / start Marionette Gecko engine
        self.marionette = Marionette(
            host=self.firefox_host,
            port=self.firefox_port,
            bin=self.firefox_bin,
            socket_timeout=self.socket_timeout,
            startup_timeout=self.startup_timeout,
            headless=self.firefox_run_headless,
            verbose=self.firefox_verbosity,
        )

        self.marionette.DEFAULT_SHUTDOWN_TIMEOUT = self.shutdown_timeout

        # Start a session with Marionette Gecko engine
        self.marionette.start_session()

        # Configure Marionette
        self.configure_marionette()

    def configure_marionette(self):

        # This specifies the time to wait for the page loading to complete.
        self.marionette.timeout.page_load = self.page_timeout

        # This specifies the time to wait for injected scripts to finish
        # before interrupting them.
        self.marionette.timeout.script = self.script_timeout

        # Configure a HTTP proxy server
        self.marionette.set_pref("network.proxy.type", 0, default_branch=True)

    @classmethod
    def find_firefox(cls):
        candidates = []
        candidates += where.where("firefox-bin")
        candidates += where.where("firefox-esr")
        candidates += [
            "/Applications/Firefox.app/Contents/MacOS/firefox-bin",
        ]
        firefox = find_program_candidate(candidates)
        logger.info('Found "firefox" program at {}'.format(firefox))
        return firefox

    def get_status(self):
        attributes = ["session", "session_id"]
        data = OrderedDict()
        for attribute in attributes:
            data[attribute] = getattr(self.marionette, attribute)
        return data

    def log_status(self):
        logger.info("Marionette report: {}".format(json.dumps(self.get_status(), indent=4)))

    def has_active_session(self):
        is_initialized = self.marionette is not None and self.marionette.session_id is not None
        return is_initialized

    def ensure_session(self):
        # self.log_status()
        if not self.has_active_session():
            self.boot_firefox()
            logger.info("No session with Marionette, started new session {}".format(self.marionette.session_id))

    def shutdown(self):
        if self.firefox_do_shutdown:

            logger.info("Aiming at shutdown")

            if self.firefox_already_started:
                logger.warning("Can not shutdown Firefox as it was already running before starting this program")
                return False

            logger.info("Shutting down Marionette/Firefox")
            if self.marionette is not None:
                self.marionette.quit()
                return True

    def find_tag(self, tagname):
        try:
            element = self.marionette.find_element("tag name", tagname)
            return element
        except NoSuchElementException:
            pass

    def wait_for_element_tag(self, tagname):
        """
        Wait for element to appear.
        """
        waiter = Wait(self.marionette, timeout=20.0, interval=0.1)
        element = waiter.until(lambda m: self.find_tag(tagname))
        return element

    def render_image(self, element=None):
        """
        Return screenshot from element.
        """
        while True:
            result = self.marionette.execute_script('''
            panels = Object.values(window.wrappedJSObject.grafanaRuntime.getPanelData())
            return panels.length && panels.every(function(o) {return o?.state=='Done'})
            ''')
            if result:
                break
            logger.info("waiting for panels to load")
            time.sleep(0.1)

        image = self.marionette.screenshot(element=element, format="binary")
        return image

    def set_window_size(self, width, height):
        self.marionette.set_window_rect(width=width, height=height)

    def get_window_rect(self):
        return self.marionette.window_rect
