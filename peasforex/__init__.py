__version__ = "0.0.1"

try:
    from peasforex.overrides import apply_patches

    apply_patches()
except ImportError:
    # erpnext not importable yet (e.g. during install/build)
    pass
