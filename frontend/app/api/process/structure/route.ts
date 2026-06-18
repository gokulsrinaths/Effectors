import { NextResponse } from 'next/server'
import { mockStructureResult } from '../../_mock/mock'

export const runtime = 'nodejs'

export async function POST(req: Request) {
  const form = await req.formData()
  const file = form.get('file')
  const filename = typeof (file as any)?.name === 'string' ? (file as any).name : 'uploaded_structure.pdb'
  return NextResponse.json(mockStructureResult(filename))
}

