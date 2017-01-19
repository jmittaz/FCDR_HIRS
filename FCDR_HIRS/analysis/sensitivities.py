#!/usr/bin/env python

"""Symbolically calculate sensitivity parameters
"""

import pathlib
import sympy
import sympy.printing
import typhon.config

template="""
<!DOCTYPE html>
<html>
<head>
<script type="text/javascript"
  src="http://cdn.mathjax.org/mathjax/latest/MathJax.js?config=TeX-AMS-MML_HTMLorMML">
</script>
<title>tex texample</title>
</head>
<body>

$${latex:s}$$

</body>
</html>
"""

(R_e, a_2, C_s, R_selfIWCT, C_IWCT, C_E, R_selfE, R_selfs, ε, λ, a_3,
    R_refl, d_PRTnk, C_PRTn, k, n, K, N, h, c, k_b) = sympy.symbols(
        "R_e a_2 C_s R_selfIWCT C_IWCT C_E R_selfE R_selfs ε λ "
        "a_3 R_refl d_prtn C_prtk k n K N h c k_b")

# further variables
(T_PRT, T_IWCT, B, φ, R_IWCT, ε, a_1, a_0) = sympy.symbols(
    "T_PRT T_IWCT B φ R_IWCT ε a_1 a_0")

# abstract functions
T_PRT_func = sympy.Function("T_PRT")(d_PRTnk, C_PRTn, K)
T_IWCT_func = sympy.Function("T_IWCT")(T_PRT, N)
T_IWCT_fullfunc = sympy.Function("T_IWCT")(T_PRT_func, N)
B_func = sympy.Function("B")(λ, T_IWCT)
B_fullfunc = sympy.Function("B")(λ, T_IWCT_fullfunc)
φ_func = sympy.Function("φ")(λ)#, T_IWCT)
φ_fullfunc = sympy.Function("φ")(λ)#, T_IWCT_fullfunc)
R_IWCT_func = sympy.Function("R_IWCT")(ε, a_3, B, R_refl, φ, λ)
R_IWCT_fullfunc = sympy.Function("R_IWCT")(ε, a_3, B_fullfunc, R_refl, φ_fullfunc, λ)
ε_func = sympy.Function("ε")(λ, T_IWCT)
a_1_func = sympy.Function("a_1")(R_IWCT, R_selfIWCT, R_selfs, a_2, C_IWCT, C_s)
a_1_fullfunc = sympy.Function("a_1")(R_IWCT_fullfunc, R_selfIWCT, R_selfs, a_2, C_IWCT, C_s)
a_0_func = sympy.Function("a_0")(C_s, a_1)
a_0_fullfunc = sympy.Function("a_0")(C_s, a_1_fullfunc)

T_PRT_full = sympy.Sum(d_PRTnk * C_PRTn**k, (k, 0, K-1))
T_IWCT_semi = sympy.Sum(T_PRT, (n, 1, N))/N
T_IWCT_full = T_IWCT_semi.subs(T_PRT, T_PRT_full)
#B_full = (2*h*c**2)/(λ**5) * 1/(sympy.exp((h*c)/(λ*k_b*T_IWCT_full))-1)
B_semi = (2*h*c**2)/(λ**5) * 1/(sympy.exp((h*c)/(λ*k_b*T_IWCT))-1)
B_full = B_semi.subs(T_IWCT, T_IWCT_full)
R_IWCT_semi = (sympy.Integral(((ε + a_3) * B + (1-ε-a_3)*R_refl) * φ, λ)) / sympy.Integral(φ, λ)
R_IWCT_full = R_IWCT_semi.subs(B, B_full).subs(φ, φ_fullfunc)
#a_1_full = (R_IWCT_full + R_selfIWCT - R_selfs - a_2*(C_IWCT**2-C_s**2))/(C_IWCT-C_s)
#a_0_full = -2*C_s**2 - a_1_full*C_s
#R_e_full = a_0_full + a_1_full*C_E + a_2*C_E**2 - R_selfE

a_1_semi = (R_IWCT + R_selfIWCT - R_selfs - a_2*(C_IWCT**2-C_s**2))/(C_IWCT-C_s)
a_1_full = a_1_semi.subs(R_IWCT, R_IWCT_full)
a_0_semi = -a_2*C_s**2 - a_1*C_s
a_0_full = a_0_semi.subs(a_1, a_1_full)

