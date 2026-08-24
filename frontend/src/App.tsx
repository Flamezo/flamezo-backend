import { FrappeProvider } from 'frappe-react-sdk'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import { Toaster } from './components/ui/sonner'
import { ThemeProvider, useTheme } from './contexts/ThemeContext'
import { OutletProvider } from './contexts/OutletContext'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import FeatureProtectedRoute from './components/FeatureProtectedRoute'
import SessionGuard from './components/SessionGuard'
import { PageSkeleton } from './components/PageSkeleton'

// Lazy load all page components for code-splitting
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Login = lazy(() => import('./pages/Login'))

const ForgotPassword = lazy(() => import('./pages/ForgotPassword'))
const ResetPassword = lazy(() => import('./pages/ResetPassword'))


const MyAccount = lazy(() => import('./pages/MyAccount'))
const FeatureLocked = lazy(() => import('./pages/FeatureLocked'))
const TieredSetupWizard = lazy(() => import('./pages/TieredSetupWizard'))
const ModuleDetail = lazy(() => import('./pages/ModuleDetail'))
const QRCodes = lazy(() => import('./pages/QRCodes'))
const LegacyContent = lazy(() => import('./pages/LegacyContent'))
const Payment = lazy(() => import('./pages/Payment'))
const PaymentSettings = lazy(() => import('./pages/PaymentSettings'))

const RecommendationsEngine = lazy(() => import('./pages/RecommendationsEngine'))
const Customers = lazy(() => import('./pages/Customers'))
const Bookings = lazy(() => import('./pages/Bookings'))
const Coupons = lazy(() => import('./pages/Coupons'))
const HotDrops = lazy(() => import('./pages/HotDrops'))
const AdminMerchantManagement = lazy(() => import('./pages/AdminMerchantManagement'))
const AdminMerchantDetailsPage = lazy(() => import('./pages/AdminMerchantDetails'))
const AdminCustomerManagement = lazy(() => import('./pages/AdminCustomerManagement'))
const AdminCustomerDetail = lazy(() => import('./pages/AdminCustomerDetail'))
const AdminEventDetail = lazy(() => import('./pages/AdminEventDetail'))
const MyOutletEvent = lazy(() => import('./pages/MyOutletEvent'))
const MyOutletEventDetail = lazy(() => import('./pages/MyOutletEventDetail'))
// AI Enhancements / AI Gallery — hidden for now (not ready to offer yet).
// Commented out, not deleted: uncomment these two lines + the matching
// <Route> entries below to bring both pages straight back.
// const AIEnhancementPage = lazy(() => import('./pages/AIEnhancementPage'))
// const AIGalleryPage = lazy(() => import('./pages/AIGalleryPage'))
const AIMenuThemeBackgroundPage = lazy(() => import('./pages/AIMenuThemeBackgroundPage'))
const AIMenuThemeHistoryPage = lazy(() => import('./pages/AIMenuThemeHistoryPage'))
const AutopaySetupPage = lazy(() => import('./pages/AutopaySetupPage'))
const RouteKycPage = lazy(() => import('./pages/RouteKycPage'))
const LoyaltyHub = lazy(() => import('./pages/hubs/LoyaltyHub'))

const LedgerPage = lazy(() => import('./pages/LedgerPage'))
const MarketingHub = lazy(() => import('./pages/hubs/MarketingHub'))
// Standalone campaign-detail view (a specific campaign's own page, not one
// of MarketingHub's tabs) still uses the plain page component directly.
const MarketingCampaigns = lazy(() => import('./pages/MarketingCampaigns'))
const Events = lazy(() => import('./pages/Events'))

const GoogleGrowthHub = lazy(() => import('./pages/hubs/GoogleGrowthHub'))
const GoogleGrowthSync = lazy(() => import('./pages/GoogleGrowthSync'))
const TeamManagement = lazy(() => import('./pages/TeamManagement'))
const BoostHub = lazy(() => import('./pages/hubs/BoostHub'))
const BoostCampaignDetail = lazy(() => import('./pages/BoostCampaignDetail'))
const MenuManagement = lazy(() => import('./pages/MenuManagement'))
const MenuCosting = lazy(() => import('./pages/MenuCosting'))
const AddonGroupManagement = lazy(() => import('./pages/AddonGroupManagement'))

