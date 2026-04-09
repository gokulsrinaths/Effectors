"""Test script for Effector Discovery Pipeline API"""
import requests
import json
import os

API_BASE = "http://localhost:8000"

print("=" * 60)
print("Testing Effector Discovery Pipeline API")
print("=" * 60)

# Test 1: Root endpoint
print("\n1. Testing root endpoint...")
try:
    response = requests.get(f"{API_BASE}/")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(json.dumps(data, indent=2))
except Exception as e:
    print(f"Error: {e}")

# Test 2: Structure upload (if TMalign available)
print("\n2. Testing structure upload...")
test_pdb = "Database/121205__ranked_0.pdb"
if os.path.exists(test_pdb):
    try:
        with open(test_pdb, 'rb') as f:
            files = {'file': ('121205__ranked_0.pdb', f, 'application/octet-stream')}
            response = requests.post(f"{API_BASE}/api/process/structure", files=files, timeout=300)
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"Job ID: {data.get('job_id')}")
                print(f"Status: {data.get('status')}")
                if data.get('results'):
                    result = data['results'][0]
                    print(f"Query ID: {result.get('query_id')}")
                    print(f"Best Match: {result.get('best_match_id')}")
                    print(f"TM-score: {result.get('tm_score')}")
                    print(f"Classification: {result.get('classification')}")
                if data.get('job_id'):
                    job_response = requests.get(f"{API_BASE}/api/job/{data['job_id']}", timeout=30)
                    print(f"Job Lookup Status: {job_response.status_code}")
            else:
                print(f"Error response: {response.text[:500]}")
    except Exception as e:
        print(f"Error: {e}")
else:
    print(f"Test file not found: {test_pdb}")

# Test 3: Sequence processing (if BLAST available)
print("\n3. Testing sequence processing...")
test_sequence = {
    "sequence": "NIWREIDGACDECGAQLQECATIATCGQATKCSLHDQPLDDCSQELYTDVRWRCPTDRGHCSRGQLQLFKRSRGCRRTHALPASFSCPKCSHLA",
    "sequence_id": "PSCE71d"
}
try:
    response = requests.post(
        f"{API_BASE}/api/process/sequence",
        json=test_sequence,
        timeout=300
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Job ID: {data.get('job_id')}")
        print(f"Status: {data.get('status')}")
        print(f"AlphaFold queued: {data.get('alphafold_queued')}")
        if data.get('results'):
            result = data['results'][0]
            print(f"Query ID: {result.get('query_id')}")
            print(f"Classification: {result.get('classification')}")
            if result.get('blast_result'):
                print(f"BLAST Hit: {result['blast_result'].get('hit_id')}")
            if result.get('tm_align_result'):
                print(f"TM-score: {result['tm_align_result'].get('tm_score')}")
    else:
        print(f"Error response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 60)
print("Testing complete")
print("=" * 60)

