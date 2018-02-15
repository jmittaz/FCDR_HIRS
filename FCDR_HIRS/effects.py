"""For the uncertainty effects
"""

import math
import abc
import collections
import copy
import numbers

import numpy
import xarray
import sympy

from typing import (Tuple, Mapping, Set)

from typhon.physics.units.common import (radiance_units, ureg)
from typhon.physics.units.tools import UnitsAwareDataArray as UADA

from . import measurement_equation as meq
from . import _fcdr_defs

WARNING = ("VERY EARLY TRIAL VERSION! "
           "DO NOT USE THE CONTENTS OF THIS PRODUCT FOR ANY PURPOSE UNDER ANY CIRCUMSTANCES! "
            "This serves exclusively as a file format demonstration!")
CorrelationType = collections.namedtuple("CorrelationType",
    ["within_scanline", "between_scanlines", "between_orbits",
    "across_time"])

CorrelationScale = collections.namedtuple("CorrelationScale",
    CorrelationType._fields)

class Rmodel(metaclass=abc.ABCMeta):
    """Derive R
    """

    @abc.abstractmethod
    def calc_R_eΛlkx(self, ds,
            sampling_l=1, sampling_e=1):
        """Return R_eΛlk for single k

        Dimensions [n_c, n_l, n_e, n_e]
        """

    @abc.abstractmethod
    def calc_R_lΛekx(self, ds,
        sampling_l=1, sampling_e=1):
        """Return R_lΛek for single k

        Dimensions [n_c, n_e, n_l, n_l]
        """

class RModelCalib(Rmodel):
    def calc_R_eΛlkx(self, ds,
        sampling_l=1, sampling_e=1):
        """Return R_eΛlk for single k

        Dimensions [n_c, n_l, n_e, n_e]
        """
        return numpy.ones(
            (ds.dims["calibrated_channel"],
             math.ceil(ds.dims["scanline_earth"]/sampling_l),
             math.ceil(ds.dims["scanpos"]/sampling_e),
             math.ceil(ds.dims["scanpos"]/sampling_e)), dtype="f4")

    def calc_R_lΛekx(self, ds,
            sampling_l=1, sampling_e=1):
        """Return R_lΛek for single k

        Dimensions [n_c, n_e, n_l, n_l]
        """

        # wherever scanline_earth shares a calibration_cycle the
        # correlation is 1; anywhere else, it's 0.
        ccid = (ds["scanline_earth"]>ds["calibration_cycle"]).sum("calibration_cycle").values
        R = (ccid[:, numpy.newaxis] == ccid[numpy.newaxis, :]).astype("f4")
        return numpy.tile(R[::sampling_l, ::sampling_l][
                numpy.newaxis, numpy.newaxis, :, :],
            (ds.dims["calibrated_channel"],
            math.ceil(ds.dims["scanpos"]/sampling_e),
            1, 1))

rmodel_calib = RModelCalib()

class RModelRandom(Rmodel):
    def calc_R_eΛlkx(self, ds,
        sampling_l=1, sampling_e=1):
        """Return R_eΛlk for single k

        Dimensions [n_c, n_l, n_e, n_e]
        """

        return numpy.tile(
            numpy.eye(math.ceil(ds.dims["scanpos"]/sampling_e), dtype="f4"),
            [ds.dims["calibrated_channel"], 
             math.ceil(ds.dims["scanline_earth"]/sampling_l), 1, 1])

    def calc_R_lΛekx(self, ds,
            sampling_l=1, sampling_e=1):
        """Return R_lΛek for single k

        Dimensions [n_c, n_e, n_l, n_l]
        """

        return numpy.tile(
            numpy.eye(math.ceil(ds.dims["scanline_earth"]/sampling_l), dtype="f4"),
            [ds.dims["calibrated_channel"],
            math.ceil(ds.dims["scanpos"]/sampling_e), 1, 1])

rmodel_random = RModelRandom()

class RModelCommon(Rmodel):
    def calc_R_eΛlkx(self, ds,
            sampling_l=1, sampling_e=1):
        raise ValueError(
            "We do not calculate error correlation matrices for common effects")
    calc_R_lΛekx = calc_R_eΛlkx

