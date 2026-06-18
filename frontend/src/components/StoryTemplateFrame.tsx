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
  discountType?: 'flat' | 'percentage' | string
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
  const logoW = Math.round(dims.w * 0.28)
  const qrSize = Math.round(dims.w * 0.17)   // smaller — don't compete with logo
  const qrPad = Math.max(2, Math.round(dims.w * 0.008))
  const chipBr = Math.round(dims.w * 0.04)
  const chipPy = Math.round(dims.w * 0.014)
  const chipPx = Math.round(dims.w * 0.020)


  // Typography scale
  const fs = (ratio: number) => Math.max(7, Math.round(dims.w * ratio))

  // Discount display
  const discountLine = discountValue
    ? discountType === 'percentage'
      ? `${discountValue}% OFF`
      : `₹${discountValue} OFF`
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
      {/* Full-bleed media */}
      {mediaType === 'video' ? (
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

      {/* Subtle full-frame bottom vignette so bottom text is always readable */}
      <div
        style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          background: 'linear-gradient(to bottom, rgba(0,0,0,0) 55%, rgba(0,0,0,0.55) 100%)',
        }}
      />

      {/* ── Top-left: frosted chip + brand logo ── */}
      <div
        style={{
          position: 'absolute', top: pad, left: pad,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          padding: `${chipPy}px ${chipPx}px`,
          background: 'rgba(255,255,255,0.22)',
          backdropFilter: 'blur(14px) saturate(1.6)',
          WebkitBackdropFilter: 'blur(14px) saturate(1.6)',
          borderRadius: chipBr,
          border: '0.5px solid rgba(255,255,255,0.35)',
          boxShadow: '0 2px 10px rgba(0,0,0,0.25)',
        }}
      >
        <img
          src="/images/main-logo-dark.png"
          alt="Flamezo"
          draggable={false}
          style={{ width: logoW, height: 'auto', objectFit: 'contain', display: 'block' }}
        />
      </div>

      {/* ── Top-right: QR + CTA ── */}
      <div
        style={{
          position: 'absolute', top: pad, right: pad,
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
            bottom: Math.round(dims.h * 0.14),
            left: '50%',
            transform: 'translateX(-50%)',
            width: Math.round(dims.w * 0.84),
            background: 'rgba(10,10,12,0.55)',
            backdropFilter: 'blur(24px) saturate(1.6)',
            WebkitBackdropFilter: 'blur(24px) saturate(1.6)',
            borderRadius: Math.round(dims.w * 0.035),
            border: '0.5px solid rgba(255,255,255,0.14)',
            padding: `${Math.round(dims.w * 0.030)}px ${Math.round(dims.w * 0.038)}px`,
            display: 'flex',
            flexDirection: 'column',
            gap: Math.round(dims.w * 0.014),
          }}
        >
          {/* Restaurant name label */}
          {restaurantName && (
            <p style={{
              color: 'rgba(255,255,255,0.42)', fontSize: fs(0.022),
              margin: 0, fontWeight: 500, letterSpacing: '0.05em',
              textTransform: 'uppercase',
            }}>
              {restaurantName}
            </p>
          )}

          {/* Main row: left offer + divider + right code */}
          <div style={{
            display: 'flex', flexDirection: 'row', alignItems: 'center',
            justifyContent: 'space-between', gap: Math.round(dims.w * 0.03),
          }}>
            {/* Left: discount + description + validity */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: Math.round(dims.w * 0.006), flex: 1, minWidth: 0 }}>
              {discountLine && (
                <p style={{
                  color: '#fff', fontSize: fs(0.058), fontWeight: 800,
                  lineHeight: 1, margin: 0, letterSpacing: '-0.01em',
                  whiteSpace: 'nowrap',
                }}>
                  {discountLine}
                </p>
              )}
              <p style={{
                color: 'rgba(255,255,255,0.55)', fontSize: fs(0.026),
                margin: 0, lineHeight: 1.3, fontWeight: 400,
              }}>
                {offerDescription || 'on dine-in'}
              </p>
              {validityLabel && (
                <p style={{
                  color: 'rgba(183,65,14,0.9)', fontSize: fs(0.022),
                  margin: 0, fontWeight: 500,
                }}>
                  {validityLabel} · T&C apply
                </p>
              )}
            </div>

            {/* Divider */}
            <div style={{ width: 0.5, alignSelf: 'stretch', background: 'rgba(255,255,255,0.15)', flexShrink: 0 }} />

            {/* Right: code chip + CTA */}
            {couponCode && (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: Math.round(dims.w * 0.01) }}>
                <div style={{
                  border: '1px dashed rgba(183,65,14,0.75)',
                  borderRadius: Math.round(dims.w * 0.018),
                  padding: `${Math.round(dims.w * 0.01)}px ${Math.round(dims.w * 0.022)}px`,
                  background: 'rgba(183,65,14,0.18)',
                }}>
                  <span style={{
                    color: '#fff', fontSize: fs(0.036), fontWeight: 800,
                    letterSpacing: '0.06em', fontFamily: 'ui-monospace, monospace',
                    whiteSpace: 'nowrap',
                  }}>
                    {couponCode}
                  </span>
                </div>
                <p style={{
                  color: 'rgba(255,255,255,0.38)', fontSize: fs(0.022),
                  margin: 0, textAlign: 'center', lineHeight: 1.4,
                }}>
                  Show at checkout
                </p>
                <p style={{
                  color: 'rgba(255,255,255,0.28)', fontSize: fs(0.020),
                  margin: 0, textAlign: 'center', lineHeight: 1.4,
                }}>
                  Take a screenshot now
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
