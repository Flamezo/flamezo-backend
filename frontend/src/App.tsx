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
const GrowthDashboard = lazy(() => import('./pages/GrowthDashboard'))
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
const AdminMerchantManagement = lazy(() => import('./pages/AdminMerchantManagement'))
const AdminMerchantDetailsPage = lazy(() => import('./pages/AdminMerchantDetails'))
const AdminCustomerManagement = lazy(() => import('./pages/AdminCustomerManagement'))
const AdminCustomerDetail = lazy(() => import('./pages/AdminCustomerDetail'))
const AIEnhancementPage = lazy(() => import('./pages/AIEnhancementPage'))
const AIGalleryPage = lazy(() => import('./pages/AIGalleryPage'))
const AIMenuThemeBackgroundPage = lazy(() => import('./pages/AIMenuThemeBackgroundPage'))
const AIMenuThemeHistoryPage = lazy(() => import('./pages/AIMenuThemeHistoryPage'))
const AutopaySetupPage = lazy(() => import('./pages/AutopaySetupPage'))
const RouteKycPage = lazy(() => import('./pages/RouteKycPage'))
const LoyaltySettings = lazy(() => import('./pages/LoyaltySettings'))
const LoyaltyAnalytics = lazy(() => import('./pages/LoyaltyAnalytics'))

const LedgerPage = lazy(() => import('./pages/LedgerPage'))
const MarketingOverview = lazy(() => import('./pages/MarketingOverview'))
const MarketingCampaigns = lazy(() => import('./pages/MarketingCampaigns'))
const MarketingAutomation = lazy(() => import('./pages/MarketingAutomation'))
const MarketingSegments = lazy(() => import('./pages/MarketingSegments'))
const MarketingAnalytics = lazy(() => import('./pages/MarketingAnalytics'))
const Events = lazy(() => import('./pages/Events'))

const GoogleGrowth = lazy(() => import('./pages/GoogleGrowth'))
const GoogleGrowthSync = lazy(() => import('./pages/GoogleGrowthSync'))
const GoogleGrowthReviews = lazy(() => import('./pages/GoogleGrowthReviews'))
const TeamManagement = lazy(() => import('./pages/TeamManagement'))
const BoostOverview = lazy(() => import('./pages/BoostOverview'))
const BoostNewCampaign = lazy(() => import('./pages/BoostNewCampaign'))
const BoostCampaignDetail = lazy(() => import('./pages/BoostCampaignDetail'))
const BoostRedeem = lazy(() => import('./pages/BoostRedeem'))
const MenuManagement = lazy(() => import('./pages/MenuManagement'))
const MenuCosting = lazy(() => import('./pages/MenuCosting'))
const AddonGroupManagement = lazy(() => import('./pages/AddonGroupManagement'))

const GalleryManagement = lazy(() => import('./pages/GalleryManagement'))
const UGCConfig = lazy(() => import('./pages/UGCConfig'))
const UGCApprovals = lazy(() => import('./pages/UGCApprovals'))
const UGCAnalytics = lazy(() => import('./pages/UGCAnalytics'))

const ChillsUpload = lazy(() => import('./pages/ChillsUpload'))
const ChillsVideos = lazy(() => import('./pages/ChillsVideos'))
const ChillsAnalytics = lazy(() => import('./pages/ChillsAnalytics'))

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
								<Route path="/growth-dashboard" element={<GrowthDashboard />} />
								<Route path="/account" element={<MyAccount />} />
								<Route path="/setup" element={<TieredSetupWizard />} />
								<Route path="/setup/:stepId" element={<TieredSetupWizard />} />

								<Route path="/admin/merchants" element={<AdminMerchantManagement />} />
								<Route path="/admin/merchants/:id" element={<AdminMerchantDetailsPage />} />
								<Route path="/admin/customers" element={<AdminCustomerManagement />} />
								<Route path="/admin/customers/:id" element={<AdminCustomerDetail />} />


								<Route element={<FeatureProtectedRoute feature="coupons" />}>
									<Route path="/coupons" element={<Coupons />} />
								</Route>



								<Route element={<FeatureProtectedRoute feature="loyalty" />}>
									<Route path="/loyalty-settings" element={<LoyaltySettings />} />
									<Route path="/loyalty-analytics" element={<LoyaltyAnalytics />} />
								</Route>
								<Route path="/loyalty-insights" element={<Navigate to="/loyalty-analytics" replace />} />

								{/* UGC Cashback — story-for-cashback growth loop */}
								<Route path="/ugc-cashback/config" element={<UGCConfig />} />
								<Route path="/ugc-cashback/approvals" element={<UGCApprovals />} />
								<Route path="/ugc-cashback/analytics" element={<UGCAnalytics />} />

								{/* Chills — short-video upload and analytics */}
								<Route path="/chills/upload" element={<ChillsUpload />} />
								<Route path="/chills/videos" element={<ChillsVideos />} />
								<Route path="/chills/analytics" element={<ChillsAnalytics />} />

								<Route element={<FeatureProtectedRoute feature="tableBooking" />}>
									<Route path="/bookings" element={<Bookings />} />
								</Route>

								<Route element={<FeatureProtectedRoute feature="events" />}>
									<Route path="/events" element={<Events />} />
								</Route>

								<Route element={<FeatureProtectedRoute feature="customer" />}>
									<Route path="/customers" element={<Customers />} />
								</Route>

								<Route element={<FeatureProtectedRoute feature="aiRecommendations" />}>
									<Route path="/recommendations-engine" element={<RecommendationsEngine />} />
								</Route>


								{/* Marketing Studio (GOLD only) */}
								<Route element={<FeatureProtectedRoute feature="marketing_studio" />}>
									<Route path="/marketing" element={<MarketingOverview />} />
									<Route path="/marketing/campaigns" element={<MarketingCampaigns />} />
									<Route path="/marketing/campaigns/:id" element={<MarketingCampaigns />} />
									<Route path="/marketing/automation" element={<MarketingAutomation />} />
									<Route path="/marketing/segments" element={<MarketingSegments />} />
									<Route path="/marketing/analytics" element={<MarketingAnalytics />} />
								</Route>
								
								{/* Google Growth (GOLD only) */}
								<Route element={<FeatureProtectedRoute feature="google_growth" />}>
									<Route path="/google-growth" element={<GoogleGrowth />} />
									<Route path="/google-growth/sync" element={<GoogleGrowthSync />} />
									<Route path="/google-growth/reviews" element={<GoogleGrowthReviews />} />
								</Route>

								{/* Boost — Ad campaign management */}
								<Route path="/boost" element={<BoostOverview />} />
								<Route path="/boost/new" element={<BoostNewCampaign />} />
								<Route path="/boost/campaign" element={<BoostCampaignDetail />} />
								<Route path="/boost/redeem" element={<BoostRedeem />} />

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

								<Route path="/ai-enhancements" element={<AIEnhancementPage />} />
								<Route path="/ai-gallery" element={<AIGalleryPage />} />
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