rmodel_common = RModelCommon()

class RModelPeriodicError(Rmodel):
    def calc_R_eΛlkx(self, ds,
            sampling_l=1, sampling_e=1):
        raise NotImplementedError()
    def calc_R_lΛekx(self, ds,
            sampling_l=1, sampling_e=1):
        raise NotImplementedError()
rmodel_periodicerror = RModelPeriodicError()

class RModelRSelf(Rmodel):
    def calc_R_eΛlkx(self, ds,
            sampling_l=1, sampling_e=1):
        raise NotImplementedError()
    def calc_R_lΛekx(self, ds,
            sampling_l=1, sampling_e=1):
        raise NotImplementedError()
rmodel_rself = RModelRSelf()

class Effect:
    """For uncertainty effects.

    Needs to have (typically set on creation):
    
    - name: short name 
    - description: description of effect
    - parameter: what it relates to
    - unit: pint unit
    - pdf_shape: str, defaults to "Gaussian"
    - channels_affected: str, defaults "all"
    - correlation_type: what the form of the correlation is (4×)
    - channel_correlations: channel correlation matrix
    - dimensions: list of dimension names or None, which means same as
      parameter it relates to.

    Additionally needs to have (probably set only later):

    - magnitude
    - correlation_scale

    Sensitivity coefficients are calculated on-the-fly using the
    measurement_equation module.
    """

    _all_effects = {}
    name = None
    description = None
    parameter = None
    unit = None
    pdf_shape = "Gaussian"
    channels_affected = "all"
    channel_correlations = None
    dimensions = None
    rmodel = None

    def __init__(self, **kwargs):
        later_pairs = []
        while len(kwargs) > 0:
            (k, v) = kwargs.popitem()
            if isinstance(getattr(self.__class__, k), property):
                # setter may depend on other values, do last
                later_pairs.append((k, v))
            else:
                setattr(self, k, v)
        while len(later_pairs) > 0:
            (k, v) = later_pairs.pop()
            setattr(self, k, v)
        if not self.parameter in self._all_effects.keys():
            self._all_effects[self.parameter] = set()
        self._all_effects[self.parameter].add(self)

    def __setattr__(self, k, v):
        if not hasattr(self, k):
            raise AttributeError("Unknown attribute: {:s}".format(k))
        super().__setattr__(k, v)

    def __repr__(self):
        return "<Effect {!s}:{:s}>\n".format(self.parameter, self.name) + (
            "{description:s} {dims!s} [{unit!s}]\n".format(
                description=self.description, dims=self.dimensions, unit=self.unit) +
            "Correlations: {!s} {!s}\n".format(self.correlation_type,
                self.correlation_scale) +
            "Magnitude: {!s}".format(self.magnitude))

    _magnitude = None
    @property
    def magnitude(self):
        """Magnitude of the uncertainty

        This should be a DataArray with dimensions matching the dimensions
        of the FCDR.  Assumed to be constant along any others.  Note that
        this means the magnitude of the uncertainty is constant; it does
        not mean anything about the error correlation, which is treated
        separately.
        """
