"""Test script for new NSF Phase 1 API endpoints"""
import requests
import json
import os
import tempfile

API_BASE = "http://localhost:8000"

print("=" * 70)
print("NSF Phase 1 API - Endpoint Testing")
print("=" * 70)

# Test 1: Root endpoint
print("\n1. Testing root endpoint...")
try:
    response = requests.get(f"{API_BASE}/")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Phase: {data.get('phase')}")
    print(f"Structures: {data['structure_database']['structures_count']}")
    print(f"BLAST+ Available: {data['blastp']['available']}")
    print(f"TMalign Available: {data['tmalign']['available']}")
except Exception as e:
    print(f"Error: {e}")

# Test 2: Stats endpoint
print("\n2. Testing /stats endpoint...")
try:
    response = requests.get(f"{API_BASE}/stats")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"Error: {e}")

# Test 3: Structure upload
print("\n3. Testing /upload/structure endpoint...")
test_pdb = "Effector structure predicted/121205__ranked_0.pdb"
if os.path.exists(test_pdb):
    try:
        with open(test_pdb, 'rb') as f:
            files = {'file': ('121205__ranked_0.pdb', f, 'application/octet-stream')}
            response = requests.post(f"{API_BASE}/upload/structure", files=files, timeout=300)
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Status: {data.get('status')}")
                print(f"TM-score: {data.get('tm_score')}")
                print(f"Matched Structure: {data.get('matched_structure')}")
                print(f"Method: {data.get('method_used')}")
                if data.get('top_matches'):
                    print(f"Top matches: {len(data['top_matches'])}")
            else:
                print(f"Error: {response.text[:500]}")
    except Exception as e:
        print(f"Error: {e}")
else:
    print(f"Test file not found: {test_pdb}")

# Test 4: Sequence upload
print("\n4. Testing /upload/sequence endpoint...")
test_sequence = {
    "sequence": "NIWREIDGACDECGAQLQECATIATCGQATKCSLHDQPLDDCSQELYTDVRWRCPTDRGHCSRGQLQLFKRSRGCRRTHALPASFSCPKCSHLA",
    "sequence_id": "PSCE71d"
}
try:
    response = requests.post(
        f"{API_BASE}/upload/sequence",
        json=test_sequence,
        headers={"Content-Type": "application/json"},
        timeout=300
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Status: {data.get('status')}")
        print(f"Message: {data.get('message')}")
        print(f"TM-score: {data.get('tm_score')}")
        print(f"Matched Structure: {data.get('matched_structure')}")
        print(f"BLAST Hit ID: {data.get('blast_hit_id')}")
        print(f"Method: {data.get('method_used')}")
    else:
        print(f"Error: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

# Test 5: Multi-sequence upload
print("\n5. Testing /upload/multisequence endpoint...")
test_fasta = "effector_sequences.fasta"
if os.path.exists(test_fasta):
    try:
        # Read first few sequences only for testing
        sequences = []
        with open(test_fasta, 'r') as f:
            current_id = None
            current_seq = []
            for line in f:
                if line.startswith('>'):
                    if current_id and current_seq:
                        sequences.append(f">{current_id}\n{''.join(current_seq)}\n")
                    current_id = line[1:].strip().split()[0]
                    current_seq = []
                    if len(sequences) >= 3:  # Test with 3 sequences
                        break
                else:
                    current_seq.append(line.strip())
            if current_id and current_seq and len(sequences) < 3:
                sequences.append(f">{current_id}\n{''.join(current_seq)}\n")
        
        # Create temporary multi-FASTA
        multi_fasta_content = ''.join(sequences[:3])
        with tempfile.NamedTemporaryFile(mode='w', suffix='.fasta', delete=False) as tmp:
            tmp.write(multi_fasta_content)
            tmp_path = tmp.name
        
        try:
            with open(tmp_path, 'rb') as f:
                files = {'file': ('test.fasta', f, 'text/plain')}
                response = requests.post(f"{API_BASE}/upload/multisequence", files=files, timeout=600)
                print(f"Status: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"Total Sequences: {data.get('total_sequences')}")
                    print(f"Processed: {data.get('processed')}")
                    print(f"Results: {len(data.get('results', []))}")
                    for i, result in enumerate(data.get('results', [])[:3], 1):
                        print(f"  Sequence {i}: {result.get('status')}")
                else:
                    print(f"Error: {response.text[:500]}")
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        print(f"Error: {e}")
else:
    print(f"Test file not found: {test_fasta}")

print("\n" + "=" * 70)
print("Testing complete")
print("=" * 70)