R_e_basic = a_0 + a_1*C_E + a_2*C_E**2 - R_selfE
R_e_func = R_e_basic.subs(a_0, a_0_func).subs(a_1, a_1_func)
#R_e_func = a_0_func + a_1_func*C_E + a_2*C_E**2 - R_selfE
R_e_fullfunc = R_e_basic.subs(a_0, a_0_fullfunc).subs(a_1, a_1_fullfunc)
#R_e_fullfunc = a_0_fullfunc + a_1_fullfunc*C_E + a_2*C_E**2 - R_selfE
#R_e_semi = a_0_semi + a_1_semi*C_E + a_2*C_E**2 - R_selfE
R_e_semi = R_e_basic.subs(a_0,a_0_semi).subs(a_1, a_1_semi)
R_e_full = R_e_basic.subs(a_0,a_0_full).subs(a_1, a_1_full)

def print_and_write(eq, fn):
    eq = eq.simplify()
    print("Writing to {!s}".format(fn))
    fn.parent.mkdir(parents=True, exist_ok=True)
    with fn.open('w') as fp:
        fp.write(template.format(latex=
            sympy.printing.latex(eq).replace(
                "ε", r"\epsilon").replace(
                "λ", r"\lambda").replace(
                "φ", r"\phi")))
    sympy.pprint(eq)
        
def main():
    outdir = pathlib.Path(
        typhon.config.conf["main"]["myscratchdir"]) / "sensitivity"

    print("R_e=")
    sympy.pprint(R_e_basic)
    print("=")
    sympy.pprint(R_e_func)
    print("=")
    sympy.pprint(R_e_fullfunc)
    print("=")
    sympy.pprint(R_e_semi)
    print("=")
    sympy.pprint(R_e_full)

    print("∂R_e/∂C_E =")
    print_and_write(sympy.diff(R_e_basic, C_E), outdir / "C_e.html")
    print("∂R_e/∂C_s =")
    print_and_write(sympy.diff(
        R_e_basic.subs(
            a_0, a_0_semi).subs(
            a_1, a_1_semi),
        C_s), outdir / "C_s.html")
    print("∂R_e/∂C_IWCT =")
    print_and_write(sympy.diff(
        R_e_basic.subs(
            a_0, a_0_semi).subs(
                a_1, a_1_semi),
        C_IWCT), outdir / "C_IWCT.html")
    print("∂R_e/∂C_PRTn =")
    print_and_write(sympy.diff(R_e_full, C_PRTn), outdir / "C_PRTn.html")
    print("∂R_e/∂d_PRTnk =")
    print_and_write(sympy.diff(R_e_full, d_PRTnk), outdir / "d_PRTnk.html")
    # FIXME: should be able to automatically do this, see
    # https://github.com/FIDUCEO/FCDR_HIRS/issues/41
    print("∂R_e/∂T_IWCT =")
    print_and_write(sympy.diff(
        R_e_basic.subs(
            a_0, a_0_semi).subs(
            a_1, a_1_semi).subs(
            R_IWCT, R_IWCT_semi).subs(
            B, B_semi),
        T_IWCT), outdir / "T_IWCT.html")
    print("∂R_e/∂T_IWCT =")
    print_and_write(sympy.diff(
        R_e_basic.subs(
            a_0, a_0_semi).subs(
            a_1, a_1_semi).subs(
            R_IWCT, R_IWCT_semi).subs(
            B, B_semi).subs(
            T_IWCT, T_IWCT_semi).subs(
            φ, φ_func),
        T_PRT), outdir / "T_PRT.html")
    print("∂R_e/∂a_3 =")
    print_and_write(sympy.diff(
        R_e_basic.subs(
            a_0, a_0_semi).subs(
            a_1, a_1_semi).subs(
            R_IWCT, R_IWCT_semi).subs(
            φ, φ_func),
        a_3), outdir / "a_3.html")
    print("∂R_e/∂a_2 =")
    print_and_write(sympy.diff(
        R_e_basic.subs(
            a_0, a_0_semi).subs(
            a_1, a_1_semi),
        a_2), outdir / "a_2.html")
    print("∂R_e/∂R_refl =")
    print_and_write(sympy.diff(
        R_e_basic.subs(
            a_0, a_0_semi).subs(
            a_1, a_1_semi).subs(
            R_IWCT, R_IWCT_semi).subs(
            φ, φ_func),
        R_refl), outdir / "R_refl.html")

