# -*- coding: utf-8 -*-
# (c) 2018 Andreas Motl <andreas@hiveeyes.org>
# License: GNU Affero General Public License, Version 3
import json
import logging

from docopt import DocoptExit, docopt

from grafanimate import __appname__, __version__
from grafanimate.core import get_scenario, make_grafana, make_storage, run_animation
from grafanimate.util import asbool, normalize_options, setup_logging, slug

log = logging.getLogger(__name__)


def run():
    """
    Usage:
      grafanimate [options] [--target=<target>]...
      grafanimate --version
      grafanimate (-h | --help)

    Options:

      --scenario=<scenario>         Which scenario to run. Built-in scenarios are defined within the
                                    `scenarios.py` file, however you can easily define scenarios in
                                    custom Python files.

                                    Scenarios can be referenced by arbitrary entrypoints, like:

                                    - `--scenario=grafanimate.scenarios:playdemo`    (module, symbol)
                                    - `--scenario=grafanimate/scenarios.py:playdemo` (file, symbol)
                                    - `--scenario=playdemo` (built-in)

      --grafana-url=<url>           Base URL to Grafana.
                                    If your Grafana instance is protected, please specify credentials
                                    within the URL, e.g. https://user:pass@www.example.org/grafana.

      --dashboard-uid=<uid>         Grafana dashboard UID.

    Optional:
      --exposure-time=<seconds>     How long to wait for each frame to complete rendering. [default: 0.5]
      --use-panel-events            Whether to enable using Grafana's panel events. [default: false]
                                    Caveat: Used to work properly with Angular-based panels like `graph`.
                                            Stopped working with React-based panels like `timeseries`.

      --panel-id=<id>               Render single panel only by navigating to "panelId=<id>&fullscreen".
      --dashboard-view=<mode>       Use Grafana's "d-solo" view for rendering single panels without header.

      --header-layout=<layout>      The header rendering subsystem offers different modes
                                    for amending the vanilla Grafana user interface.
                                    Multiple modes can be combined.
                                    [default: large-font]

                                    - no-chrome:            Set kiosk mode, remove sidemenu and more chrome
                                    - large-font:           Use larger font sizes for title and datetime
                                    - collapse-datetime:    Collapse datetime into title
                                    - studio:               Apply studio modifications. This options aggregates
                                                            "no-chrome", "large-font" and "collapse-datetime".
                                    - no-folder:            Don't include foldername in title

                                    - no-title:             Turn off title widget
                                    - no-datetime:          Turn off datetime widget

      --datetime-format=<format>    Datetime format to use with header layouts like "studio".
                                    Examples: YYYY-MM-DD HH:mm:ss, YYYY, HH:mm.

                                    There are also some format presets available here:
                                    - human-date:           on 2018-08-14
                                    - human-time:           at 03:16:05
                                    - human-datetime:       on 2018-08-14 at 03:16:05

                                    When left empty, the default is determined by the configured interval.

      --debug                       Enable debug logging
      -h --help                     Show this screen


    Examples for scenario mode. Script your animation in file `scenarios.py`. The output files
    will be saved at `./var/spool/{scenario}/{dashboard-uid}`.

      # Use freely accessible `play.grafana.org` for demo purposes.
      grafanimate --grafana-url=https://play.grafana.org/ --dashboard-uid=000000012 --scenario=playdemo

      # Example for generating Luftdaten.info graph & map.
      grafanimate --grafana-url=http://localhost:3000/ --dashboard-uid=1aOmc1sik --scenario=ldi_all

      # Use more parameters to control the rendering process.
      grafanimate --grafana-url=http://localhost:3000/ --dashboard-uid=acUXbj_mz --scenario=ir_sensor_svg_pixmap --header-layout=studio --datetime-format=human-time --panel-id=6

    """

    # Parse command line arguments.
    options = docopt(run.__doc__, version=__appname__ + " " + __version__)
    options = normalize_options(options, lists=["header-layout"])

    # Setup logging.
    debug = options.get("debug")
    log_level = logging.INFO
    if debug:
        log_level = logging.DEBUG
    setup_logging(log_level)

    # Debug command line options.
    if debug:
        log.info("Options: {}".format(json.dumps(options, indent=4)))

    # Sanity checks.
    if not options["scenario"]:
        raise DocoptExit("Error: Parameter --scenario is mandatory")

    if options["dashboard-view"] == "d-solo" and not options["panel-id"]:
        raise DocoptExit("Error: Parameter --panel-id is mandatory for --dashboard-view=d-solo")

    options["exposure-time"] = float(options["exposure-time"])
    options["use-panel-events"] = asbool(options["use-panel-events"])
    if options["use-panel-events"]:
        options["exposure-time"] = 0

    # Load scene.
    scenario = get_scenario(options["scenario"])

    # Resolve URL to Grafana, either from command line (precedence), or from scenario file.
    if options["grafana-url"]:
        scenario.grafana_url = options["grafana-url"]
    if not scenario.grafana_url:
        scenario.grafana_url = "http://localhost:3000"

    # The dashboard UID can be defined either in the scenario or via command line.
    # Command line takes precedence.
    if options["dashboard-uid"]:
        scenario.dashboard_uid = options["dashboard-uid"]
    if not scenario.dashboard_uid:
        raise KeyError("Dashboard UID is mandatory, either supply it on the command line or via scenario file")

    # Define pipeline elements.
    grafana = make_grafana(scenario.grafana_url, options["use-panel-events"])
    storage = make_storage(
        imagefile="./var/spool/{scenario}/{uid}/{uid}_{dtstart}_{dtuntil}.png",
        outputfile="./var/results/{scenario}--{name}--{uid}.mp4",
    )

    # Assemble pipeline.
    # Run stop motion animation to produce single artifacts.
    run_animation(grafana=grafana, storage=storage, scenario=scenario, options=options)

    # Run rendering steps, produce composite artifacts.
    title = grafana.get_dashboard_title()
    path = "./var/spool/{scenario}/{uid}/{uid}_*.png".format(scenario=slug(options.scenario), uid=scenario.dashboard_uid)
    results = storage.produce_artifacts(path=path, scenario=options.scenario, uid=scenario.dashboard_uid, name=title)

    log.info("Produced %s results\n%s", len(results), json.dumps(results, indent=2))
