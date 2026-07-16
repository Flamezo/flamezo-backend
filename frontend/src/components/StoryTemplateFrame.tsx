import { useEffect, useRef, useState } from 'react'
import QRCode from 'qrcode'

const WA_CHANNEL_URL = 'https://whatsapp.com/channel/0029VbDInYjE50Up33JZob10'

const qrPromise = QRCode.toDataURL(WA_CHANNEL_URL, {
  width: 220,
  margin: 1,
  color: { dark: '#1a1a1a', light: '#ffffff' },
  errorCorrectionLevel: 'M',
})

export interface StoryTemplateFrameProps {
  mediaUrl: string
  mediaType?: 'image' | 'video'
  width?: number
  className?: string
  // Offer / coupon data
  couponCode?: string
  discountType?: 'flat' | 'percent' | 'percentage' | string
  discountValue?: number
  offerDescription?: string
  validUntil?: string   // ISO date string e.g. "2025-06-11"
  // Restaurant identity
  restaurantName?: string
}

export default function StoryTemplateFrame({
  mediaUrl,
  mediaType = 'image',
  width = 300,
  className = '',
  couponCode,
  discountType,
  discountValue,
  offerDescription,
  validUntil,
  restaurantName,
}: StoryTemplateFrameProps) {
  const height = Math.round((width / 9) * 16)
  const [qrDataUrl, setQrDataUrl] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)
  const [dims, setDims] = useState({ w: width, h: Math.round((width / 9) * 16) })

  useEffect(() => {
    qrPromise.then(setQrDataUrl).catch(() => {})
  }, [])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(entries => {
      const e = entries[0]
      if (e) setDims({ w: Math.round(e.contentRect.width), h: Math.round(e.contentRect.height) })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const pad = Math.round(dims.w * 0.038)
  const qrSize = Math.round(dims.w * 0.22)   // larger now that logo is gone
  const qrPad = Math.max(2, Math.round(dims.w * 0.008))


  // Typography scale
  const fs = (ratio: number) => Math.max(7, Math.round(dims.w * ratio))

  // Discount display — always produce a headline so the strip is never empty
  const isPercent = discountType === 'percent' || discountType === 'percentage'
  const discountLine = discountValue
    ? isPercent
      ? `${discountValue}% OFF`
      : `₹${discountValue} OFF`
    : couponCode
      ? 'Exclusive Offer'
      : null

  const hasOffer = !!(couponCode || discountLine)

  // Validity label: "Valid till 11 Jun"
  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  const validityLabel = validUntil
    ? (() => { const d = new Date(validUntil); return `Valid till ${d.getDate()} ${MONTHS[d.getMonth()]}` })()
    : null

  return (
    <div
      ref={containerRef}
      className={`relative overflow-hidden ${className}`}
      style={{ width, height }}
    >
      {/* Full-bleed media — fallback gradient when no URL */}
      {!mediaUrl ? (
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(160deg,#0f1520 0%,#1a2d4a 50%,#0a1020 100%)' }} />
      ) : mediaType === 'video' ? (
        <video
          src={mediaUrl}
          autoPlay muted loop playsInline
          className="absolute inset-0 w-full h-full object-cover"
        />
      ) : (
        <img
          src={mediaUrl}
          alt=""
          className="absolute inset-0 w-full h-full object-cover"
          draggable={false}
        />
      )}

      {/* Strong bottom vignette — ensures strip area is always readable on any BG */}
      <div
        style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          background: 'linear-gradient(to bottom, rgba(0,0,0,0) 25%, rgba(0,0,0,0.25) 50%, rgba(0,0,0,0.65) 75%, rgba(0,0,0,0.88) 100%)',
        }}
      />

      {/* ── Top-left: QR + CTA ── */}
      <div
        style={{
          position: 'absolute', top: pad, left: pad,
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          gap: Math.round(dims.w * 0.018),
        }}
      >
        {qrDataUrl ? (
          <div
            style={{
              width: qrSize, height: qrSize,
              background: '#fff',
              borderRadius: Math.round(dims.w * 0.018),
              padding: qrPad,
              boxShadow: '0 2px 8px rgba(0,0,0,0.45)',
              flexShrink: 0,
            }}
          >
            <img
              src={qrDataUrl}
              alt="Scan to join"
              draggable={false}
              style={{ width: '100%', height: '100%', display: 'block', objectFit: 'contain' }}
            />
          </div>
        ) : (
          <div style={{ width: qrSize, height: qrSize, background: 'rgba(255,255,255,0.15)', borderRadius: 4 }} />
        )}
        <p
          style={{
            color: 'rgba(255,255,255,0.7)', fontSize: fs(0.024), fontWeight: 500,
            textAlign: 'center', lineHeight: 1.25,
            textShadow: '0 1px 3px rgba(0,0,0,0.8)',
            letterSpacing: '0.01em', margin: 0,
          }}
        >
          Scan to join
        </p>
      </div>

      {/* ── Center-lower: compact coupon strip ── */}
      {hasOffer && (
        <div
          style={{
            position: 'absolute',
            bottom: Math.round(dims.h * 0.22),
            left: '50%',
            transform: 'translateX(-50%)',
            width: Math.round(dims.w * 0.82),
            background: 'rgba(10,10,12,0.55)',
            backdropFilter: 'blur(24px) saturate(1.6)',
            WebkitBackdropFilter: 'blur(24px) saturate(1.6)',
            borderRadius: Math.round(dims.w * 0.035),
            border: '0.5px solid rgba(255,255,255,0.14)',
            padding: `${Math.round(dims.w * 0.024)}px ${Math.round(dims.w * 0.032)}px`,
            display: 'flex',
            flexDirection: 'column',
            gap: Math.round(dims.w * 0.010),
            overflow: 'hidden',
          }}
        >
          {/* Row 1: restaurant name (left) + coupon code chip (right) */}
          <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: Math.round(dims.w * 0.02) }}>
            {restaurantName && (
              <p style={{
                color: 'rgba(255,255,255,0.45)', fontSize: fs(0.021),
                margin: 0, fontWeight: 600, letterSpacing: '0.055em',
                textTransform: 'uppercase',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                flex: 1, minWidth: 0,
              }}>
                {restaurantName}
              </p>
            )}
            {couponCode && (
              <div style={{
                border: '1px dashed rgba(183,65,14,0.85)',
                borderRadius: Math.round(dims.w * 0.014),
                padding: `${Math.round(dims.w * 0.006)}px ${Math.round(dims.w * 0.014)}px`,
                background: 'rgba(183,65,14,0.20)',
                flexShrink: 0,
                maxWidth: Math.round(dims.w * 0.44),
                overflow: 'hidden',
              }}>
                <span style={{
                  color: '#fff', fontSize: fs(0.024), fontWeight: 800,
                  letterSpacing: '0.04em', fontFamily: 'ui-monospace, monospace',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  display: 'block',
                }}>
                  {couponCode}
                </span>
              </div>
            )}
          </div>

          {/* Row 2: discount headline — full width */}
          {discountLine && (
            <p style={{
              color: '#fff',
              fontSize: discountValue ? fs(0.058) : fs(0.038),
              fontWeight: 800, lineHeight: 1, margin: 0,
              letterSpacing: discountValue ? '-0.01em' : '0.01em',
              whiteSpace: 'nowrap',
            }}>
              {discountLine}
            </p>
          )}

          {/* Row 3: description — full width, up to 2 lines */}
          <p style={{
            color: 'rgba(255,255,255,0.55)', fontSize: fs(0.026),
            margin: 0, lineHeight: 1.3, fontWeight: 400,
            display: '-webkit-box', WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical', overflow: 'hidden',
          }}>
            {offerDescription || 'on dine-in'}
          </p>

          {/* Row 4: validity + T&C — always shown */}
          <p style={{
            fontSize: fs(0.023),
            margin: 0, fontWeight: 700,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            <span style={{ color: 'rgba(183,65,14,1)' }}>
              {validityLabel ? `${validityLabel} · T&C apply · ` : 'T&C apply · '}
            </span>
            <span style={{ color: '#E23744' }}>Secured by Flamezo</span>
          </p>

          {/* Row 5: CTA (wraps if needed) */}
          <p style={{
            color: 'rgba(255,255,255,0.3)', fontSize: fs(0.019),
            margin: 0, lineHeight: 1.3,
          }}>
            Show at checkout · Take a screenshot now
          </p>
        </div>
      )}
    </div>
  )
}
