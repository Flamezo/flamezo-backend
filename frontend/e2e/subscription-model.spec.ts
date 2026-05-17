import { test, expect } from '@playwright/test'

// Test data
const LITE_RESTAURANT = {
  name: 'Test Lite Restaurant',
  restaurant_id: 'test-lite-123',
  plan_type: 'LITE'
}

const PRO_RESTAURANT = {
  name: 'Test Pro Restaurant', 
  restaurant_id: 'test-pro-456',
  plan_type: 'PRO'
}

test.describe('Flamezo Subscription Model - E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Login as admin
    await page.goto('/login')
    await page.fill('input[type="email"]', 'admin@example.com')
    await page.fill('input[type="password"]', 'admin123')
    await page.click('button[type="submit"]')
    await page.waitForURL('/dashboard')
  })

  test.describe('Lite Restaurant Experience', () => {
    test('Lite restaurant sees simplified setup wizard', async ({ page }) => {
      // Create or select Lite restaurant
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', LITE_RESTAURANT.restaurant_id)
      
      // Navigate to setup wizard - should redirect to lite setup
      await page.goto('/setup')
      await page.waitForURL('/lite-setup**')
      
      // Verify Lite branding and simplified steps
      await expect(page.locator('h1')).toContainText('Lite Restaurant Setup')
      await expect(page.locator('text=Lite Plan Features')).toBeVisible()
      await expect(page.locator('text=Digital QR menu • Basic website')).toBeVisible()
      
      // Verify only Lite-safe steps are shown
      const steps = await page.locator('[data-testid="setup-step"]').count()
      expect(steps).toBeLessThanOrEqual(5) // restaurant, config, categories, products, home_features
      
      // Verify step titles are Lite-appropriate
      await expect(page.locator('text=Staff Members')).not.toBeVisible()
      await expect(page.locator('text=Create Offers')).not.toBeVisible()
      await expect(page.locator('text=Add Games')).not.toBeVisible()
    })

    test('Lite restaurant sees filtered modules page', async ({ page }) => {
      // Select Lite restaurant
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', LITE_RESTAURANT.restaurant_id)
      
      // Navigate to modules
      await page.goto('/modules')
      
      // Verify Lite branding
      await expect(page.locator('text=Lite Plan - Basic modules only')).toBeVisible()
      await expect(page.locator('[data-testid="lite-badge"]')).toBeVisible()
      
      // Verify only Lite-safe modules are shown
      await expect(page.locator('text=Restaurant')).toBeVisible()
      await expect(page.locator('text=Menu Category')).toBeVisible()
      await expect(page.locator('text=Menu Product')).toBeVisible()
      await expect(page.locator('text=QR Code')).toBeVisible()
      
      // Verify Pro modules are hidden
      await expect(page.locator('text=Order')).not.toBeVisible()
      await expect(page.locator('text=Analytics')).not.toBeVisible()
      await expect(page.locator('text=Loyalty')).not.toBeVisible()
      await expect(page.locator('text=Games')).not.toBeVisible()
    })

    test('Lite restaurant media upload restrictions', async ({ page }) => {
      // Select Lite restaurant and navigate to product
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', LITE_RESTAURANT.restaurant_id)
      await page.goto('/products')
      await page.click('[data-testid="product-item"]:first-child')
      
      // Verify media upload shows Lite restrictions
      await page.click('[data-testid="media-tab"]')
      await expect(page.locator('[data-testid="lite-media-upload"]')).toBeVisible()
      await expect(page.locator('text=Lite Plan Usage')).toBeVisible()
      await expect(page.locator('text=Images only')).toBeVisible()
      
      // Verify video upload is blocked
      const fileInput = page.locator('input[type="file"]')
      await fileInput.setInputFiles({
        name: 'test-video.mp4',
        mimeType: 'video/mp4',
        buffer: Buffer.from('fake video content')
      })
      
      // Should show upgrade prompt for video
      await expect(page.locator('text=Video uploads require Pro plan')).toBeVisible()
      await expect(page.locator('button:has-text("Upgrade")')).toBeVisible()
      
      // Verify image limit enforcement
      // Mock having 199 images (near limit)
      await page.evaluate(() => {
        window.__mockImageCount = 199
      })
      
      await fileInput.setInputFiles({
        name: 'test-image.jpg',
        mimeType: 'image/jpeg',
        buffer: Buffer.from('fake image content')
      })
      
      await expect(page.locator('text=Image limit exceeded')).toBeVisible()
      await expect(page.locator('text=Upgrade to Pro for unlimited images')).toBeVisible()
    })

    test('Lite restaurant sidebar shows locked features', async ({ page }) => {
      // Select Lite restaurant
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', LITE_RESTAURANT.restaurant_id)
      
      // Verify locked sidebar items
      const lockedItems = [
        'Manage Orders',
        'Analytics', 
        'Loyalty & Coupons',
        'Games',
        'Table Bookings'
      ]
      
      for (const item of lockedItems) {
        const sidebarItem = page.locator(`[data-testid="sidebar-${item.toLowerCase().replace(/\s+/g, '-')}"]`)
        await expect(sidebarItem).toBeVisible()
        await expect(sidebarItem.locator('[data-testid="lock-icon"]')).toBeVisible()
        
        // Click should show upgrade prompt
        await sidebarItem.click()
        await expect(page.locator('text=This feature requires a Pro subscription')).toBeVisible()
        await page.keyboard.press('Escape') // Close toast
      }
    })
  })

  test.describe('Pro Restaurant Experience', () => {
    test('Pro restaurant sees full setup wizard', async ({ page }) => {
      // Select Pro restaurant
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', PRO_RESTAURANT.restaurant_id)
      
      // Navigate to setup wizard - should stay on regular setup
      await page.goto('/setup')
      await page.waitForURL('/setup**')
      await expect(page.locator('h1')).toContainText('Restaurant Setup Wizard')
      
      // Verify all steps are available
      await expect(page.locator('text=Staff Members')).toBeVisible()
      await expect(page.locator('text=Create Offers')).toBeVisible()
      await expect(page.locator('text=Add Games')).toBeVisible()
      await expect(page.locator('text=Table Booking Setup')).toBeVisible()
      
      // Should not show Lite branding
      await expect(page.locator('text=Lite Plan Features')).not.toBeVisible()
    })

    test('Pro restaurant sees all modules', async ({ page }) => {
      // Select Pro restaurant
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', PRO_RESTAURANT.restaurant_id)
      
      // Navigate to modules
      await page.goto('/modules')
      
      // Should not show Lite branding
      await expect(page.locator('text=Lite Plan - Basic modules only')).not.toBeVisible()
      
      // Verify all modules are available
      await expect(page.locator('text=Restaurant')).toBeVisible()
      await expect(page.locator('text=Orders')).toBeVisible()
      await expect(page.locator('text=Analytics')).toBeVisible()
      await expect(page.locator('text=Loyalty')).toBeVisible()
      await expect(page.locator('text=Games')).toBeVisible()
    })

    test('Pro restaurant has unrestricted media upload', async ({ page }) => {
      // Select Pro restaurant and navigate to product
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', PRO_RESTAURANT.restaurant_id)
      await page.goto('/products')
      await page.click('[data-testid="product-item"]:first-child')
      
      // Verify regular media upload (no Lite restrictions)
      await page.click('[data-testid="media-tab"]')
      await expect(page.locator('[data-testid="lite-media-upload"]')).not.toBeVisible()
      await expect(page.locator('text=Unlimited storage')).toBeVisible()
      
      // Should be able to upload videos
      const fileInput = page.locator('input[type="file"]')
      await fileInput.setInputFiles({
        name: 'test-video.mp4',
        mimeType: 'video/mp4',
        buffer: Buffer.from('fake video content')
      })
      
      // Should not show upgrade prompt
      await expect(page.locator('text=Video uploads require Pro plan')).not.toBeVisible()
    })
  })

  test.describe('Plan Switching', () => {
    test('Restaurant upgraded from Lite to Pro', async ({ page }) => {
      // Start with Lite restaurant
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', LITE_RESTAURANT.restaurant_id)
      
      // Verify Lite experience
      await page.goto('/modules')
      await expect(page.locator('text=Lite Plan - Basic modules only')).toBeVisible()
      
      // Simulate admin upgrading the restaurant
      await page.goto('/admin/restaurants')
      await page.click(`[data-testid="restaurant-${LITE_RESTAURANT.restaurant_id}"]`)
      await page.selectOption('#plan_type', 'PRO')
      await page.click('button:has-text("Save")')
      await page.waitForSelector('text=Restaurant updated successfully')
      
      // Verify Pro experience after upgrade
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', LITE_RESTAURANT.restaurant_id)
      await page.goto('/modules')
      
      // Should now see Pro experience
      await expect(page.locator('text=Lite Plan - Basic modules only')).not.toBeVisible()
      await expect(page.locator('text=Orders')).toBeVisible()
      await expect(page.locator('text=Analytics')).toBeVisible()
    })

    test('Restaurant downgraded from Pro to Lite', async ({ page }) => {
      // Start with Pro restaurant
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', PRO_RESTAURANT.restaurant_id)
      
      // Verify Pro experience
      await page.goto('/modules')
      await expect(page.locator('text=Orders')).toBeVisible()
      
      // Simulate admin downgrading the restaurant
      await page.goto('/admin/restaurants')
      await page.click(`[data-testid="restaurant-${PRO_RESTAURANT.restaurant_id}"]`)
      await page.selectOption('#plan_type', 'LITE')
      await page.click('button:has-text("Save")')
      await page.waitForSelector('text=Restaurant updated successfully')
      
      // Verify Lite experience after downgrade
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', PRO_RESTAURANT.restaurant_id)
      await page.goto('/modules')
      
      // Should now see Lite experience
      await expect(page.locator('text=Lite Plan - Basic modules only')).toBeVisible()
      await expect(page.locator('text=Orders')).not.toBeVisible()
    })
  })

  test.describe('Permission Enforcement', () => {
    test('Direct URL access blocked for Lite users', async ({ page }) => {
      // Select Lite restaurant
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', LITE_RESTAURANT.restaurant_id)
      
      // Try to access protected routes directly
      const protectedRoutes = [
        '/orders',
        '/analytics',
        '/loyalty',
        '/games',
        '/table-bookings'
      ]
      
      for (const route of protectedRoutes) {
        await page.goto(route)
        
        // Should be redirected or shown error
        await expect(page.locator('text=This feature requires a Pro subscription')).toBeVisible()
        // Or redirected to dashboard
        const currentUrl = page.url()
        expect(currentUrl).toMatch(/(dashboard|setup)/)
      }
    })

    test('API endpoints respect plan restrictions', async ({ page }) => {
      // Select Lite restaurant
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', LITE_RESTAURANT.restaurant_id)
      
      // Monitor network requests
      const responses: any[] = []
      page.on('response', response => {
        if (response.url().includes('/api/method/')) {
          responses.push({
            url: response.url(),
            status: response.status()
          })
        }
      })
      
      // Try to access protected API endpoints
      await page.evaluate(async () => {
        const protectedEndpoints = [
          'flamezo_backend.flamezo.api.orders.create_order',
          'flamezo_backend.flamezo.api.analytics.get_dashboard',
          'flamezo_backend.flamezo.api.loyalty.get_program'
        ]
        
        for (const endpoint of protectedEndpoints) {
          try {
            const response = await fetch(`/api/method/${endpoint}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ restaurant_id: 'test-lite-123' })
            })
            console.log(`${endpoint}: ${response.status}`)
          } catch (error) {
            console.log(`${endpoint}: ${error.message}`)
          }
        }
      })
      
      // Wait for network monitoring
      await page.waitForTimeout(2000)
      
      // Verify protected endpoints return appropriate errors
      const protectedResponses = responses.filter(r => 
        r.url.includes('orders') || 
        r.url.includes('analytics') || 
        r.url.includes('loyalty')
      )
      
      expect(protectedResponses.length).toBeGreaterThan(0)
      protectedResponses.forEach(response => {
        expect([401, 403, 404]).toContain(response.status)
      })
    })
  })

  test.describe('Upgrade Flow', () => {
    test('Lite users can access upgrade prompts', async ({ page }) => {
      // Select Lite restaurant
      await page.goto('/dashboard')
      await page.selectOption('#restaurant-selector', LITE_RESTAURANT.restaurant_id)
      
      // Navigate to locked feature
      await page.goto('/modules')
      const lockedModule = page.locator('[data-testid="sidebar-orders"]')
      await lockedModule.click()
      
      // Should show upgrade prompt
      await expect(page.locator('text=This feature requires a Pro subscription')).toBeVisible()
      await expect(page.locator('button:has-text("Upgrade Now")')).toBeVisible()
      
      // Click upgrade button
      await page.click('button:has-text("Upgrade Now")')
      
      // Should navigate to upgrade page
      await page.waitForURL('/upgrade')
      await expect(page.locator('h1')).toContainText('Upgrade to Pro')
      await expect(page.locator('text=Unlimited everything')).toBeVisible()
    })

    test('Upgrade page shows proper comparison', async ({ page }) => {
      // Navigate to upgrade page
      await page.goto('/upgrade')
      
      // Verify comparison table
      await expect(page.locator('[data-testid="comparison-table"]')).toBeVisible()
      
      // Verify Lite limitations are highlighted
      await expect(page.locator('text=200 images')).toBeVisible()
      await expect(page.locator('text=No video uploads')).toBeVisible()
      await expect(page.locator('text=No ordering features')).toBeVisible()
      
      // Verify Pro benefits are highlighted
      await expect(page.locator('text=Unlimited images')).toBeVisible()
      await expect(page.locator('text=Video uploads')).toBeVisible()
      await expect(page.locator('text=Complete ordering system')).toBeVisible()
    })
  })
})

test.describe('Performance Tests', () => {
  test('Lite setup wizard loads quickly', async ({ page }) => {
    // Select Lite restaurant
    await page.goto('/dashboard')
    await page.selectOption('#restaurant-selector', LITE_RESTAURANT.restaurant_id)
    
    // Measure load time
    const startTime = Date.now()
    await page.goto('/lite-setup')
    await page.waitForSelector('[data-testid="setup-step"]')
    const loadTime = Date.now() - startTime
    
    // Should load in under 2 seconds
    expect(loadTime).toBeLessThan(2000)
  })

  test('Modules page filtering is performant', async ({ page }) => {
    // Select Lite restaurant
    await page.goto('/dashboard')
    await page.selectOption('#restaurant-selector', LITE_RESTAURANT.restaurant_id)
    
    // Measure filtering time
    const startTime = Date.now()
    await page.goto('/modules')
    await page.waitForSelector('[data-testid="module-card"]')
    const loadTime = Date.now() - startTime
    
    // Should load in under 1.5 seconds
    expect(loadTime).toBeLessThan(1500)
  })
})
