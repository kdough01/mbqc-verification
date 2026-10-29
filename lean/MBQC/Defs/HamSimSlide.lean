/-!
# The slide's cost formulas (vocabulary for the Layer C claims)

"Hamiltonian simulation: explicit costs and trade-offs" (docs/img/hamsim_slide.png).
n data qubits, QSVT degree d, GQSP degree g. These are the formulas exactly as
the slide prints them; whether the slide's compiler produces them is a separate
claim (DAG nodes `hamsim.B.slide.*`).
-/

namespace MBQC.Defs.HamSim

def slideNQ (n d : Int) : Int := (36*n - 18)*d + 14*n + 23
def slideNG (n g : Int) : Int := (12*n - 6)*g + 32*n - 11
def slideEQ (n d : Int) : Int := (168*n - 102)*d + 45*n + 185
/-- χ = [g ≡ 1 (mod 4)] -/
def chi (g : Int) : Int := if g % 4 = 1 then 1 else 0
/-- η = [g = 3] -/
def eta (g : Int) : Int := if g = 3 then 1 else 0
def slideEG (n g : Int) : Int := (124*n - 116)*g + (122 - chi g)*n - 40 + 3*chi g - eta g
def slideMQ (n d : Int) : Int := slideNQ n d - n
def slideMG (n g : Int) : Int := slideNG n g - n

end MBQC.Defs.HamSim