#        if self._magnitude.identical(self._init_magnitude):
#            logging.warning("uncertainty magnitude not set for " +
#                self.name)
        return self._magnitude

    @magnitude.setter
    def magnitude(self, da):
        if not isinstance(da, xarray.DataArray):
            try:
                unit = da.u
            except AttributeError:
                unit = None

            da = xarray.DataArray(da)
            if unit is not None:
                da.attrs.setdefault("units", unit)

        if da.name is None:
            da.name = "u_{:s}".format(self.name)

        # make sure dimensions match
        # FIXME: make sure short names for effects always match the short
        # names used in _fcdr_defs so that the dictionary lookup works
        # EDIT 2017-02-13: Commenting this because I don't understand
        # why this is needed.  If I uncomment it later I should explain
        # clearly what is going on here.  It fails because uncertainty
        # magnitudes may have less dimensions than the quantities they relate to, in
        # particular when relating to systematic errors; for example, PRT
        # type B uncertainty has magnitude 0.1 across all dimensions.
        #da = da.rename(dict(zip(da.dims, _fcdr_defs.FCDR_data_vars_props[self.name][1])))

        da.attrs.setdefault("long_name", self.description)
        da.attrs["short_name"] = self.name
        da.attrs["parameter"] = str(self.parameter)
        da.attrs["pdf_shape"] = self.pdf_shape
        da.attrs["channels_affected"] = self.channels_affected
        for (k, v) in self.correlation_type._asdict().items():
            da.attrs["correlation_type_" + k] = v
            # FIXME: can an attribute have dimensions?  Or does this need to
            # be stored as a variable?  See
            # https://github.com/FIDUCEO/FCDR_HIRS/issues/47
            da.attrs["correlation_scale_" + k] = getattr(self.correlation_scale, k)
        da.attrs["channel_correlations"] = self.channel_correlations
        da.attrs["sensitivity_coefficient"] = str(self.sensitivity())
        da.attrs["WARNING"] = WARNING

        if not self.name.startswith("O_") or self.name in _fcdr_defs.FCDR_data_vars_props.keys():
            da.encoding.update(_fcdr_defs.FCDR_data_vars_props[self.name][3])
        da.encoding.update(_fcdr_defs.FCDR_uncertainty_encodings.get(self.name, {}))

        self._magnitude = da


    _corr_type = CorrelationType("undefined", "undefined", "undefined",
                                "undefined")
    _valid_correlation_types = ("undefined", "random",
                                "rectangular_absolute",
                                "triangular_relative",
                                "truncated_gaussian_relative",
                                "repeated_rectangles",
                                "repeated_truncated_gaussians")

    @property
    def correlation_type(self):
        """Form of correlation
        """
        return self._corr_type

    @correlation_type.setter
    def correlation_type(self, v):
        if not isinstance(v, CorrelationType):
            v = CorrelationType(*v)
        for x in v:
            if not x in self._valid_correlation_types:
                raise ValueError("Unknown correlation type: {:s}. "
                    "Expected one of: {:s}".format(
                        x, ", ".join(self._valid_correlation_types)))
        self._corr_type = v
            
    _corr_scale = CorrelationScale(*[0]*4)
    @property
    def correlation_scale(self):
        """Scale for correlation
        """
        return self._corr_scale

    @correlation_scale.setter
    def correlation_scale(self, v):
        if not isinstance(v, CorrelationScale):
            v = CorrelationScale(*v)
        for x in v:
            if not isinstance(x, (numbers.Number, numpy.ndarray)):
                raise TypeError("correlation scale must be numeric, "
                    "found {:s}".format(type(v)))
        self._corr_scale = v

    def sensitivity(self, s="R_e"):
        """Get expression for sensitivity coefficient

        Normally starting at R_e, but can provide other.

        Returns sympy expression.
        """

        return meq.calc_sensitivity_coefficient(s, self.parameter)

    def is_independent(self):
        """True if this effect is independent
        """

        return all(x=="random" for x in self.correlation_type)

    def is_common(self):
        """True if this effect is common
        """
        return all(x=="rectangular_absolute" for x in
                self.correlation_type) and all(numpy.isinf(i) for i in
                self.correlation_scale)

    def is_structured(self):
        """True if this effect is structured
        """

        return not self.is_independent() and not self.is_common()

    def calc_R_eΛlkx(self, ds,
            sampling_l=1, sampling_e=1):
        """Return R_eΛlk for single k

        Dimensions [n_c, n_l, n_e, n_e]
        """

        return self.rmodel.calc_R_eΛlkx(ds,
            sampling_l=sampling_l,
            sampling_e=sampling_e)

    def calc_R_lΛekx(self, ds,
            sampling_l=1, sampling_e=1):
        """Return R_lΛes or R_lΛei
        """
        return self.rmodel.calc_R_lΛekx(ds,
            sampling_l=sampling_l,
            sampling_e=sampling_e)

    def calc_R_cΛpx(self):
        """Return R_cΛps or R_cΛpi
        """

        raise NotImplementedError("Not implemented")

