"""Offline library entry point; deployed in Aplicacion beside python_companion."""
from pathlib import Path
import os
import runpy
import sys
import traceback
from datetime import datetime, timezone


def main():
    root = Path(__file__).resolve().parent.parent
    os.environ["CAVITY_LIGHT_PACKAGE_ROOT"] = str(root)
    os.environ["TCL_LIBRARY"] = str(root / "Python/tcl/tcl8.6")
    os.environ["TK_LIBRARY"] = str(root / "Python/tcl/tk8.6")
    sys.path.insert(0, str(root / "Aplicacion/python_companion"))
    mutex = None
    if os.name == "nt" and "--editor" not in sys.argv:
        # One library writer per Windows session prevents two frontends from
        # replacing each other's cached locations/references.
        import ctypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        mutex = kernel.CreateMutexW(None, False, "Local\\CavityTEMLightLibrary12")
        if not mutex:
            raise OSError(ctypes.get_last_error(), "No se pudo reservar el catálogo local")
        if ctypes.get_last_error() == 183:
            from tkinter import Tk, messagebox
            window = Tk(); window.withdraw()
            messagebox.showinfo("Cavity TEM Light", "La biblioteca ya está abierta. Continúa en su ventana.", parent=window)
            window.destroy()
            return 0
    (root / "Registro").mkdir(exist_ok=True)
    log = root / "Registro" / ("biblioteca_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".log")
    with log.open("a", encoding="utf-8") as output:
        sys.stdout = sys.stderr = output
        try:
            if "--editor" in sys.argv:
                from cavity_library.launch import launch_editor
                launch_editor()
            else:
                sys.argv = ["cavity_library"]
                runpy.run_module("cavity_library", run_name="__main__")
        except Exception as exc:
            traceback.print_exc()
            from tkinter import Tk, messagebox
            window = Tk()
            window.withdraw()
            messagebox.showerror("Cavity TEM Light · inicio", f"No se pudo iniciar: {exc}\n\nRegistro: {log}", parent=window)
            window.destroy()
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
