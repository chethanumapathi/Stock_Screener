import glob
import os

files = glob.glob('strategies/*.py')
print(f"Total strategy py files: {len(files)}")
for fpath in files:
    with open(fpath, 'r', encoding='utf-8') as f:
        code = f.read()
    fname = os.path.basename(fpath)
    lines = code.splitlines()
    has_eod = False
    has_still_running = False
    has_timeout = False
    findings = []
    for idx, l in enumerate(lines):
        line = l.strip()
        if any(k in line for k in ['End of Data', 'Still Running', 'OPEN_TIMEOUT', 'open_timeout']):
            findings.append(f"L{idx+1}: {line}")
    print(f"\n{fname}:")
    for fnd in findings:
        print(f"  {fnd}")
