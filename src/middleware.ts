import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

// Browser calls same-origin /api/*, Next proxies to backend service inside compose.
const BACKEND = process.env.INTERNAL_API_URL || 'http://api:8000'

export function middleware(request: NextRequest) {
  const target = new URL(request.nextUrl.pathname + request.nextUrl.search, BACKEND)
  return NextResponse.rewrite(target)
}

export const config = {
  matcher: '/api/:path*',
}
