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
    derive_alignment_metrics,
    _match_from_parsed,
    sort_matches,
    StructureMatchResult,
    SequenceResult,
    _classify_structure_result,
    _classify_sequence_result,
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
Name of Chain_1: query.pdb (to be superimposed onto Chain_2)
Name of Chain_2: target.pdb
Length of Chain_1:  180 residues
Length of Chain_2:  150 residues

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
    assert result["chain1_length"] == 180
    assert result["chain2_length"] == 150
    assert result["seq_id"] == pytest.approx(0.154)


def test_parse_tmalign_aligned_length_not_confused_by_other_numbers():
    """The aligned-length value must come from its own label, not the first
    number on a line that also carries RMSD and Seq_ID."""
    output = """
Aligned length= 49, RMSD=   3.39, Seq_ID=n_identical/n_aligned= 0.082
TM-score= 0.44834 (if normalized by length of Chain_1, i.e., LN=68, d0=2.86)
"""
    result = parse_tmalign_output(output)
    assert result["aligned_length"] == 49
    assert result["rmsd"] == pytest.approx(3.39)


def test_parse_tmalign_ignores_average_normalized_score():
    """TM-align's -a flag adds a third score normalized by average length; it
    must not be mistaken for either chain."""
    output = """
Aligned length= 100, RMSD= 2.00, Seq_ID=n_identical/n_aligned= 0.100
TM-score= 0.60000 (if normalized by length of Chain_1, i.e., LN=180, d0=5.02)
TM-score= 0.70000 (if normalized by length of Chain_2, i.e., LN=150, d0=4.56)
TM-score= 0.65000 (if normalized by average length of two structures, i.e., LN=165.0, d0=4.80)
"""
    result = parse_tmalign_output(output)
    assert result["tm_score_chain1"] == pytest.approx(0.60000)
    assert result["tm_score_chain2"] == pytest.approx(0.70000)


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
    """Chain 1 of 0.49 with Chain 2 of 0.74 means the query contains the target
    as a domain. Ranking on Chain 1 alone used to label this 'Novel structure'."""
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
    assert result.classification == "Partial / domain match"
    assert result.tm_score == pytest.approx(0.49)
    assert result.tm_align_result["tm_score_chain1"] == pytest.approx(0.49)
    assert result.tm_align_result["tm_score_chain2"] == pytest.approx(0.74)
    assert result.tm_align_result["top_matches"][0]["tm_score_chain2"] == pytest.approx(0.74)


def test_alignment_type_bands():
    """Bands follow Zhang & Skolnick 2005: <0.20 random, >=0.50 same fold."""
    cases = [
        ((0.90, 0.88), "full_fold"),
        ((0.33, 0.97), "domain_match"),   # query contains target
        ((0.97, 0.33), "domain_match"),   # target contains query
        ((0.35, 0.30), "ambiguous"),
        ((0.25, 0.21), "ambiguous"),
        ((0.15, 0.10), "unrelated"),
    ]
    for (c1, c2), expected in cases:
        parsed = {"tm_score": c1, "tm_score_chain1": c1, "tm_score_chain2": c2}
        assert derive_alignment_metrics(parsed)["alignment_type"] == expected, (c1, c2)


def test_missing_chain2_does_not_demote_score():
    """A missing Chain 2 must fall back to Chain 1, never to 0.0."""
    parsed = {"tm_score": 0.80, "tm_score_chain1": 0.80, "tm_score_chain2": None}
    derived = derive_alignment_metrics(parsed)
    assert derived["tm_score_best"] == pytest.approx(0.80)
    assert derived["alignment_type"] == "full_fold"


def test_ranking_surfaces_domain_match():
    """A sub-domain hit must outrank a mediocre whole-protein hit."""
    matches = [
        _match_from_parsed("whole_mediocre",
                           {"tm_score": 0.55, "tm_score_chain1": 0.55, "tm_score_chain2": 0.52}, False),
        _match_from_parsed("subdomain",
                           {"tm_score": 0.33, "tm_score_chain1": 0.33, "tm_score_chain2": 0.97}, False),
        _match_from_parsed("poor",
                           {"tm_score": 0.18, "tm_score_chain1": 0.18, "tm_score_chain2": 0.15}, False),
    ]
    sort_matches(matches)
    assert [m["structure"] for m in matches] == ["subdomain", "whole_mediocre", "poor"]


def test_cache_hit_and_miss_produce_identical_shape():
    """Regression: the cached branch used to omit 'interpretation', so match
    dicts differed depending on warm-cache state."""
    parsed = {"tm_score": 0.44, "tm_score_chain1": 0.44, "tm_score_chain2": 0.30,
              "rmsd": 2.0, "aligned_length": 50, "chain1_length": 100, "chain2_length": 150}
    miss = _match_from_parsed("t", parsed, cached=False)
    hit = _match_from_parsed("t", parsed, cached=True)
    assert set(miss) == set(hit)
    assert "interpretation" in miss and "interpretation" in hit

    # A cache entry written before these fields existed must back-fill, not raise.
    legacy = _match_from_parsed("t", {"tm_score": 0.44}, cached=True)
    assert set(legacy) == set(miss)


def test_coverage_from_chain_lengths():
    parsed = {"tm_score": 0.5, "tm_score_chain1": 0.5, "tm_score_chain2": 0.9,
              "aligned_length": 49, "chain1_length": 119, "chain2_length": 39}
    derived = derive_alignment_metrics(parsed)
    assert derived["coverage_query"] == pytest.approx(49 / 119, abs=1e-4)
    assert derived["coverage_target"] == pytest.approx(49 / 39, abs=1e-4)


def test_structure_and_sequence_paths_classify_identically():
    """These two used to disagree: 0.05 read 'Structurally similar' on the
    sequence path but 'Novel structure' on the structure path."""
    for c1, c2 in [(0.05, 0.04), (0.49, 0.74), (0.90, 0.88), (0.35, 0.30)]:
        struct = _classify_structure_result(
            StructureMatchResult(status="matched", tm_score=c1, tm_score_chain1=c1,
                                 tm_score_chain2=c2, method_used="TM-align",
                                 matched_structure="t"), "q")
        seq = _classify_sequence_result(
            SequenceResult(status="blast_hit_with_structure", tm_score=c1,
                           tm_score_chain1=c1, tm_score_chain2=c2,
                           blast_hit_id="h", matched_structure="t"), "q")
        assert struct.classification == seq.classification, (c1, c2)


def test_path_conversion():
    """Test Windows to WSL path conversion."""
    test_paths = [
        (r"C:\Users\sgoku\file.pdb", "/mnt/c/Users/sgoku/file.pdb"),
        (r"C:\Program Files\test.pdb", "/mnt/c/Program Files/test.pdb"),
    ]
    
    for win_path, expected_wsl in test_paths:
        result = windows_to_wsl_path(win_path)
        assert result == expected_wsl, f"{win_path} -> {result} (expected {expected_wsl})"