const GalleryManagement = lazy(() => import('./pages/GalleryManagement'))
const UGCCashbackHub = lazy(() => import('./pages/hubs/UGCCashbackHub'))

const ClubTalksHub = lazy(() => import('./pages/hubs/ClubTalksHub'))
const ChillsHub = lazy(() => import('./pages/hubs/ChillsHub'))

// Non-dining industry pages
const CatalogueManagementPage = lazy(() => import('./pages/CatalogueManagement'))
const AppointmentsPage = lazy(() => import('./pages/AppointmentsPage'))
const CourtsPage = lazy(() => import('./pages/CourtsPage'))


function AppContent() {
	const { theme } = useTheme()
	return (
		<>
			<BrowserRouter basename="/flamezo_backend">
				<Suspense fallback={<Layout><PageSkeleton /></Layout>}>
					<Routes>
						{/* Public routes */}
						<Route path="/login" element={<Login />} />
						<Route path="/forgot-password" element={<ForgotPassword />} />
						<Route path="/reset-password" element={<ResetPassword />} />




						{/* Protected routes */}
						<Route element={<ProtectedRoute />}>
							<Route path="/" element={<Navigate to="/dashboard" replace />} />
							<Route path="/feature-locked" element={<FeatureLocked />} />
							
							{/* Routes using the shared Layout */}
							<Route element={<Layout />}>
								<Route path="/dashboard" element={<Dashboard />} />
									<Route path="/account" element={<MyAccount />} />
								<Route path="/setup" element={<TieredSetupWizard />} />
								<Route path="/setup/:stepId" element={<TieredSetupWizard />} />

								<Route path="/admin/merchants" element={<AdminMerchantManagement />} />
								<Route path="/admin/merchants/:id" element={<AdminMerchantDetailsPage />} />
								<Route path="/admin/customers" element={<AdminCustomerManagement />} />
								<Route path="/admin/customers/:id" element={<AdminCustomerDetail />} />
								<Route path="/admin/events" element={<Events />} />
								<Route path="/admin/events/:id" element={<AdminEventDetail />} />


								<Route element={<FeatureProtectedRoute feature="coupons" />}>
									<Route path="/coupons" element={<Coupons />} />
									<Route path="/hot-drops" element={<HotDrops />} />
								</Route>



								<Route element={<FeatureProtectedRoute feature="loyalty" />}>
									<Route path="/loyalty-settings" element={<LoyaltyHub />} />
									<Route path="/loyalty-analytics" element={<LoyaltyHub />} />
								</Route>
								<Route path="/loyalty-insights" element={<Navigate to="/loyalty-analytics" replace />} />

								{/* UGC Cashback — story-for-cashback growth loop */}
								<Route path="/ugc-cashback/config" element={<UGCCashbackHub />} />
								<Route path="/ugc-cashback/approvals" element={<UGCCashbackHub />} />
								<Route path="/ugc-cashback/analytics" element={<UGCCashbackHub />} />

								{/* Club Talks — merchant broadcast feed (Chills-style: posts / upload / analytics) */}
								<Route path="/club-talks" element={<Navigate to="/club-talks/posts" replace />} />
								<Route path="/club-talks/posts" element={<ClubTalksHub />} />
								<Route path="/club-talks/upload" element={<ClubTalksHub />} />
								<Route path="/club-talks/analytics" element={<ClubTalksHub />} />

								{/* Chills — short-video upload and analytics */}
								<Route path="/chills/upload" element={<ChillsHub />} />
								<Route path="/chills/videos" element={<ChillsHub />} />
								<Route path="/chills/analytics" element={<ChillsHub />} />

								<Route element={<FeatureProtectedRoute feature="tableBooking" />}>
									<Route path="/bookings" element={<Bookings />} />
								</Route>

								{/* Events moved to /admin/events (admin-only, cross-merchant). */}
								<Route path="/events" element={<Navigate to="/admin/events" replace />} />
								{/* Outlet's own live-event tab (appears while an event is on). */}
								<Route path="/my-event" element={<MyOutletEvent />} />
								{/* View-only event detail (event info + joined customers). */}
								<Route path="/my-event/:id" element={<MyOutletEventDetail />} />

								<Route element={<FeatureProtectedRoute feature="customer" />}>
									<Route path="/customers" element={<Customers />} />
								</Route>

								<Route element={<FeatureProtectedRoute feature="aiRecommendations" />}>
									<Route path="/recommendations-engine" element={<RecommendationsEngine />} />
								</Route>


								{/* Marketing Studio (GOLD only) */}
								<Route element={<FeatureProtectedRoute feature="marketing_studio" />}>
									<Route path="/marketing" element={<MarketingHub />} />
									<Route path="/marketing/campaigns" element={<MarketingHub />} />
									{/* Single-campaign detail — not one of the hub's tabs */}
									<Route path="/marketing/campaigns/:id" element={<MarketingCampaigns />} />
									<Route path="/marketing/automation" element={<MarketingHub />} />
									<Route path="/marketing/segments" element={<MarketingHub />} />
									<Route path="/marketing/analytics" element={<MarketingHub />} />
								</Route>

								{/* Google Growth (GOLD only) */}
								<Route element={<FeatureProtectedRoute feature="google_growth" />}>
									<Route path="/google-growth" element={<GoogleGrowthHub />} />
									<Route path="/google-growth/sync" element={<GoogleGrowthSync />} />
									<Route path="/google-growth/reviews" element={<GoogleGrowthHub />} />
								</Route>

								{/* Boost — Ad campaign management */}
								<Route path="/boost" element={<BoostHub />} />
								<Route path="/boost/new" element={<BoostHub />} />
								<Route path="/boost/campaign" element={<BoostCampaignDetail />} />
								<Route path="/boost/redeem" element={<BoostHub />} />

								<Route path="/billing" element={<PaymentSettings />} />
								<Route path="/ledger" element={<LedgerPage />} />
								<Route path="/autopay-setup" element={<AutopaySetupPage />} />
								<Route path="/route-kyc" element={<RouteKycPage />} />
								<Route path="/team" element={<TeamManagement />} />

								<Route path="/menu" element={<MenuManagement />} />
								<Route path="/menu-costing" element={<MenuCosting />} />
								<Route path="/addon-groups" element={<AddonGroupManagement />} />

								{/* Non-dining industry pages */}
								<Route path="/catalogue" element={<CatalogueManagementPage />} />
								<Route path="/appointments" element={<AppointmentsPage />} />
								<Route path="/courts" element={<CourtsPage />} />

								<Route path="/qr-codes" element={<QRCodes />} />
								<Route path="/gallery-management" element={<GalleryManagement />} />

								{/* AI Enhancements / AI Gallery — hidden for now, see commented lazy imports above */}
								{/* <Route path="/ai-enhancements" element={<AIEnhancementPage />} /> */}
								{/* <Route path="/ai-gallery" element={<AIGalleryPage />} /> */}
								<Route path="/ai-menu-theme-background" element={<AIMenuThemeBackgroundPage />} />
								<Route path="/ai-menu-theme-history" element={<AIMenuThemeHistoryPage />} />

								<Route path="/Legacy Content" element={<LegacyContent />} />
								<Route path="/restaurant/:outletId/payment" element={<Payment />} />
								<Route path="/restaurant/:outletId/billing" element={<PaymentSettings />} />
								<Route path="/restaurant/:outletId/route-kyc" element={<RouteKycPage />} />
								<Route path="/:doctype/:docname" element={<ModuleDetail />} />
							</Route>
						</Route>
					</Routes>
				</Suspense>
			</BrowserRouter>
			<Toaster richColors theme={theme} />
		</>
	)
}

function App() {
	return (
		<FrappeProvider
			swrConfig={{
				errorRetryCount: 2
			}}
			socketPort={import.meta.env.VITE_SOCKET_PORT || undefined}
			siteName={(window as any)?.frappe?.boot?.sitename ?? import.meta.env.VITE_SITE_NAME}>
			<ThemeProvider>
				<OutletProvider>
					<SessionGuard />
					<AppContent />
				</OutletProvider>
			</ThemeProvider>
		</FrappeProvider>
	)
}

export default App
