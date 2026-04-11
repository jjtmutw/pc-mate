import os
import sys
import types


if os.environ.get("PYI_DISABLE_SPLASH_TK") == "1":
    stub = types.ModuleType("PyInstaller.building.splash")

    class Splash:  # pragma: no cover
        pass

    stub.Splash = Splash
    sys.modules["PyInstaller.building.splash"] = stub
