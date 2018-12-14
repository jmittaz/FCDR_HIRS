"""Common utility functions between scripts

Should probably be sorted into smaller modules.
"""

import sys
import logging
import datetime
import warnings
import traceback
import io
import pprint
import inspect
import numpy
import xarray
from .fcdr import list_all_satellites

my_pb_widget = [progressbar.Bar("=", "[", "]"), " ",
                progressbar.Percentage(), " (",
                progressbar.AdaptiveETA(), " -> ",
                progressbar.AbsoluteETA(), ') ']

def add_to_argparse(parser,
        include_period=True,
        include_sat=0,
        include_channels=True,
        include_temperatures=False,
        include_debug=False):
    """Add commoners to argparse object
    """

    if include_sat == 1:
        parser.add_argument("satname", action="store", type=str.lower,
            help="Satellite name",
            metavar="satname",
            choices=sorted(list_all_satellites())+["all"])
    elif include_sat == 2:
        parser.add_argument("satname1", action="store", type=str,
            help="Satellite name, primary",
            metavar="SAT1",
            choices=sorted(list_all_satellites()))

        parser.add_argument("satname2", action="store", type=str,
            help="Satellite name, secondary",
            metavar="SAT2",
            choices=sorted(list_all_satellites()))
    elif include_sat!=0:
        raise ValueError("include_sat should be False, 0, 1, True, or 2. "
            "Got {!s}.".format(include_sat))

    if include_period:
        parser.add_argument("from_date", action="store", type=str,
            help="Start date/time")

        parser.add_argument("to_date", action="store", type=str,
            help="End date/time")

        parser.add_argument("--datefmt", action="store", type=str,
            help="Date format for start/end dates",
            default="%Y-%m-%d")

    hasboth = include_channels and include_temperatures
    if hasboth:
        required_named = parser.add_argument_group(
            "required named arguments")
        ch_tm = required_named
        regarg = dict(required=True)
    else:
        ch_tm = parser
        regarg = {}

    # http://stackoverflow.com/a/24181138/974555
    if include_channels:
        ch_tm.add_argument(("--" if hasboth else "") + "channels", action="store", type=int,
            nargs="+", choices=list(range(1, 21)),
            default=list(range(1, 20)),
            help="Channels to consider",
            **regarg)

    if include_temperatures:
        ch_tm.add_argument(("--" if hasboth else "") + "temperatures", action="store", type=str,
            nargs="+",
            choices=['an_el', 'patch_exp', 'an_scnm', 'fwm', 'scanmotor',
                'iwt', 'sectlscp', 'primtlscp', 'elec', 'baseplate',
                'an_rd', 'an_baseplate', 'ch', 'an_fwm', 'ict', 'an_pch',
                'scanmirror', 'fwh', 'patch_full', 'fsr'],
            help="Temperature fields to use",
            **regarg)

    parser.add_argument("--verbose", action="store_true",
        help="Be verbose", default=False)

    parser.add_argument("--log", action="store", type=str,
        help="Logfile to write to.  Leave out for stdout.")

    if include_debug:
        parser.add_argument("--debug", action="store_true",
            help="Add extra debugging information", default=False)

    return parser


def time_epoch_to(ds, epoch):
    """Convert all time variables/coordinates to count from epoch
    """

    for k in [k for (k, v) in ds.variables.items() if v.dtype.kind.startswith("M")]:
        ds[k].encoding["units"] = "seconds since {:%Y-%m-%d %H:%M:%S}".format(epoch)
        if ds[k].size > 0:
            ds[k].encoding["add_offset"] = (
                ds[k].min().values.astype("M8[ms]").astype(datetime.datetime)
                - epoch).total_seconds()
        else:
            ds[k].encoding["add_offset"] = 0
    return ds


def sample_flags(da, period="1H", dim="time"):
    """Sample flags

    For a flag field, estimate percentage during which flag is set each
    period (default 1H)

    Must have .flag_masks and .flag_meanings following
    http://cfconventions.org/Data/cf-conventions/cf-conventions-1.7/build/ch03s05.html

    Arguments:

        da

            must have flag_masks and flag_meanings attributes

        period

        dim

    Returns:

        (percs, labels)
    """

    flags = da & xarray.DataArray(numpy.atleast_1d(da.flag_masks), dims=("flag",))
    perc = (100*(flags!=0)).resample(period, dim=dim, how="mean")
    # deeper dimensions
    for d in set(perc.dims) - {dim, "flag"}:
        perc = perc.mean(dim=d)
    
    return (perc, da.flag_meanings.split())


_root_logger_set = False
def set_logger(level, filename=None, root=True):
    """Set propertios of FIDUCEO root logger

    Arguments:

        level

            What loglevel to use.

        filename

            What file to log to.  None for sys.stderr.

        root

            Use root logger (True), so that it applies to modules outside
            FCDR_HIRS, or only apply it to FCDR_HIRS logging (False)
    """
    global _root_logger_set
    if root:
        if _root_logger_set:
            warnings.warn("Root logger already configured")
            return
        logger = logging.getLogger()
        _root_logger_set = True
    else:
        logger = logging.getLogger(__name__).parent # should be FCDR_HIRS
    if filename:
        handler = logging.FileHandler(filename, mode="a", encoding="utf-8")
    else:
        handler = logging.StreamHandler(sys.stderr)
    logger.setLevel(level)
    handler.setFormatter(
        logging.Formatter("%(levelname)-8s %(name)s %(asctime)s %(module)s.%(funcName)s:%(lineno)s: %(message)s"))
    logger.addHandler(handler)


def get_verbose_stack_description(first=2, last=-1, include_source=True,
                                    include_locals=True, include_globals=False):
    f = io.StringIO()
    f.write("".join(traceback.format_stack()))
    for fminfo in inspect.stack()[first:last]:
        frame = fminfo.frame
        try:
            f.write("-" * 60 + "\n")
            if include_source:
                try:
                    f.write(inspect.getsource(frame) + "\n")
                except OSError:
                    f.write(str(inspect.getframeinfo(frame)) + 
                         "\n(no source code)\n")
            if include_locals:
                f.write(pprint.pformat(frame.f_locals) + "\n")
            if include_globals:
                f.write(pprint.pformat(frame.f_globals) + "\n")
        finally:
            try:
                frame.clear()
            except RuntimeError:
                pass
    return f.getvalue()

def savetxt_3d(fname, data, *args, **kwargs):
    """Write 3D-array to file that pgfplots likes
    """
    with open(fname, 'wb') as outfile:
        for data_slice in data:
            numpy.savetxt(outfile, data_slice, *args, **kwargs)
            outfile.write(b"\n")

def plotdatadir():
    """Returns todays plotdatadir

    Configuration 'plotdatadir' must be set.  Value is expanded with
    strftime.
    """
    return datetime.date.today().strftime(
        config.conf["main"]["plotdatadir"])

