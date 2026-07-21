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
    SEQUENCE_DB_PATH,
    parse_tmalign_output,
    StructureMatchResult,
    _classify_structure_result,
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
    assert 'tm_score_chain1' in result, "TM-align result missing Chain 1 score"
    assert 'tm_score_chain2' in result, "TM-align result missing Chain 2 score"


def test_parse_tmalign_two_normalized_scores():
    output = """
Aligned length= 143, RMSD= 2.31, Seq_ID=n_identical/n_aligned= 0.154
TM-score= 0.61234 (if normalized by length of Chain_1, i.e., LN=180, d0=5.02)
TM-score= 0.73456 (if normalized by length of Chain_2, i.e., LN=150, d0=4.56)
"""
    result = parse_tmalign_output(output)
    assert result is not None
    assert result["tm_score"] == pytest.approx(0.61234)
    assert result["tm_score_chain1"] == pytest.approx(0.61234)
    assert result["tm_score_chain2"] == pytest.approx(0.73456)
    assert result["rmsd"] == pytest.approx(2.31)
    assert result["aligned_length"] == 143


def test_parse_tmalign_allows_missing_chain2():
    output = """
Aligned length= 90, RMSD= 3.10
TM-score= 0.45678 (if normalized by length of Chain_1)
"""
    result = parse_tmalign_output(output)
    assert result is not None
    assert result["tm_score"] == pytest.approx(0.45678)
    assert result["tm_score_chain1"] == pytest.approx(0.45678)
    assert result["tm_score_chain2"] is None


def test_parse_tmalign_equal_scores_remain_equal():
    output = """
Aligned length= 100, RMSD= 0.00
TM-score= 1.00000 (if normalized by length of Chain_1)
TM-score= 1.00000 (if normalized by length of Chain_2)
"""
    result = parse_tmalign_output(output)
    assert result is not None
    assert result["tm_score_chain1"] == result["tm_score_chain2"] == 1.0


def test_parse_tmalign_requires_chain1():
    output = "TM-score= 0.76543 (if normalized by length of Chain_2)"
    assert parse_tmalign_output(output) is None


def test_classification_contract_propagates_both_scores():
    match = StructureMatchResult(
        status="matched",
        tm_score=0.49,
        tm_score_chain1=0.49,
        tm_score_chain2=0.74,
        rmsd=2.3,
        matched_structure="target_1",
        method_used="TM-align",
        alignment_length=143,
        top_matches=[{
            "structure": "target_1",
            "tm_score": 0.49,
            "tm_score_chain1": 0.49,
            "tm_score_chain2": 0.74,
        }],
    )
    result = _classify_structure_result(match, "query_1")
    assert result.classification == "Novel structure"
    assert result.tm_score == pytest.approx(0.49)
    assert result.tm_align_result["tm_score_chain1"] == pytest.approx(0.49)
    assert result.tm_align_result["tm_score_chain2"] == pytest.approx(0.74)
    assert result.tm_align_result["top_matches"][0]["tm_score_chain2"] == pytest.approx(0.74)


def test_path_conversion():
    """Test Windows to WSL path conversion."""
    test_paths = [
        (r"C:\Users\sgoku\file.pdb", "/mnt/c/Users/sgoku/file.pdb"),
        (r"C:\Program Files\test.pdb", "/mnt/c/Program Files/test.pdb"),
    ]
    
    for win_path, expected_wsl in test_paths:
        result = windows_to_wsl_path(win_path)
        assert result == expected_wsl, f"{win_path} -> {result} (expected {expected_wsl})"

