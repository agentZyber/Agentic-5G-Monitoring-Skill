import os
import sys

# Make the `zortenet` package importable (mirrors testing_netapp/conftest.py).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
