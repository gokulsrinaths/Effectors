import { NextResponse } from 'next/server'
import { mockFastaResult } from '../../_mock/mock'

export const runtime = 'nodejs'

export async function POST(req: Request) {
  const form = await req.formData()
  const file = form.get('file')

  if (!(file instanceof File)) {
    return NextResponse.json({ detail: 'FASTA file is required.' }, { status: 400 })
  }

  const text = await file.text()
  if (!text.trim()) {
    return NextResponse.json({ detail: 'FASTA file is empty.' }, { status: 400 })
  }

  return NextResponse.json(mockFastaResult(text))
}

