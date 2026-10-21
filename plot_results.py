"""
plot_results.py — figures for the Hamiltonian-simulation verification.

Reads hamsim_results.json (written by hamsim_check.py) and, for the curves
that need finer resolution than the harness grid, calls the same
degree/step functions the harness uses. Writes PNG + PDF into figures/.

    python hamsim_check.py      # produces hamsim_results.json (~7 min)
    python plot_results.py      # produces figures/ (~10 s)

Figures
  1  accuracy       actual error vs target eps, one panel per method (Layer A)
  2  repetitions    repetitions needed vs eps: theory curves + simulated points (Layer A)
  3  vs_slide       per-degree and setup vertex cost, ours vs the slide's (Layer B)
  4  optimization   vertices vs peak live qubits, before/after Pauli removal (Layer B)
  5  cheaper_map    which of QSVT/GQSP is cheaper for each degree pair, slide vs ours (Layer C)
  6  equal_accuracy total vertices to reach the same eps, all methods (Layer C)

Colors are fixed per method across every figure (and every method also has
its own marker), so a method looks the same everywhere.
"""

from __future__ import annotations

import json
import os
from fractions import Fraction

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from ham_sim import gqsp_degree, qsvt_degree, trotter_steps
from circuits import IsingChain
from scipy.linalg import expm
from numpy.polynomial import chebyshev as cheb

from circuits import IsingChain, qsvt_circuit, gqsp_circuit
from ham_sim import postselected_block, product_formula, op_norm
from qsp_angles import chebyshev_coeffs_cos_sin, qsvt_phases, gqsp_hamsim_polynomial, gqsp_angles

# ---------------------------------------------------------------------------
# Style: one color + one marker per method, recessive axes and grid
# ---------------------------------------------------------------------------

COLOR = {"qsvt": "#2a78d6", "gqsp": "#eb6834", "trotter2": "#1baf7a", "trotter1": "#eda100"}
MARKER = {"qsvt": "o", "gqsp": "s", "trotter2": "^", "trotter1": "D"}
NAME = {"qsvt": "QSVT", "gqsp": "GQSP", "trotter2": "Trotter (2nd order)", "trotter1": "Trotter (1st order)"}
INK, INK_2, GRID, NEUTRAL = "#0b0b0b", "#52514e", "#e6e5e0", "#bdbcb6"

plt.rcParams.update({
    "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10,
    "text.color": INK, "axes.labelcolor": INK, "xtick.color": INK_2, "ytick.color": INK_2,
    "axes.edgecolor": INK_2, "axes.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "lines.linewidth": 1.6, "lines.markersize": 6, "legend.frameon": False,
    "figure.facecolor": "white", "savefig.facecolor": "white", "savefig.bbox": "tight",
})

OUT = "figures"


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(os.path.join(OUT, f"{name}.{ext}"), dpi=200)
    plt.close(fig)
    print(f"  {OUT}/{name}.png")


def label_line_end(ax, x, y, text, color, dx=4, dy=0):
    """Direct label just right of a line's last point (text in ink, a colored marker beside it)."""
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points",
                va="center", ha="left", fontsize=9, color=INK)


def formula(results, tag, method, q="N"):
    """(a, b, c, e) as floats for value = (a n + b) k + c n + e."""
    return [float(Fraction(c)) for c in results["formulas"][tag][method][q]["coef"]]


def evaluate(f, n, k):
    a, b, c, e = f
    return (a * n + b) * k + c * n + e


# ---------------------------------------------------------------------------
# Figure 1: accuracy — every run lands below the error = eps line
# ---------------------------------------------------------------------------

