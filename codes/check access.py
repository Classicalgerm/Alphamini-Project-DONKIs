import pkgutil
import importlib
import mini
import mini.apis.api_sence as sence
import mini.apis.api_sence as sence
print(dir(sence))

print(dir(sence))

print("=== Checking Alpha Mini SDK modules ===")

# 1. List all submodules in 'mini.apis'
package = importlib.import_module("mini.apis")
print("\nSubmodules under mini.apis:")
for loader, name, is_pkg in pkgutil.iter_modules(package.__path__):
    print(" -", name)

# 2. Try to import anything camera-related
possible_names = [
    "mini.apis.api_camera",
    "mini.apis.api_sence",
    "mini.apis.api_vision",
    "mini.apis.api_media",
]

print("\n=== Trying possible camera-related modules ===")
for name in possible_names:
    try:
        mod = importlib.import_module(name)
        print(f"[✅ FOUND] {name}")
        print("Attributes:", dir(mod))
    except ModuleNotFoundError:
        print(f"[❌ NOT FOUND] {name}")
    except Exception as e:
        print(f"[⚠️ ERROR importing {name}]: {e}")

print("\n=== Check complete ===")

