# Structure-based Effector Discovery Pipeline

Research-grade web application for structure-based effector discovery. This NSF-style cyberinfrastructure project enables identification and classification of protein effectors through sequence search (BLAST) and structure comparison (TM-align).

## Architecture

- **Frontend**: Next.js (React) with clean academic UI
- **Backend**: FastAPI (Python) REST API
- **Communication**: REST (JSON)

## Features

### Input Methods
1. **Upload Structure (PDB/CIF)**: Direct structure comparison using TM-align
2. **Paste Single Sequence**: BLAST search followed by structure comparison
3. **Upload FASTA File**: Batch processing of multiple sequences

### Processing Pipeline

#### Case A: Structure Upload (PDB/CIF)
- Runs TM-align against internal structure database
- Classifies results:
  - TM-score ≥ 0.9 → "Already in database"
  - 0.6 ≤ TM-score < 0.9 → "Known structural family"
  - TM-score < 0.5 → "Novel structure"

#### Case B: Sequence Upload (single or multi-FASTA)
1. **BLAST Search**: Searches against internal effector sequence database
2. **If BLAST hit found**: Retrieves structure and runs TM-align
3. **If no BLAST hit**: 
   - Checks for existing structure via external lookup
   - If not found: Queues AlphaFold/ColabFold prediction (toast notification)
   - Runs TM-align once structure is available

## Installation

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
```

### Frontend Setup

```bash
cd frontend
npm install
```

## Running the Application

### Start Backend Server

```bash
cd backend
python main.py
```

The API will be available at `http://localhost:8000`

### Start Frontend Development Server

```bash
cd frontend
npm run dev
```

The frontend will be available at `http://localhost:3000`

## API Endpoints

### `POST /api/process/structure`
Upload a PDB or CIF structure file for comparison.

**Request**: Multipart form data with `file` field

**Response**: `ProcessingResult` with classification results

### `POST /api/process/sequence`
Process a single protein sequence.

**Request**: JSON body with `sequence` and optional `sequence_id`

**Response**: `ProcessingResult` with classification results

### `POST /api/process/fasta`
Process a FASTA file with multiple sequences.

**Request**: Multipart form data with `file` field

**Response**: `ProcessingResult` with classification results for all sequences

### `GET /api/job/{job_id}`
Get status of a processing job.

## Notes

- **BLAST and TM-align**: The current implementation uses mock functions. In production, these would call actual BLAST and TM-align binaries installed on the backend system.
- **AlphaFold/ColabFold**: Not implemented. The system shows a toast notification when structure prediction is queued.
- **Database**: Uses mock data. In production, connect to actual structure and sequence databases.

## Development

### Backend Mock Functions

The backend includes mock implementations for:
- `mock_blast_search()`: Simulates BLAST search
- `mock_tmalign()`: Simulates TM-align comparison
- `mock_structure_lookup()`: Simulates external structure database lookup

Replace these with actual binary calls in production.

### Frontend Configuration

Set the API URL in `frontend/app/page.tsx` or via environment variable:
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Project Structure

```
.
├── backend/
│   ├── main.py              # FastAPI application
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── app/
│   │   ├── page.tsx         # Main application page
│   │   ├── page.module.css  # Component styles
│   │   ├── layout.tsx       # Root layout
│   │   └── globals.css      # Global styles
│   ├── package.json         # Node dependencies
│   └── tsconfig.json        # TypeScript configuration
└── README.md
```

## License

Research infrastructure project for academic use.

