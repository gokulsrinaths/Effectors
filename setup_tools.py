"""Setup script to download and configure BLAST+ and TMalign"""
import os
import subprocess
import urllib.request
import tarfile
import zipfile
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).parent
BIN_DIR = BASE_DIR / "bin"
BIN_DIR.mkdir(exist_ok=True)

def download_file(url, dest_path):
    """Download a file from URL"""
    try:
        print(f"Downloading {url}...")
        urllib.request.urlretrieve(url, dest_path)
        print(f"Downloaded to {dest_path}")
        return True
    except Exception as e:
        print(f"Download failed: {e}")
        return False

def extract_tar_gz(archive_path, extract_to):
    """Extract tar.gz archive"""
    try:
        with tarfile.open(archive_path, 'r:gz') as tar:
            tar.extractall(extract_to)
        print(f"Extracted {archive_path}")
        return True
    except Exception as e:
        print(f"Extraction failed: {e}")
        return False

def extract_zip(archive_path, extract_to):
    """Extract zip archive"""
    try:
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        print(f"Extracted {archive_path}")
        return True
    except Exception as e:
        print(f"Extraction failed: {e}")
        return False

def find_executable(base_dir, exe_name):
    """Find executable in directory tree"""
    for root, dirs, files in os.walk(base_dir):
        if exe_name in files:
            return os.path.join(root, exe_name)
    return None

def setup_blast():
    """Setup BLAST+"""
    print("\n" + "="*60)
    print("Setting up BLAST+")
    print("="*60)
    
    # Check if already installed
    try:
        result = subprocess.run(['blastp', '-version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("✓ BLAST+ already installed in PATH")
            return True
    except:
        pass
    
    # Try downloading Windows version - check latest version first
    # Latest stable: 2.15.0+ (as of 2024)
    blast_url = "https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/2.15.0/ncbi-blast-2.15.0+-win64.tar.gz"
    blast_archive = BIN_DIR / "blast.tar.gz"
    
    if not blast_archive.exists():
        if not download_file(blast_url, blast_archive):
            print("WARNING: Could not download BLAST+. Please install manually:")
            print("  1. Download from: https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/")
            print("  2. Extract and add to PATH")
            return False
    
    # Extract
    extract_dir = BIN_DIR / "blast"
    if not extract_dir.exists():
        if extract_tar_gz(blast_archive, BIN_DIR):
            # Find the actual bin directory
            for item in BIN_DIR.iterdir():
                if item.is_dir() and 'blast' in item.name.lower():
                    blast_bin = item / "bin"
                    if blast_bin.exists():
                        print(f"✓ BLAST+ extracted to {blast_bin}")
                        return True
    
    print("⚠ BLAST+ setup incomplete. Please install manually.")
    return False

def setup_tmalign():
    """Setup TMalign"""
    print("\n" + "="*60)
    print("Setting up TMalign")
    print("="*60)
    
    # Check if already installed
    try:
        result = subprocess.run(['TMalign'], capture_output=True, text=True, timeout=5)
        if 'TM-align' in result.stdout or 'TM-align' in result.stderr or result.returncode == 0:
            print("✓ TMalign already installed in PATH")
            return True
    except:
        pass
    
    print("WARNING: TMalign needs to be installed manually:")
    print("  1. Download from: https://zhanggroup.org/TM-align/")
    print("  2. Extract and add TMalign.exe to PATH or bin/ directory")
    print("  3. Or compile from source")
    return False

def create_blast_database():
    """Create BLAST database from sequence file"""
    print("\n" + "="*60)
    print("Creating BLAST database")
    print("="*60)
    
    seq_file = BASE_DIR / "effector_sequences.fasta"
    db_name = BASE_DIR / "effector_sequences"
    
    if not seq_file.exists():
        print(f"ERROR: Sequence file not found: {seq_file}")
        return False
    
    # Check if database already exists
    if (Path(f"{db_name}.psq").exists() or 
        Path(f"{db_name}.phr").exists() or 
        Path(f"{db_name}.pin").exists()):
        print("✓ BLAST database already exists")
        return True
    
    # Find makeblastdb
    makeblastdb_path = None
    try:
        result = subprocess.run(['makeblastdb', '-version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            makeblastdb_path = 'makeblastdb'
    except:
        pass
    
    if not makeblastdb_path:
        # Try to find in bin directory
        for exe in ['makeblastdb.exe', 'makeblastdb']:
            test_path = BIN_DIR / exe
            if test_path.exists():
                makeblastdb_path = str(test_path)
                break
    
    if not makeblastdb_path:
        print("ERROR: makeblastdb not found. Please install BLAST+ first.")
        return False
    
    # Create database
    print(f"Creating BLAST database from {seq_file}...")
    cmd = [
        makeblastdb_path,
        '-in', str(seq_file),
        '-dbtype', 'prot',
        '-out', str(db_name),
        '-title', 'Effector Sequences'
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print("✓ BLAST database created successfully")
            return True
        else:
            print(f"ERROR: Database creation failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"ERROR: Error creating database: {e}")
        return False

if __name__ == "__main__":
    print("Effector Discovery Pipeline - Tool Setup")
    print("="*60)
    
    blast_ok = setup_blast()
    tmalign_ok = setup_tmalign()
    db_ok = create_blast_database()
    
    print("\n" + "="*60)
    print("Setup Summary")
    print("="*60)
    print(f"BLAST+: {'READY' if blast_ok else 'NEEDS SETUP'}")
    print(f"TMalign: {'READY' if tmalign_ok else 'NEEDS SETUP'}")
    print(f"BLAST Database: {'READY' if db_ok else 'NEEDS SETUP'}")
    print("\nIf tools are not ready, please install them manually:")
    print("- BLAST+: https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/")
    print("- TMalign: https://zhanggroup.org/TM-align/")

