"""Verification script to check if all tools are properly installed"""
import os
import subprocess
import sys
from pathlib import Path

def check_binary(name, test_cmd=None):
    """Check if a binary is available"""
    # Check in PATH
    try:
        if test_cmd:
            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0 or name.lower() in result.stdout.lower() or name.lower() in result.stderr.lower():
                return True, "PATH"
        else:
            # Try to find it
            if os.name == 'nt':
                result = subprocess.run(['where', name], capture_output=True, text=True, timeout=5)
            else:
                result = subprocess.run(['which', name], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                return True, "PATH"
    except:
        pass
    
    # Check local bin
    local_bin = Path(__file__).parent / "bin" / name
    local_bin_exe = Path(__file__).parent / "bin" / f"{name}.exe"
    
    if local_bin.exists():
        return True, str(local_bin)
    if local_bin_exe.exists():
        return True, str(local_bin_exe)
    
    return False, None

def check_blast_db():
    """Check if BLAST database exists"""
    base_dir = Path(__file__).parent
    db_base = base_dir / "effector_sequences"
    
    required_files = [f"{db_base}.psq", f"{db_base}.phr", f"{db_base}.pin"]
    existing = [f for f in required_files if Path(f).exists()]
    
    return len(existing) > 0, existing

print("=" * 70)
print("Effector Discovery Pipeline - Installation Verification")
print("=" * 70)

# Check BLAST+
print("\n1. Checking BLAST+ installation...")
blast_ok, blast_loc = check_binary('blastp', ['blastp', '-version'])
makeblastdb_ok, makeblastdb_loc = check_binary('makeblastdb', ['makeblastdb', '-version'])

if blast_ok:
    print(f"   [OK] blastp found: {blast_loc}")
else:
    print("   [FAIL] blastp NOT FOUND")
    print("     Install from: https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/")

if makeblastdb_ok:
    print(f"   [OK] makeblastdb found: {makeblastdb_loc}")
else:
    print("   [FAIL] makeblastdb NOT FOUND")

# Check TMalign
print("\n2. Checking TMalign installation...")
tmalign_ok, tmalign_loc = check_binary('TMalign')

if tmalign_ok:
    print(f"   [OK] TMalign found: {tmalign_loc}")
else:
    print("   [FAIL] TMalign NOT FOUND")
    print("     Install from: https://zhanggroup.org/TM-align/")
    print("     Or copy TMalign.exe to bin/ directory")

# Check BLAST database
print("\n3. Checking BLAST database...")
db_ok, db_files = check_blast_db()

if db_ok:
    print(f"   [OK] BLAST database found ({len(db_files)} files)")
    for f in db_files:
        print(f"     - {Path(f).name}")
else:
    print("   [FAIL] BLAST database NOT FOUND")
    if makeblastdb_ok:
        print("     Run: makeblastdb -in 'effector_sequences.fasta' -dbtype prot -out 'effector_sequences'")
    else:
        print("     Install BLAST+ first, then create database")

# Check structure database
print("\n4. Checking structure database...")
struct_dir = Path(__file__).parent / "Effector structure predicted"
if struct_dir.exists():
    pdb_files = list(struct_dir.glob("*.pdb"))
    print(f"   [OK] Structure database found ({len(pdb_files)} PDB files)")
else:
    print("   [FAIL] Structure database NOT FOUND")

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

all_ok = blast_ok and makeblastdb_ok and tmalign_ok and db_ok

if all_ok:
    print("[SUCCESS] ALL SYSTEMS READY!")
    print("\nYou can now use the full pipeline with real BLAST and TM-align.")
else:
    print("[WARNING] SOME COMPONENTS MISSING")
    print("\nPlease install missing components:")
    if not blast_ok or not makeblastdb_ok:
        print("  - BLAST+: https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/")
    if not tmalign_ok:
        print("  - TMalign: https://zhanggroup.org/TM-align/")
    if not db_ok and makeblastdb_ok:
        print("  - Create BLAST database (see INSTALL.md)")

print("\n" + "=" * 70)

sys.exit(0 if all_ok else 1)

