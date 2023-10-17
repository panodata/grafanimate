# -*- coding: utf-8 -*-
# (c) 2018-2021 Andreas Motl <andreas.motl@panodata.org>
# License: GNU Affero General Public License, Version 3
import json
import logging
import time

from marionette_driver import Wait
from marionette_driver.errors import TimeoutException
from pkg_resources import resource_stream

from grafanimate.marionette import FirefoxMarionetteBase
from grafanimate.model import AnimationFrame
from grafanimate.timeutil import format_date_grafana

log = logging.getLogger(__name__)


class GrafanaWrapper(FirefoxMarionetteBase):
    """
    https://marionette-client.readthedocs.io/en/master/interactive.html
    """

    def __init__(self, baseurl: str = None, use_panel_events: bool = False, dry_run: bool = False):
        self.baseurl = baseurl
        self.use_panel_events = use_panel_events
        self.dry_run = dry_run
        log.info("Starting GrafanaWrapper on %s", baseurl)
        FirefoxMarionetteBase.__init__(self)

    def boot_grafana(self):
        """
        Navigate to Grafana application and inject Grafana Sidecar service.
        """
        log.info("Starting Grafana at {}".format(self.baseurl))

        self.set_window_size(1920,1080+85*2.2)
        self.navigate(self.baseurl)

    def navigate(self, url):

        # Navigate to resource URL.
        self.marionette.navigate(url)

        # Wait for Grafana application to load.
        self.wait_for_grafana()

        # Zoom page
        self.marionette.set_pref("layout.css.devPixelsPerPx", str(2.2))

        # Load Javascript for GrafanaStudio sidecar service.
        jsfiles = ["grafana-util.js", "grafana-studio.js"]
        for jsfile in jsfiles:
            with resource_stream("grafanimate", jsfile) as f:
                javascript = f.read().decode("utf-8")
                self.run_javascript(javascript)

    def wait_for_grafana(self):
        """
        Wait for element <grafana-app> to appear.
        """
        log.info("Waiting for Grafana to load")
        element = self.wait_for_element_tag("grafana-app")
        time.sleep(0.3)
        log.info("Grafana loaded")
        return element

    def login(self, username, password):
        log.info("Logging in")
        javascript = mkjscall("grafanaStudio.login", username, password)
        self.run_javascript(javascript)

    def open_dashboard(self, uid, options=None):
        """
        Open a Grafana Dashboard with the designated uid
        and wait for all data to load into all panels.
        """
        options = options or {}
        javascript = mkjscall("grafanaStudio.openDashboard", uid, options)
        self.run_javascript(javascript)
        self.wait_for_frame_finished()

    def wait_for_frame_finished(self):
        if self.use_panel_events:
            return self.wait_all_data_received()

    def wait_all_data_received(self):
        """
        Wait for all data to arrive in the dashboard.
        """

        log.info('Waiting for "all-data-received" event')
        waiter = Wait(self.marionette, timeout=20.0, interval=0.1)

        def condition(marionette):
            return self.calljs("grafanaStudio.hasAllData", silent=True)

        try:
            waiter.until(condition)
        except TimeoutException as ex:
            log.warning("Timed out waiting for data: %s. Continuing anyway.", ex)

    def clear_all_data_received(self):
        return self.calljs("grafanaStudio.hasAllData", False)

    def timewarp(self, frame: AnimationFrame, dry_run: bool = False):
        """
        Navigate the Dashboard to the designated point in time
        and wait for refreshing all child components including data.
        """

        # Notify user.
        message = "Timewarp to {} -> {}".format(frame.timerange.start, frame.timerange.stop)
        log.info(message)
        self.console_log(message)

        # Perform timewarp.
        if not dry_run:
            self.clear_all_data_received()
            self.timerange_set(
                format_date_grafana(frame.timerange.start, frame.timerange.recurrence),
                format_date_grafana(frame.timerange.stop, frame.timerange.recurrence),
            )
            self.wait_for_frame_finished()

    def timerange_set(self, starttime, endtime):
        """
        Adjust Grafana time control. This is not synchronous.
        """
        return self.calljs("grafanaStudio.setTime", starttime, endtime)

    def timerange_get(self):
        """
        For fetching the current timeRange values, use::

            var timeRange = angular.element('grafana-app').injector().get('timeSrv').timeRange();
            var temp_date_from = new Date(timeRange.from);
            var temp_date_to = new Date(timeRange.to);

        -- https://community.grafana.com/t/how-to-access-time-picker-from-to-within-a-text-panel-and-jquery/6071/3
        """
        return self.calljs("grafanaStudio.getTime")
        raise NotImplemented("timerange_get not implemented yet")

    def run_javascript(self, sourcecode, silent=False):
        """
        Run the designated Javascript code directly in the scope
        of the application under test. Don't use any sandboxing.

        :code: Plain Javascript source code.
        """
        # https://github.com/mozilla/geckodriver/issues/1067#issuecomment-347180427
        # https://github.com/devtools-html/har-export-trigger/issues/27#issuecomment-424777524
        if not silent:
            log.debug("Running Javascript: %s", sourcecode)
        return self.marionette.execute_script(sourcecode, sandbox=None, new_sandbox=False)

    def calljs(self, name, *args, silent=False):
        return self.run_javascript(mkjscall(name, *args), silent=silent)

    def get_dashboard_title(self):
        return self.calljs("grafanaStudio.getDashboardTitle")

    def console_log(self, message):
        """
        Write a message to the Browser console (console.log).
        """
        return self.calljs("console.log", message, silent=True)

    def console_info(self, message):
        """
        Write a message to the Browser console (console.info).
        """
        return self.calljs("console.info", message, silent=True)

    def wait_for_map(self):
        """
        Wait for map element <panel-plugin-grafana-worldmap-panel ...> to appear.
        """
        log.debug("Waiting for map element to appear in DOM")
        # TODO: Make naming/addressing more universal.
        element = self.wait_for_element_tag("panel-plugin-grafana-worldmap-panel")
        log.info("Finished waiting for map element")
        log.info(element)
        return element


def mkjscall(name, *arguments, **flags):
    flags.setdefault("add_return", True)
    tpl = "{return}{name}({arguments});"
    tplvars = {
        "return": flags["add_return"] and "return " or "",
        "name": name,
        "arguments": mkjsargs(*arguments),
    }
    return tpl.format(**tplvars)


def mkjsargs(*arguments):
    return json.dumps(arguments).strip("[]")