def fig_accuracy(results):
    rows = results["accuracy"]
    methods = ["trotter1", "trotter2", "qsvt", "gqsp"]
    fig, axes = plt.subplots(1, 4, figsize=(12, 3.4), sharex=True, sharey=True)
    eps_line = np.array([3e-6, 3e-2])
    for ax, m in zip(axes, methods):
        ax.fill_between(eps_line, eps_line, 1, color=GRID, alpha=0.6, lw=0, zorder=0)
        ax.plot(eps_line, eps_line, ls="--", color=INK_2, lw=1, zorder=1)
        for r in (r for r in rows if r["method"] == m):
            filled = r["t"] > 1
            jitter = 1.12 if r["n"] == 3 else 1 / 1.12          # separate n=2 / n=3 horizontally
            ax.plot(r["eps"] * jitter, r["err"], MARKER[m], ms=7, mec=COLOR[m], mew=1.4,
                    mfc=COLOR[m] if filled else "white", zorder=3)
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xlim(*eps_line); ax.set_ylim(1e-9, 1e-1)
        ax.set_title(NAME[m], loc="left")
        ax.set_xlabel("target error ε")
        ok = all(r["ok"] for r in rows if r["method"] == m)
        ax.text(0.97, 0.04, "all within ε" if ok else "SOME FAIL", transform=ax.transAxes,
                ha="right", va="bottom", fontsize=9, color=INK_2)
    axes[0].set_ylabel(r"actual error  $\|\,\mathrm{block} - e^{-iHt}\|$")
    axes[0].text(1e-5, 2e-5 * 1.6, "error = ε", rotation=33, fontsize=8, color=INK_2)
    axes[0].text(4e-6, 1.5e-2, "fails", fontsize=8, color=INK_2)
    handles = [Line2D([], [], marker="o", ls="", mec=INK_2, mfc="white", ms=7, label="t = 0.5"),
               Line2D([], [], marker="o", ls="", mec=INK_2, mfc=INK_2, ms=7, label="t = 2"),
               Line2D([], [], ls="", label="left / right of each ε: n = 2 / n = 3")]
    fig.legend(handles=handles, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.06), fontsize=9)
    fig.suptitle("Layer A — repetitions chosen from theory always reach the target accuracy",
                 x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    save(fig, "fig1_accuracy")


# ---------------------------------------------------------------------------
# Figure 2: repetitions needed vs eps — 1/eps, 1/sqrt(eps), log(1/eps)
# ---------------------------------------------------------------------------

def fig_repetitions(results, n=3, t=2.0):
    H = IsingChain.random(n, seed=n)          # same Hamiltonian as the harness's Layer A
    eps = np.logspace(-1, -10, 37)
    curves = {
        "trotter1": [trotter_steps(H, t, e, 1) for e in eps],
        "trotter2": [trotter_steps(H, t, e, 2) for e in eps],
        "qsvt": [3 * qsvt_degree(H, t, e) for e in eps],
        "gqsp": [2 * gqsp_degree(H, t, e) for e in eps],
    }
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    label_offset = {"qsvt": 7, "gqsp": -7}          # the two QSP curves end close together
    for m, ys in curves.items():
        ax.plot(eps, ys, color=COLOR[m], lw=1.8, drawstyle="steps-mid" if m in ("qsvt", "gqsp") else "default")
        sim = [r for r in results["accuracy"] if r["method"] == m and r["n"] == n and r["t"] == t]
        ax.plot([r["eps"] for r in sim], [r["reps"] for r in sim], MARKER[m], ms=7,
                mfc=COLOR[m], mec="white", mew=1.2, zorder=3)
        label_line_end(ax, eps[-1], ys[-1], NAME[m], COLOR[m], dy=label_offset.get(m, 0))
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.invert_xaxis()
    ax.set_xlim(1.5e-1, 1e-12)
    ax.set_xlabel("target error ε   (more precise →)")
    ax.set_ylabel("repetitions\n(Trotter steps, or block-encoding calls)")
    for x, y, txt in ((1e-6, 6e5, "∝ 1/ε"), (1e-7, 3.5e3, "∝ 1/√ε"), (1e-7, 12, "∝ log(1/ε)")):
        ax.text(x, y, txt, fontsize=9, color=INK_2)
    ax.legend(handles=[Line2D([], [], color=INK_2, label="from the theory (bound / series truncation)"),
                       Line2D([], [], marker="o", ls="", mfc=INK_2, mec="white", ms=7,
                              label="simulated in Layer A (error ≤ ε confirmed)")],
              loc="upper left", fontsize=9)
    ax.set_title(f"How many repetitions each method needs   (n = {n}, t = {t:g}, α = {H.alpha:.1f})", loc="left")
    fig.tight_layout()
    save(fig, "fig2_repetitions")


# ---------------------------------------------------------------------------
# Figure 3: our vertex formulas vs the slide's
# ---------------------------------------------------------------------------

def fig_vs_slide(results):
    ns = np.arange(2, 65)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    for m in ("qsvt", "gqsp"):
        a, b, c, e = formula(results, "optimized", m)
        sa, sb, sc, se = results["slide_N"][m]
        # per-degree cost (a n + b) and one-time setup cost (c n + e)
        for ax, ours, slide in ((ax1, a * ns + b, sa * ns + sb), (ax2, c * ns + e, sc * ns + se)):
            ax.plot(ns, ours, color=COLOR[m], lw=2)
            ax.plot(ns[::6], slide[::6], MARKER[m], ls="none", ms=7, mfc="white", mec=COLOR[m], mew=1.4)
            ax.plot(ns, slide, color=COLOR[m], lw=1, ls="--")
    # direct labels
    a_q, b_q, *_ = formula(results, "optimized", "qsvt")
    a_g, b_g, *_ = formula(results, "optimized", "gqsp")
    sg = results["slide_N"]["gqsp"]
    arrow = dict(arrowstyle="-", color=INK_2, lw=0.6)
    ax1.annotate("QSVT: ours = slide = 36n − 18\n(lines coincide)", (33, a_q * 33 + b_q), xytext=(39, 790),
                 fontsize=9, va="bottom", arrowprops=arrow)
    ax1.annotate(f"GQSP ours: {a_g:g}n − {abs(b_g):g}", (52, a_g * 52 + b_g), xytext=(-140, 10),
                 textcoords="offset points", fontsize=9, arrowprops=arrow)
    ax1.annotate(f"GQSP slide: {sg[0]}n − {abs(sg[1])}", (58, sg[0] * 58 + sg[1]), xytext=(44, 180),
                 fontsize=9, arrowprops=arrow)
    ax1.set_title("Vertices per degree", loc="left")
    ax2.set_title("One-time setup vertices", loc="left")
    for ax in (ax1, ax2):
        ax.set_xlabel("data qubits n")
        ax.set_ylim(bottom=0)
    ax1.set_ylabel("vertices")
    handles = [Line2D([], [], color=COLOR["qsvt"], lw=2, label="QSVT"),
               Line2D([], [], color=COLOR["gqsp"], lw=2, label="GQSP"),
               Line2D([], [], color=INK_2, lw=2, label="ours (optimized, fitted exactly)"),
               Line2D([], [], color=INK_2, lw=1, ls="--", marker="o", mfc="white", label="slide")]
    ax2.legend(handles=handles, loc="upper left", fontsize=9)
    fig.suptitle("Layer B — our MBQC vertex counts vs the slide's formulas  "
                 "[vertices = (per-degree) × degree + setup]", x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    save(fig, "fig3_vs_slide")


# ---------------------------------------------------------------------------
# Figure 4: what Pauli-measurement removal buys and costs
# ---------------------------------------------------------------------------

def fig_optimization(results):
    fig, ax = plt.subplots(figsize=(7.5, 5))
    for m in ("trotter2", "qsvt", "gqsp"):
        before = {(p["n"], p["k"]): p for p in results["counts"]["unoptimized"][m]}
        after = {(p["n"], p["k"]): p for p in results["counts"]["optimized"][m]}
        for key in before:
            b, a = before[key], after[key]
            ax.annotate("", xy=(a["space"], a["N"]), xytext=(b["space"], b["N"]),
                        arrowprops=dict(arrowstyle="-|>", color=NEUTRAL, lw=0.7, shrinkA=4, shrinkB=4))
            ax.plot(b["space"], b["N"], MARKER[m], ms=7, mfc="white", mec=COLOR[m], mew=1.4, zorder=3)
            ax.plot(a["space"], a["N"], MARKER[m], ms=7, mfc=COLOR[m], mec="white", mew=1, zorder=3)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("peak live qubits (max_space)")
    ax.set_ylabel("total vertices N")
    handles = ([Line2D([], [], marker=MARKER[m], ls="", ms=7, mfc=COLOR[m], mec=COLOR[m], label=NAME[m])
                for m in ("trotter2", "qsvt", "gqsp")]
               + [Line2D([], [], marker="o", ls="", ms=7, mfc="white", mec=INK_2, label="unoptimized"),
                  Line2D([], [], marker="o", ls="", ms=7, mfc=INK_2, mec=INK_2, label="optimized (Pauli removal)")])
    ax.legend(handles=handles, loc="upper right", fontsize=9)
    ax.set_title("Optimization trades vertices for memory  (each arrow = one compiled circuit)", loc="left")
    ax.text(0.98, 0.03, "arrows point down and right:\nfewer vertices, more qubits alive at once",
            transform=ax.transAxes, fontsize=9, color=INK_2, va="bottom", ha="right")
    fig.tight_layout()
    save(fig, "fig4_optimization")


# ---------------------------------------------------------------------------
# Figure 5: which method is cheaper for each pair of degrees (slide vs ours)
# ---------------------------------------------------------------------------

def _cheaper_map(fq, fg, degrees_q, degrees_g, ns):
    """0 = GQSP cheaper for all n, 1 = QSVT cheaper for all n, 2 = depends on n."""
    grid = np.zeros((len(degrees_g), len(degrees_q)), dtype=int)
    for i, g in enumerate(degrees_g):
        for j, d in enumerate(degrees_q):
            diff = np.array([evaluate(fq, n, d) - evaluate(fg, n, g) for n in ns])
            grid[i, j] = 0 if (diff > 0).all() else 1 if (diff < 0).all() else 2
    return grid


def fig_cheaper_map(results):
    from matplotlib.colors import ListedColormap
    ns = np.arange(2, 65)
    odd = np.arange(3, 33, 2)
    sq, sg = results["slide_N"]["qsvt"], results["slide_N"]["gqsp"]
    maps = [("Slide's formulas", _cheaper_map(sq, sg, odd, odd, ns), "GQSP degree g"),
            ("Our optimized formulas", _cheaper_map(formula(results, "optimized", "qsvt"),
                                                    formula(results, "optimized", "gqsp"), odd, odd, ns),
             "GQSP Laurent degree d")]
    cmap = ListedColormap([COLOR["gqsp"], COLOR["qsvt"], "#e6e5e0"])
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6))
    for ax, (title, grid, ylab) in zip(axes, maps):
        ax.imshow(grid, origin="lower", cmap=cmap, vmin=0, vmax=2, aspect="equal",
                  extent=(odd[0] - 1, odd[-1] + 1, odd[0] - 1, odd[-1] + 1))
        # 2px-style gaps between cells
        for v in np.arange(odd[0] - 1, odd[-1] + 2, 2):
            ax.axvline(v, color="white", lw=1)
            ax.axhline(v, color="white", lw=1)
        ax.plot([2, 32], [2, 32], color=INK, lw=1, ls="--")
        ax.text(23, 23, "equal degree", rotation=45, fontsize=8, color=INK, ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none"))
        ax.grid(False)
        ax.set_title(title, loc="left")
        ax.set_xlabel("QSVT degree D")
        ax.set_ylabel(ylab)
    legend = [Patch(color=COLOR["gqsp"], label="GQSP fewer vertices (all n ≤ 64)"),
              Patch(color=COLOR["qsvt"], label="QSVT fewer vertices (all n ≤ 64)"),
              Patch(color="#e6e5e0", label="depends on n")]
    fig.legend(handles=legend, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.04), fontsize=9)
    fig.suptitle("Layer C — same question, different compiler, opposite answer:  which uses fewer vertices?",
                 x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    save(fig, "fig5_cheaper_map")


# ---------------------------------------------------------------------------
# Figure 6: total cost at equal accuracy
# ---------------------------------------------------------------------------

def fig_equal_accuracy(results, n=16, ts=(1.0, 10.0)):
    H = IsingChain.random(n, seed=n)
    eps = np.logspace(-1, -10, 46)
    fig, axes = plt.subplots(1, len(ts), figsize=(11, 4.4), sharey=True)
    for ax, t in zip(axes, ts):
        reps = {"trotter2": [trotter_steps(H, t, e, 2, exact=False) for e in eps],
                "qsvt": [qsvt_degree(H, t, e) for e in eps],
                "gqsp": [gqsp_degree(H, t, e) for e in eps]}
        totals = {}
        for m, ks in reps.items():
            f = formula(results, "optimized", m)
            totals[m] = np.array([evaluate(f, n, k) for k in ks])
            ax.plot(eps, totals[m], color=COLOR[m], lw=1.8)
            ax.plot(eps[::5], totals[m][::5], MARKER[m], ms=6, mfc=COLOR[m], mec="white", mew=1, ls="none")
            label_line_end(ax, eps[-1], totals[m][-1], NAME[m], COLOR[m])
        # crossover between Trotter and the cheaper QSP-type method, interpolated in log-log
        best_qsp = np.minimum(totals["qsvt"], totals["gqsp"])
        gap = np.log(totals["trotter2"]) - np.log(best_qsp)
        i = np.where(np.diff(np.sign(gap)) != 0)[0]
        if len(i):
            i = i[0]
            frac = gap[i] / (gap[i] - gap[i + 1])
            x = 10 ** (np.log10(eps[i]) + frac * (np.log10(eps[i + 1]) - np.log10(eps[i])))
            ax.axvline(x, color=INK_2, lw=0.8, ls=":")
            ax.text(x, best_qsp.min() / 3, f" crossover\n ε ≈ {x:.0e}", fontsize=8, color=INK_2, va="top")
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.invert_xaxis()
        ax.set_xlim(1.5e-1, 1e-12)
        ax.set_title(f"t = {t:g}", loc="left")
        ax.set_xlabel("target error ε   (more precise →)")
    axes[0].set_ylabel("total vertices N (optimized formulas)")
    fig.suptitle(f"Layer C — cost to reach the same accuracy  (n = {n}, α = {H.alpha:.1f}; "
                 "Trotter steps from the norm bound)", x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    save(fig, "fig6_equal_accuracy")


def plot_error_vs_repetitions(n=2, t=1.0, seed=None, trotter_steps=None, qsvt_degrees=None,
                              gqsp_degrees=None, eps=None, floor=1e-6, ax=None):
    """Actual error ||U_method - e^{-iHt}|| vs repetitions for Trotter (2nd order), QSVT and GQSP.

    x axis: Trotter steps r for Trotter; block-encoding calls for QSVT (3D) and GQSP (2d).
    QSVT/GQSP polynomials are scaled to stay below 1 in magnitude (required by angle
    finding); that scaling sets an error floor of about `floor`.
    """
    H = IsingChain.random(n, seed=n if seed is None else seed)
    exact = expm(-1j * H.matrix() * t)
    tau = H.alpha * t
    x = np.cos(np.linspace(0, np.pi, 2001))

    trotter_steps = trotter_steps or sorted({int(r) for r in np.logspace(0, 3, 30)})
    qsvt_degrees = qsvt_degrees or list(range(3, int(tau) + 26, 2))       # QSVT degree D (odd)
    gqsp_degrees = gqsp_degrees or list(range(1, int(tau) + 21))          # GQSP Laurent degree d

    results = {"Trotter (2nd order)": [], "QSVT": [], "GQSP": []}

    for r in trotter_steps:
        results["Trotter (2nd order)"].append((r, op_norm(product_formula(H, t, r, order=2) - exact)))

    for D in qsvt_degrees:
        c_cos, c_sin = chebyshev_coeffs_cos_sin(tau, D - 1, "cos"), chebyshev_coeffs_cos_sin(tau, D, "sin")
        peak = max(np.abs(cheb.chebval(x, c_cos)).max(), np.abs(cheb.chebval(x, c_sin)).max())
        beta = min(1 - floor, (1 - floor) / peak)
        try:
            hc = qsvt_circuit(H, qsvt_phases(c_cos, beta), qsvt_phases(c_sin, beta))
        except RuntimeError:            # angle finding didn't converge at this degree
            continue
        results["QSVT"].append((hc.calls, op_norm(postselected_block(hc) - exact)))

    for d in gqsp_degrees:
        p = gqsp_hamsim_polynomial(tau, d, 1.0)
        peak = np.abs(np.polyval(p[::-1], np.exp(1j * np.linspace(0, 2 * np.pi, 4001)))).max()
        try:
            angles = gqsp_angles(gqsp_hamsim_polynomial(tau, d, min(1 - floor, (1 - floor) / peak)))
        except (RuntimeError, ValueError):
            continue
        hc = gqsp_circuit(H, *angles)
        results["GQSP"].append((hc.calls, op_norm(postselected_block(hc) - exact)))

    style = {"Trotter (2nd order)": ("#1baf7a", "^"), "QSVT": ("#2a78d6", "o"), "GQSP": ("#eb6834", "s")}
    if ax is None:
        _, ax = plt.subplots(figsize=(7, 4.5))
    for name, pts in results.items():
        if pts:
            reps, errs = zip(*pts)
            color, marker = style[name]
            ax.plot(reps, errs, marker=marker, color=color, ms=5, lw=1.6, label=name)
    if eps is not None:
        ax.axhline(eps, color="#52514e", ls="--", lw=1, label=f"target ε = {eps:g}")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("repetitions  (Trotter steps  /  block-encoding calls)")
    ax.set_ylabel(r"error  $\|U - e^{-iHt}\|$")
    ax.set_title(f"Error vs repetitions   (n = {n}, t = {t:g}, α = {H.alpha:.2f})", loc="left")
    ax.grid(True, which="major", color="#e6e5e0", lw=0.6)
    ax.legend(frameon=False)
    return results


if __name__ == "__main__":
    # with open("hamsim_results.json") as f:
    #     results = json.load(f)
    # print("writing figures:")
    # fig_accuracy(results)
    # fig_repetitions(results)
    # fig_vs_slide(results)
    # fig_optimization(results)
    # fig_cheaper_map(results)
    # fig_equal_accuracy(results)

    plot_error_vs_repetitions(n=2, t=1.0, eps=1e-3)
    plt.tight_layout()
    plt.savefig("error_vs_repetitions.png", dpi=200)