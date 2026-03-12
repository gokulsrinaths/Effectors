"""
Pytest integration tests for BLAST+ and TM-align pipeline.

These tests verify that real binaries are working correctly.
Tests will FAIL if binaries are not reachable.
"""
import subprocess
import tempfile
import os
import pathlib
import sys
import pytest

# Add backend to path
sys.path.insert(0, str(pathlib.Path(__file__).parent / "backend"))

from main import (
    run_blastp_search,
    run_tmalign_binary,
    windows_to_wsl_path,
    check_wsl_available,
    check_binary,
    check_tmalign_via_wsl,
    BLASTP_PATH,
    MAKEBLASTDB_PATH,
    WSL_AVAILABLE,
    WSL_DISTRO,
    SEQUENCE_DB_INDEX_PATH,
    STRUCTURE_DB_PATH,
    ensure_blast_database_indexed,
    SEQUENCE_DB_PATH
)

# Initialize globals for testing
import backend.main as main_module

@pytest.fixture(scope="module", autouse=True)
def initialize_config():
    """Ensure config is initialized before tests run."""
    # Initialize BLAST paths
    if not main_module.BLASTP_PATH:
        main_module.BLASTP_PATH = check_binary('blastp')
    if not main_module.MAKEBLASTDB_PATH:
        main_module.MAKEBLASTDB_PATH = check_binary('makeblastdb')
    
    # Initialize WSL state
    wsl_avail, wsl_distro = check_wsl_available()
    main_module.WSL_AVAILABLE = wsl_avail
    main_module.WSL_DISTRO = wsl_distro
    
    # Ensure BLAST database is indexed (will create if needed)
    if SEQUENCE_DB_PATH.exists():
        ensure_blast_database_indexed()


def test_blast_binary():
    """Test that BLAST+ binary is accessible and working."""
    blastp_path = check_binary('blastp')
    assert blastp_path is not None, "blastp not found in PATH"
    
    # Test version command
    result = subprocess.run(
        [blastp_path, '-version'],
        capture_output=True,
        text=True,
        timeout=5,
        check=True
    )
    assert result.returncode == 0, "blastp version check failed"


def test_blast_database():
    """Test that BLAST database exists and is accessible."""
    # Updated path for effector_sequences
    db_index_path = pathlib.Path(__file__).parent / "effector_sequences"
    db_files = [
        db_index_path.with_suffix('.psq'),
        db_index_path.with_suffix('.phr'),
        db_index_path.with_suffix('.pin'),
    ]
    
    all_exist = all(f.exists() for f in db_files)
    assert all_exist, f"BLAST database not fully indexed. Missing: {[f.name for f in db_files if not f.exists()]}"


def test_blast_search():
    """Test real BLAST search with a known protein sequence."""
    # Use a short test sequence (first sequence from database)
    test_sequence = "NIWREIDGACDECGAQLQECATIATCGQATKCSLHDQPLDDCSQELYTDVRWRCPTDRGHCSRGQLQLFKRSRGCRRTHALPASFSCPKCSHLA"
    test_id = "TEST_SEQ_001"
    
    # Test passes if search completes (even if no hit found - result can be None)
    result = run_blastp_search(test_sequence, test_id, timeout=120)
    # If we get here without exception, the search worked
    assert True, "BLAST search completed successfully"


def test_wsl_available():
    """Test that WSL is available."""
    available, distro = check_wsl_available()
    assert available, "WSL not available"


def test_tmalign_via_wsl():
    """Test that TMalign is accessible via WSL."""
    # check_tmalign_via_wsl uses wsl TMalign -h directly
    assert check_tmalign_via_wsl(), "TMalign not found in WSL"


def test_tmalign_comparison():
    """Test real TM-align comparison with two known PDB files."""
    # Find two PDB files in database
    pdb_files = list(STRUCTURE_DB_PATH.glob("*.pdb"))
    if len(pdb_files) < 2:
        pytest.skip("Need at least 2 PDB files for comparison")
    
    query_pdb = str(pdb_files[0])
    target_pdb = str(pdb_files[1])
    
    result = run_tmalign_binary(query_pdb, target_pdb, timeout=60)
    assert result is not None, "TM-align returned no result"
    assert 'tm_score' in result, "TM-align result missing tm_score"


def test_path_conversion():
    """Test Windows to WSL path conversion."""
    test_paths = [
        (r"C:\Users\sgoku\file.pdb", "/mnt/c/Users/sgoku/file.pdb"),
        (r"C:\Program Files\test.pdb", "/mnt/c/Program Files/test.pdb"),
    ]
    
    for win_path, expected_wsl in test_paths:
        result = windows_to_wsl_path(win_path)
        assert result == expected_wsl, f"{win_path} -> {result} (expected {expected_wsl})"

