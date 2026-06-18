import { NextResponse } from 'next/server'
import { mockSequenceResult } from '../../_mock/mock'

export const runtime = 'nodejs'

export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}))
  const sequence = typeof body?.sequence === 'string' ? body.sequence : ''
  const sequenceId = typeof body?.sequence_id === 'string' ? body.sequence_id : undefined

  if (!sequence.trim()) {
    return NextResponse.json({ detail: 'Sequence is required.' }, { status: 400 })
  }

  return NextResponse.json(mockSequenceResult(sequence, sequenceId))
}

