"""Seed helper re-export for sample-data/ script."""
from lab.seed import seed_data
if __name__ == "__main__":
    import sys
    seed_data(sys.argv[1] if len(sys.argv) > 1 else "/data/victim", count=int(sys.argv[2]) if len(sys.argv) > 2 else 300)
