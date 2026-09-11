import { useLayoutEffect, useState } from 'react'

function scrollParent(el: HTMLElement): HTMLElement | null {
  for (let p = el.parentElement; p; p = p.parentElement) {
    const oy = getComputedStyle(p).overflowY
    if (oy === 'auto' || oy === 'scroll') return p
  }
  return null
}

/**
 * Makes a page a fixed workspace: its root fills exactly from where it starts
 * to the bottom of the visible area, and BOTH the layout's scroll area and the
 * browser page are locked while it's open — so only the page's inner panels
 * scroll, whatever top bar / breadcrumb / padding the layout adds.
 * Re-measures on resize and once more after the first paint settles.
 *
 * Returns a callback ref (not a ref object) so it measures when the element
 * actually mounts — pages that first render a loading or "access" state
 * would otherwise never be measured.
 */
export function useFillViewportHeight(bottomGap = 16) {
  const [el, setEl] = useState<HTMLElement | null>(null)
  const [height, setHeight] = useState<number>()
  useLayoutEffect(() => {
    if (!el) return
    const sc = scrollParent(el)
    const html = document.documentElement
    const body = document.body
    const saved = [sc?.style.overflowY ?? '', html.style.overflow, body.style.overflow]
    if (sc) {
      sc.style.overflowY = 'hidden'
      sc.scrollTop = 0
    }
    html.style.overflow = 'hidden'
    body.style.overflow = 'hidden'
    window.scrollTo(0, 0)

    // The layout's own bottom padding (e.g. <main className="md:p-6">) sits
    // under the page; leave room for it or the page ends up a few px taller
    // than the window and scrolls both panels together.
    const padBottom = sc ? parseFloat(getComputedStyle(sc).paddingBottom) || 0 : 0

    const update = () => {
      // The lower of the window's bottom and the scroll area's bottom.
      const bottom = Math.min(window.innerHeight, sc ? sc.getBoundingClientRect().bottom : window.innerHeight)
      setHeight(Math.max(420, Math.floor(bottom - el.getBoundingClientRect().top - bottomGap - padBottom)))
    }
    // Safety net: if the page is still taller than the window, shrink by the
    // exact difference — nothing is left for the page to scroll.
    const correct = () => {
      const extra = Math.ceil(document.documentElement.scrollHeight - window.innerHeight)
      if (extra > 0) setHeight((h) => (h ? Math.max(420, h - extra) : h))
    }
    update()
    const raf = requestAnimationFrame(() => {
      update()
      requestAnimationFrame(correct)
    })
    const late = window.setTimeout(() => {
      update()
      requestAnimationFrame(correct)
    }, 300)
    window.addEventListener('resize', update)
    return () => {
      cancelAnimationFrame(raf)
      window.clearTimeout(late)
      window.removeEventListener('resize', update)
      if (sc) sc.style.overflowY = saved[0]
      html.style.overflow = saved[1]
      body.style.overflow = saved[2]
    }
  }, [el, bottomGap])
  return [setEl, height] as const
}
