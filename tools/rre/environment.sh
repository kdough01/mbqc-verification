#!/usr/bin/env bash
# Build the pinned environment for experiments/rre and the Cabaliser compiler (experiments/compilers): Python 3.11, Rigetti Resource Estimation (RRE) at the commit
# the paper's code release points to, Cabaliser (C + Rust) built from RRE's submodule, pyLIQTR 1.3.3.
#
#   bash tools/rre/environment.sh [DIR]      # default DIR: .rre (git-ignored)
#   source DIR/venv/bin/activate && export RRE_COMMIT=$(git -C DIR/rre rev-parse --short HEAD)
#
# Needs: git, gcc/make, a CPU with AVX2 (Cabaliser's build flags), uv (https://docs.astral.sh/uv/) and Rust
# (cargo). Without system Rust, the script installs it from conda-forge with micromamba. Rust newer than 1.89
# rejects one pointer expression in Cabaliser's pauli_tracker crate by default (lint dangerous_implicit_autorefs);
# RUSTFLAGS=--cap-lints=warn keeps it a warning, as older compilers did.
set -euo pipefail
DIR="${1:-.rre}"
RRE_REV=9383b4d                                   # rigetti-resource-estimation, version 0.26.33
CABALISER_REV=10f5c4e700fba59adadf4197fa6fbf1aea1f8175
GSG_REV=3a4f151ca1de86fa6697d1e7ac15fc89f87c189f  # sfc-aqua/gosc-graph-state-generation
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$DIR"
DIR="$(cd "$DIR" && pwd)"

if [ ! -d "$DIR/rre/.git" ]; then
  git clone -q https://github.com/rigetti/rigetti-resource-estimation "$DIR/rre"
fi
git -C "$DIR/rre" checkout -q "$RRE_REV"
git -C "$DIR/rre" submodule update -q --init --recursive
git -C "$DIR/rre/external/cabaliser" checkout -q "$CABALISER_REV"

if ! command -v cargo >/dev/null; then
  if [ ! -x "$DIR/rust/bin/cargo" ]; then
    curl -sSL -o "$DIR/micromamba" https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-linux-64
    chmod +x "$DIR/micromamba"
    MAMBA_ROOT_PREFIX="$DIR/mamba" "$DIR/micromamba" create -y -q -p "$DIR/rust" -c conda-forge rust
  fi
  export PATH="$DIR/rust/bin:$PATH"
fi
export RUSTFLAGS="${RUSTFLAGS:---cap-lints=warn}"
make -s -C "$DIR/rre/external/cabaliser/c_lib/pauli_tracker" all
make -s -C "$DIR/rre/external/cabaliser/c_lib"

[ -x "$DIR/venv/bin/python" ] || uv venv -q -p 3.11 "$DIR/venv"
uv pip install -q -p "$DIR/venv/bin/python" -r "$HERE/requirements-rre.txt"
uv pip install -q -p "$DIR/venv/bin/python" "git+https://github.com/sfc-aqua/gosc-graph-state-generation@$GSG_REV"
uv pip install -q -p "$DIR/venv/bin/python" --no-deps -e "$DIR/rre/external/cabaliser" -e "$DIR/rre"

# RRE's own verification tests (Appendix C protocol, QFT4 graph sizes) as a smoke test of the build
(cd "$DIR/rre" && "$DIR/venv/bin/python" -m pytest -q -p no:cacheprovider tests/verify_n_validate)
echo "RRE environment ready: source $DIR/venv/bin/activate; export RRE_COMMIT=$RRE_REV"
