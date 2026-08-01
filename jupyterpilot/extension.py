import sys
import traceback

from IPython.core.magic import Magics, line_magic, magics_class

from .provider import LLMProvider


@magics_class
class JupyterPilotMagics(Magics):
    def __init__(self, shell):
        super().__init__(shell)
        self.provider = LLMProvider()

    def _get_context(self):
        # Retrieve last 3 input cells
        history = self.shell.history_manager.input_hist_raw
        # Exclude current line and empty ones
        valid = [
            h.strip()
            for h in history
            if h.strip() and not h.startswith(("%do", "%fix"))
        ]
        return "\n# --- Previous Cell ---\n".join(valid[-3:])

    @line_magic
    def do(self, line):
        """%do <prompt> - Generate code from natural language."""
        if not line:
            return
        context = self._get_context()
        code = self.provider.generate(line, context)
        self.shell.set_next_input(code)

    @line_magic
    def fix(self, line):
        """%fix - Analyze and fix the last error."""
        if not hasattr(sys, "last_traceback"):
            print("No recent error found in sys.last_traceback.")
            return

        etype, evalue, tb = sys.last_type, sys.last_value, sys.last_traceback
        err_msg = "".join(traceback.format_exception(etype, evalue, tb))

        # Get the cell that caused the error
        last_cell = self.shell.history_manager.input_hist_raw[-1]
        context = self._get_context()

        prompt = f"The following code failed with an error. Please fix it.\n\nCode:\n{last_cell}\n\nError:\n{err_msg}"
        fixed_code = self.provider.generate(prompt, context)
        self.shell.set_next_input(fixed_code)


def load_ipython_extension(ipython):
    """Register the extension with IPython."""
    ipython.register_magics(JupyterPilotMagics(ipython))
