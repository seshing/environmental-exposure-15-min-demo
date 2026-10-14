"""Compatibility entry: use latest 5090 reference inputs for a registered city."""
import argparse,subprocess,sys
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--cbsa',default='47900');parser.add_argument('--model-dir');parser.add_argument('--name');args=parser.parse_args()
command=[sys.executable,str(Path(__file__).with_name('recalculate_building_ranks.py')),'--cbsa',args.cbsa]
if args.model_dir:command+=['--model-dir',args.model_dir]
if args.name:command+=['--name',args.name]
subprocess.run(command,check=True)
