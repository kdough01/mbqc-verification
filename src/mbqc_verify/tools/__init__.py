"""Adapters for the pinned external tools the tool/* tests call (versions pinned in tools/requirements.txt).

    surface_code   Stim + PyMatching + sinter: rotated surface-code memory experiments and threshold fits
    gridsynth      Ross–Selinger single-qubit synthesis (pygridsynth)
    qualtran_cost  Qualtran's gate and qubit costs for a bloq
    azure_re       the Azure Quantum Resource Estimator, run locally through qdk

Heavy imports happen inside the functions, so importing an adapter is cheap.
"""
