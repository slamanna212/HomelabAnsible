#!/usr/bin/env python3
"""
Test if Proxmox inventory plugin requirements are met
"""
import sys

print(f"Python version: {sys.version}")
print(f"Python executable: {sys.executable}")
print()

# Test for required modules
required_modules = ['requests', 'proxmoxer']

print("Testing required Python modules:")
for module in required_modules:
    try:
        __import__(module)
        print(f"  ✓ {module} - INSTALLED")
    except ImportError as e:
        print(f"  ✗ {module} - MISSING")
        print(f"    Error: {e}")

print()

# Try to import the Proxmox inventory plugin
print("Testing Proxmox inventory plugin import:")
try:
    # This is how Ansible tries to load the plugin
    import ansible.plugins.inventory
    print(f"  ✓ Ansible inventory plugins available")
except ImportError as e:
    print(f"  ✗ Failed to import ansible.plugins.inventory: {e}")

print()
print("To install missing modules, run:")
print("  sudo apt install -y python3-requests python3-proxmoxer")
print("Or:")
print("  pip3 install requests proxmoxer")
