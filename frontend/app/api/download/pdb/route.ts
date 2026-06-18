import { NextResponse } from 'next/server'

export const runtime = 'nodejs'

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const structureId = searchParams.get('structure_id') || 'demo_structure'

  const pdb = [
    `HEADER    DEMO PDB FOR ${structureId}`,
    `TITLE     Mock PDB download (demo mode)`,
    `REMARK    Replace with real database-backed download in production.`,
    `ATOM      1  N   ALA A   1      11.104  13.207   9.447  1.00 20.00           N`,
    `ATOM      2  CA  ALA A   1      12.560  13.156   9.284  1.00 20.00           C`,
    `ATOM      3  C   ALA A   1      13.030  11.719   9.017  1.00 20.00           C`,
    `ATOM      4  O   ALA A   1      12.288  10.784   9.259  1.00 20.00           O`,
    `TER`,
    `END`,
    ``,
  ].join('\n')

  return new NextResponse(pdb, {
    headers: {
      'Content-Type': 'chemical/x-pdb; charset=utf-8',
      'Content-Disposition': `attachment; filename="${structureId}.pdb"`,
      'Cache-Control': 'no-store',
    },
  })
}

