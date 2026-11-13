# Lets pytest find the research tools and the shared "client" package when run from the repository.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
