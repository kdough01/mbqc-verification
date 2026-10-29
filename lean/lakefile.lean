import Lake
open Lake DSL

/-! The Lean side of mbqc-verification. Core Lean only (no Mathlib), so it builds
anywhere elan can fetch the toolchain. `grind` is used for ring identities. -/

package mbqc where
  leanOptions := #[⟨`autoImplicit, false⟩]

@[default_target]
lean_lib MBQC

/-- Reads J/CZ instruction streams on stdin and prints N E M per line (the differential check). -/
lean_exe mbqc_counts where
  root := `Main
