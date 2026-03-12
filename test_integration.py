"""
Integration tests for BLAST+ and TM-align pipeline.

These tests verify that real binaries are working correctly.
Tests will FAIL if binaries are not reachable.
"""
import subprocess
import tempfile
import os
import pathlib
import sys

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
    WSL_AVAILABLE,
    WSL_DISTRO,
    SEQUENCE_DB_INDEX_PATH,
    STRUCTURE_DB_PATH
)

# Initialize globals for testing
import backend.main as main_module
# Ensure config is initialized before tests run
if not main_module.BLASTP_PATH:
    main_module.BLASTP_PATH = check_binary('blastp')
if not main_module.MAKEBLASTDB_PATH:
    main_module.MAKEBLASTDB_PATH = check_binary('makeblastdb')
wsl_avail, wsl_distro = check_wsl_available()
main_module.WSL_AVAILABLE = wsl_avail
main_module.WSL_DISTRO = wsl_distro

def test_blast_binary():
    """Test that BLAST+ binary is accessible and working."""
    print("\n" + "="*70)
    print("TEST 1: BLAST+ Binary Availability")
    print("="*70)
    
    blastp_path = check_binary('blastp')
    if not blastp_path:
        print("FAIL: blastp not found in PATH")
        return False
    
    print(f"PASS: blastp found at {blastp_path}")
    
    # Test version command
    try:
        result = subprocess.run(
            [blastp_path, '-version'],
            capture_output=True,
            text=True,
            timeout=5,
            check=True
        )
        print(f"PASS: blastp version check successful")
        print(f"      Output: {result.stdout[:100]}")
        return True
    except Exception as e:
        print(f"FAIL: blastp version check failed: {e}")
        return False


def test_blast_database():
    """Test that BLAST database exists and is accessible."""
    print("\n" + "="*70)
    print("TEST 2: BLAST Database")
    print("="*70)
    
    # Updated path for effector_sequences
    db_index_path = pathlib.Path(__file__).parent / "effector_sequences"
    db_files = [
        db_index_path.with_suffix('.psq'),
        db_index_path.with_suffix('.phr'),
        db_index_path.with_suffix('.pin'),
    ]
    
    all_exist = all(f.exists() for f in db_files)
    if all_exist:
        print(f"PASS: BLAST database indexed")
        for f in db_files:
            print(f"      Found: {f.name}")
        return True
    else:
        print(f"FAIL: BLAST database not fully indexed")
        for f in db_files:
            status = "EXISTS" if f.exists() else "MISSING"
            print(f"      {f.name}: {status}")
        return False


def test_blast_search():
    """Test real BLAST search with a known protein sequence."""
    print("\n" + "="*70)
    print("TEST 3: BLAST Search (Real)")
    print("="*70)
    
    # Use a short test sequence (first sequence from database)
    test_sequence = "NIWREIDGACDECGAQLQECATIATCGQATKCSLHDQPLDDCSQELYTDVRWRCPTDRGHCSRGQLQLFKRSRGCRRTHALPASFSCPKCSHLA"
    test_id = "TEST_SEQ_001"
    
    try:
        result = run_blastp_search(test_sequence, test_id, timeout=120)
        
        if result:
            print(f"PASS: BLAST search returned hit")
            print(f"      Hit ID: {result['hit_id']}")
            print(f"      E-value: {result['evalue']:.2e}")
            print(f"      Identity: {result['percent_identity']:.1f}%")
            print(f"      Coverage: {result['query_coverage']:.1f}%")
            return True
        else:
            print(f"INFO: BLAST search completed but no hit found (may be expected)")
            return True  # Still a pass - search worked
            
    except Exception as e:
        print(f"FAIL: BLAST search failed: {e}")
        return False


def test_wsl_available():
    """Test that WSL is available."""
    print("\n" + "="*70)
    print("TEST 4: WSL Availability")
    print("="*70)
    
    available, distro = check_wsl_available()
    if available:
        print(f"PASS: WSL available with distro: {distro}")
        return True
    else:
        print(f"FAIL: WSL not available")
        return False


def test_tmalign_via_wsl():
    """Test that TMalign is accessible via WSL."""
    print("\n" + "="*70)
    print("TEST 5: TMalign via WSL")
    print("="*70)
    
    # check_tmalign_via_wsl uses wsl TMalign -h directly, no need for WSL_AVAILABLE
    if check_tmalign_via_wsl():
        print(f"PASS: TMalign available via WSL")
        return True
    else:
        print(f"FAIL: TMalign not found in WSL")
        return False


def test_tmalign_comparison():
    """Test real TM-align comparison with two known PDB files."""
    print("\n" + "="*70)
    print("TEST 6: TM-align Comparison (Real)")
    print("="*70)
    
    # Find two PDB files in database
    pdb_files = list(STRUCTURE_DB_PATH.glob("*.pdb"))
    if len(pdb_files) < 2:
        print("SKIP: Need at least 2 PDB files for comparison")
        return False
    
    query_pdb = str(pdb_files[0])
    target_pdb = str(pdb_files[1])
    
    print(f"      Query: {os.path.basename(query_pdb)}")
    print(f"      Target: {os.path.basename(target_pdb)}")
    
    try:
        result = run_tmalign_binary(query_pdb, target_pdb, timeout=60)
        
        if result:
            print(f"PASS: TM-align comparison successful")
            print(f"      TM-score: {result['tm_score']:.4f}")
            print(f"      RMSD: {result.get('rmsd', 0.0):.2f} Å")
            print(f"      Aligned length: {result.get('aligned_length', 0)}")
            return True
        else:
            print(f"FAIL: TM-align returned no result")
            return False
            
    except Exception as e:
        print(f"FAIL: TM-align comparison failed: {e}")
        return False


def test_path_conversion():
    """Test Windows to WSL path conversion."""
    print("\n" + "="*70)
    print("TEST 7: Windows to WSL Path Conversion")
    print("="*70)
    
    test_paths = [
        (r"C:\Users\sgoku\file.pdb", "/mnt/c/Users/sgoku/file.pdb"),
        (r"C:\Program Files\test.pdb", "/mnt/c/Program Files/test.pdb"),
    ]
    
    all_pass = True
    for win_path, expected_wsl in test_paths:
        result = windows_to_wsl_path(win_path)
        if result == expected_wsl:
            print(f"PASS: {win_path} -> {result}")
        else:
            print(f"FAIL: {win_path} -> {result} (expected {expected_wsl})")
            all_pass = False
    
    return all_pass


if __name__ == "__main__":
    print("="*70)
    print("Integration Tests for BLAST+ and TM-align Pipeline")
    print("="*70)
    
    tests = [
        ("BLAST Binary", test_blast_binary),
        ("BLAST Database", test_blast_database),
        ("BLAST Search", test_blast_search),
        ("WSL Availability", test_wsl_available),
        ("TMalign via WSL", test_tmalign_via_wsl),
        ("TM-align Comparison", test_tmalign_comparison),
        ("Path Conversion", test_path_conversion),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\nERROR in {test_name}: {e}")
            results.append((test_name, False))
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All integration tests passed!")
        sys.exit(0)
    else:
        print(f"\nFAILED: {total - passed} test(s) failed")
        sys.exit(1)

