# jupyterpilot_extension.py — compatibility shim
# This file exists so users can still do:
#   %load_ext jupyterpilot_extension
# All logic lives in the jupyterpilot package.
from jupyterpilot.extension import load_ipython_extension  # noqa: F401