def effects() -> Mapping[sympy.Symbol, Set[Effect]]:
    """Initialise a new dictionary with all effects per symbol.

    Returns: Mapping[symbol, Set[Effect]]
    """
    return copy.deepcopy(Effect._all_effects)

_I = numpy.eye(19, dtype="f4")
_ones = numpy.ones(shape=(19, 19), dtype="f4")
_random = ("random",)*4
_calib = ("rectangular_absolute", "rectangular_absolute",
          "random", "triangular_relative")
_systematic = ("rectangular_absolute",)*4
_inf = (numpy.inf,)*4

earth_counts_noise = Effect(name="C_Earth",
    description="noise on Earth counts",
    parameter=meq.symbols["C_E"],
    correlation_type=_random,
    unit=ureg.count,
    channel_correlations=_I,
    dimensions=["calibration_cycle"], # FIXME: update if interpolated (issue#10)
    rmodel=rmodel_random,
    ) 

space_counts_noise = Effect(name="C_space",
    description="noise on Space counts",
    parameter=meq.symbols["C_s"],
    correlation_type=_calib,
    unit=ureg.count,
    channel_correlations=_I,
    dimensions=["calibration_cycle"],
    rmodel=rmodel_calib)

IWCT_counts_noise = Effect(name="C_IWCT",
    description="noise on IWCT counts",
    parameter=meq.symbols["C_IWCT"],
    correlation_type=_calib,
    unit=ureg.count,
    channel_correlations=_I,
    dimensions=["calibration_cycle"],
    rmodel=rmodel_calib)

SRF_calib = Effect(name="SRF_calib",
    description="Spectral response function calibration",
    parameter=meq.symbols["νstar"],
    correlation_type=_systematic,
    correlation_scale=_inf,
    unit=ureg.nm,
    dimensions=(),
    channel_correlations=_I,
    rmodel=rmodel_common)

# This one does not fit in measurement equation, how to code?
#
#SRF_RtoBT = Effect(description="Spectral response function radiance-to-BT",
#    parameter=meq.symbols["T_b"],
#    correlation_type=_systematic,
#    correlation_scale=_inf,
#    unit=ureg.nm,
#    channel_correlations=_I)

PRT_counts_noise = Effect(name="C_PRT",
    description="IWCT PRT counts noise",
    parameter=meq.symbols["C_PRT"],
    correlation_type=_calib,
    unit=ureg.count,
    dimensions=(),
    channel_correlations=_ones,
    rmodel=rmodel_calib)

IWCT_PRT_representation = Effect(
    name="O_TIWCT",
    description="IWCT PRT representation",
    parameter=meq.symbols["O_TIWCT"],
    correlation_type=_systematic,
    correlation_scale=_inf,
    unit=ureg.K,
    dimensions=(),
    channel_correlations=_ones,
    rmodel=rmodel_calib)

IWCT_PRT_counts_to_temp = Effect(
    name="d_PRT",
    description="IWCT PRT counts to temperature",
    parameter=meq.symbols["d_PRT"], # Relates to free_symbol but actual
        # parameter in measurement equation to be replaced relates to as
        # returned by typhon.physics.metrology.recursive_args; need to
        # translate in some good way
    correlation_type=_systematic,
    correlation_scale=_inf,
    unit=ureg.counts/ureg.K, # FIXME WARNING: see https://github.com/FIDUCEO/FCDR_HIRS/issues/43
    dimensions=(),
    channel_correlations=_ones,
    rmodel=rmodel_calib)

IWCT_type_b = Effect(
    name="O_TPRT",
    description="IWCT type B",
    parameter=meq.symbols["O_TPRT"],
    correlation_type=_systematic,
    correlation_scale=_inf,
    unit=ureg.K,
    dimensions=(),
    channel_correlations=_ones,
    rmodel=rmodel_calib)
# set magnitude when I'm sure everything else has been set (order of
# kwargs not preserved before Python 3.6)
IWCT_type_b.magnitude=UADA(0.1, name="uncertainty", attrs={"units": "K"})

