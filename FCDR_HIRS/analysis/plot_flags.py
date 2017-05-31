"""Plot flags.
"""

import matplotlib
matplotlib.use("Agg")
import argparse
from .. import common

def parse_cmdline():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parse = common.add_to_argparse(parser,
        include_period=True,
        include_sat=True,
        include_channels=False,
        include_temperatures=False)

    p = parser.parse_args()
    return p
parsed_cmdline = parse_cmdline()

import logging
logging.basicConfig(
    format=("%(levelname)-8s %(asctime)s %(module)s.%(funcName)s:"
            "%(lineno)s: %(message)s"),
    filename=parsed_cmdline.log,
    level=logging.DEBUG if parsed_cmdline.verbose else logging.INFO)


import datetime
import xarray
import numpy
import matplotlib.pyplot
import typhon.datasets.tovs
import pyatmlab.graphics

def parse_cmdline():
    pass

def plot(sat, start, end):
    h = typhon.datasets.tovs.which_hirs(sat)
    #h15 = typhon.datasets.tovs.HIRS3(satname="noaa15")
    M15 = h.read_period(
        start, end,
        reader_args={"max_flagged": 1.0, "apply_flags": False},
        fields=["hrs_qualind", "hrs_linqualflgs", "hrs_chqualflg",
                "hrs_mnfrqual", "time", "lat", "lon"])

    ds = h.as_xarray_dataset(M15)

    perc_all = []
    labels = []
    for fld in ("quality_flags_bitfield", "line_quality_flags_bitfield",
                "channel_quality_flags_bitfield",
                "minorframe_quality_flags_bitfield"):
        da = ds[fld]
        flags = da & xarray.DataArray(da.flag_masks, dims=("flag",))
        perc = (100*(flags!=0)).resample("1H", dim="time", how="mean")
        for d in set(perc.dims) - {"time", "flag"}:
            perc = perc.mean(dim=d)
        perc_all.append(perc)
        labels.extend(da.flag_meanings.split())

    (f, a) = matplotlib.pyplot.subplots(1, 1, figsize=(14, 9))

    perc = xarray.concat(perc_all, dim="flag")
    # I want 0 distinct from >0
    perc.values[perc.values==0] = numpy.nan
    perc.T.plot.pcolormesh(ax=a)
    a.set_yticks(numpy.arange(len(labels)))
    a.set_yticklabels(labels)
    a.set_title("Percentage of flag set per hour "
        "{:s} {:%Y%m%d}-{:%Y%m%d}".format(sat, start, end))
    a.grid(axis="x")
    #f.subplots_adjust(left=0.2)

    pyatmlab.graphics.print_or_show(f, False,
        "hirs_flags/{sat:s}_{start:%Y}/hirs_flags_set_{sat:s}_{start:%Y%m%d%H%M}-{end:%Y%m%d%H%M}.png".format(
            sat=sat, start=start, end=end))

def main():
    p = parsed_cmdline
    sat = p.satname
    start = datetime.datetime.strptime(p.from_date, p.datefmt)
    end = datetime.datetime.strptime(p.to_date, p.datefmt)
    plot(sat, start, end)
