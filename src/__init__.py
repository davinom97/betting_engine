import logging
import os

# Define package version
__version__ = "1.0.0"

# Configure default logging to avoid "No handler found" warnings
# In a real app, main.py usually overrides this with a proper config
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Create a shared logger for the package
logger = logging.getLogger("betting_engine")