blockmat = numpy.vstack((
            numpy.hstack((
                numpy.ones(shape=(12,12)),
                numpy.zeros(shape=(12,9)))),
            numpy.hstack((
                numpy.zeros(shape=(9,12)),
                numpy.ones(shape=(9,9))))))
nonlinearity = Effect(
    name="a_2",
    description="Nonlinearity",
    parameter=meq.symbols["a_2"],
    correlation_type=_systematic,
    correlation_scale=_inf,
    unit=radiance_units["si"]/ureg.count**2,
    dimensions=(),
    channel_correlations=blockmat,
    rmodel=rmodel_common)
nonlinearity.magnitude=UADA(
    3e-20, # equivalent to 1e-6 in ir units
    name="uncertainty",
    attrs={"units": radiance_units["si"]/ureg.count**2,
           "note": "Placeholder uncertainty awaiting proper "
                   "harmonisation"})

nonnonlinearity = Effect(
    name="O_Re",
    description="Wrongness of nonlinearity",
    parameter=meq.symbols["O_Re"],
    correlation_type=_systematic,
    correlation_scale=_inf,
    unit=radiance_units["ir"],
    dimensions=(),
    channel_correlations=nonlinearity.channel_correlations,
    rmodel=rmodel_common)

Earthshine = Effect(
    name="Earthshine",
    description="Earthshine",
    parameter=meq.symbols["R_refl"],
    correlation_type=("rectangular_absolute", "rectangular_absolute",
          "repeated_rectangles", "triangular_relative"),
    channel_correlations=blockmat,
    dimensions=(),
    unit=radiance_units["ir"],
    rmodel=rmodel_calib)

Rself = Effect(
    name="Rself",
    dimensions=("rself_update_time",),
    description="self-emission",
    parameter=meq.symbols["R_selfE"],
    correlation_type=("rectangular_absolute", "triangular_relative",
        "triangular_relative", "repeated_rectangles"),
    channel_correlations=blockmat,
    unit=radiance_units["ir"],
    rmodel=rmodel_rself)

Rselfparams = Effect(
    name="Rselfparams",
    description="self-emission parameters",
    parameter=Rself.parameter,
    correlation_type=Rself.correlation_type,
    channel_correlations=blockmat,
    dimensions=(),
    unit=Rself.unit,
    rmodel=rmodel_rself)

electronics = Effect(
    name="electronics",
    description="unknown electronics effects",
    parameter=meq.symbols["O_Re"],
    correlation_type=_systematic,
    correlation_scale=_inf,
    channel_correlations=blockmat,
    dimensions=(),
    unit=radiance_units["ir"],
    rmodel=rmodel_common)

unknown_periodic = Effect(
    name="extraneous_periodic",
    description="extraneous periodic signal",
    parameter=meq.symbols["O_Re"],
    #correlation_type=_systematic,
    #correlation_scale=_inf,
    #channel_correlations=blockmat,
    dimensions=(),
    unit=radiance_units["ir"],
    rmodel=rmodel_periodicerror)

Δα = Effect(
    name="α",
    description="uncertainty in band correction factor α (ad-hoc)",
    parameter=meq.symbols["α"],
    correlation_type=_systematic,
    correlation_scale=_inf,
    channel_correlations=_I,
    dimensions=(),
    unit="1",
    rmodel=rmodel_common)

Δβ = Effect(
    name="β",
    description="uncertainty in band correction factor β (ad-hoc)",
    parameter=meq.symbols["β"],
    correlation_type=_systematic,
    correlation_scale=_inf,
    channel_correlations=_I,
    dimensions=(),
    unit="1/K",
    rmodel=rmodel_common),

Δf_eff = Effect(
    name="f_eff",
    description="uncertainty in band correction centroid",
    parameter=meq.symbols["fstar"],
    correlation_type=_systematic,
    correlation_scale=_inf,
    channel_correlations=_I,
    dimensions=(),
    unit="THz",
    rmodel=rmodel_common)
