import { FrappeProvider } from 'frappe-react-sdk'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Suspense, lazy } from 'react'
import { Toaster } from './components/ui/sonner'
import { ThemeProvider, useTheme } from './contexts/ThemeContext'
import { RestaurantProvider } from './contexts/RestaurantContext'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import FeatureProtectedRoute from './components/FeatureProtectedRoute'
import { PageSkeleton } from './components/PageSkeleton'

// Lazy load all page components for code-splitting
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Login = lazy(() => import('./pages/Login'))
const MyAccount = lazy(() => import('./pages/MyAccount'))
const FeatureLocked = lazy(() => import('./pages/FeatureLocked'))
const TieredSetupWizard = lazy(() => import('./pages/TieredSetupWizard'))
const ModuleDetail = lazy(() => import('./pages/ModuleDetail'))
const Orders = lazy(() => import('./pages/Orders'))
const AcceptOrders = lazy(() => import('./pages/AcceptOrders'))
const PastOrders = lazy(() => import('./pages/PastOrders'))
const OrderDetail = lazy(() => import('./pages/OrderDetail'))
const QRCodes = lazy(() => import('./pages/QRCodes'))
const HomeFeaturesManager = lazy(() => import('./pages/HomeFeaturesManager'))
const LegacyContent = lazy(() => import('./pages/LegacyContent'))
const LegacySignatureDish = lazy(() => import('./pages/LegacySignatureDish'))
const Payment = lazy(() => import('./pages/Payment'))
const PaymentSettings = lazy(() => import('./pages/PaymentSettings'))
const OrderSettings = lazy(() => import('./pages/OrderSettings'))
const RecommendationsEngine = lazy(() => import('./pages/RecommendationsEngine'))
const Customers = lazy(() => import('./pages/Customers'))
const Bookings = lazy(() => import('./pages/Bookings'))
const Coupons = lazy(() => import('./pages/Coupons'))
const AdminRestaurantManagement = lazy(() => import('./pages/AdminRestaurantManagement'))
const AdminRestaurantDetailsPage = lazy(() => import('./pages/AdminRestaurantDetails'))
const AIEnhancementPage = lazy(() => import('./pages/AIEnhancementPage'))
const AIGalleryPage = lazy(() => import('./pages/AIGalleryPage'))
const AIMenuThemeBackgroundPage = lazy(() => import('./pages/AIMenuThemeBackgroundPage'))
const AIMenuThemeHistoryPage = lazy(() => import('./pages/AIMenuThemeHistoryPage'))
const AutopaySetupPage = lazy(() => import('./pages/AutopaySetupPage'))
const LoyaltySettings = lazy(() => import('./pages/LoyaltySettings'))
const CustomerInsights = lazy(() => import('./pages/CustomerInsights'))
const PaymentConfiguration = lazy(() => import('./pages/PaymentConfiguration'))
const POSIntegration = lazy(() => import('./pages/POSIntegration'))
const LedgerPage = lazy(() => import('./pages/LedgerPage'))
const WhatsAppOrders = lazy(() => import('./pages/WhatsAppOrders'))
const MarketingOverview = lazy(() => import('./pages/MarketingOverview'))
const MarketingCampaigns = lazy(() => import('./pages/MarketingCampaigns'))
const MarketingAutomation = lazy(() => import('./pages/MarketingAutomation'))
const MarketingSegments = lazy(() => import('./pages/MarketingSegments'))
const MarketingAnalytics = lazy(() => import('./pages/MarketingAnalytics'))
const Events = lazy(() => import('./pages/Events'))
const LogisticsHub = lazy(() => import('./pages/LogisticsHub'))
const GoogleGrowth = lazy(() => import('./pages/GoogleGrowth'))
const GoogleGrowthSync = lazy(() => import('./pages/GoogleGrowthSync'))
const GoogleGrowthReviews = lazy(() => import('./pages/GoogleGrowthReviews'))
const TeamManagement = lazy(() => import('./pages/TeamManagement'))
const MenuManagement = lazy(() => import('./pages/MenuManagement'))


function AppContent() {
	const { theme } = useTheme()
	return (
		<>
			<BrowserRouter basename="/dinematters">
				<Suspense fallback={<Layout><PageSkeleton /></Layout>}>
					<Routes>
						{/* Public routes */}
						<Route path="/login" element={<Login />} />

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

								<Route path="/Home Feature" element={<Navigate to="/home-features" replace />} />
								<Route path="/Home%20Feature" element={<Navigate to="/home-features" replace />} />

								<Route path="/admin/restaurants" element={<AdminRestaurantManagement />} />
								<Route path="/admin/restaurants/:id" element={<AdminRestaurantDetailsPage />} />

								<Route element={<FeatureProtectedRoute feature="ordering" />}>
									<Route path="/orders" element={<Orders />} />
									<Route path="/accept-orders" element={<AcceptOrders />} />
									<Route path="/orders/:orderId" element={<OrderDetail />} />
									<Route path="/past-orders" element={<PastOrders />} />
								</Route>

								<Route element={<FeatureProtectedRoute feature="coupons" />}>
									<Route path="/coupons" element={<Coupons />} />
								</Route>

								<Route element={<FeatureProtectedRoute feature="ordering" />}>
									<Route path="/pos-integration" element={<POSIntegration />} />
									<Route path="/frontend-ordering" element={<OrderSettings />} />
									<Route path="/order-settings" element={<OrderSettings />} />
								</Route>

								<Route element={<FeatureProtectedRoute feature="loyalty" />}>
									<Route path="/loyalty-settings" element={<LoyaltySettings />} />
									<Route path="/loyalty-insights" element={<CustomerInsights />} />
								</Route>

								<Route element={<FeatureProtectedRoute feature="tableBooking" />}>
									<Route path="/bookings" element={<Bookings />} />
								</Route>

								<Route element={<FeatureProtectedRoute feature="events" />}>
									<Route path="/events" element={<Events />} />
								</Route>

								<Route element={<FeatureProtectedRoute feature="ordering" />}>
									<Route path="/customers" element={<Customers />} />
								</Route>

								<Route element={<FeatureProtectedRoute feature="aiRecommendations" />}>
									<Route path="/recommendations-engine" element={<RecommendationsEngine />} />
								</Route>

								<Route element={<FeatureProtectedRoute requireGold />}>
									<Route path="/whatsapp-orders" element={<WhatsAppOrders />} />
								</Route>

								{/* Marketing Studio (DIAMOND only) */}
								<Route element={<FeatureProtectedRoute feature="marketing_studio" />}>
									<Route path="/marketing" element={<MarketingOverview />} />
									<Route path="/marketing/campaigns" element={<MarketingCampaigns />} />
									<Route path="/marketing/campaigns/:id" element={<MarketingCampaigns />} />
									<Route path="/marketing/automation" element={<MarketingAutomation />} />
									<Route path="/marketing/segments" element={<MarketingSegments />} />
									<Route path="/marketing/analytics" element={<MarketingAnalytics />} />
								</Route>
								
								{/* Google Growth (GOLD/DIAMOND) */}
								<Route element={<FeatureProtectedRoute feature="google_growth" />}>
									<Route path="/google-growth" element={<GoogleGrowth />} />
									<Route path="/google-growth/sync" element={<GoogleGrowthSync />} />
									<Route path="/google-growth/reviews" element={<GoogleGrowthReviews />} />
								</Route>

								<Route path="/billing" element={<PaymentSettings />} />
								<Route path="/billing/configure" element={<PaymentConfiguration />} />
								<Route path="/ledger" element={<LedgerPage />} />
								<Route path="/autopay-setup" element={<AutopaySetupPage />} />
								<Route path="/team" element={<TeamManagement />} />

								<Route path="/menu" element={<MenuManagement />} />
								<Route path="/qr-codes" element={<QRCodes />} />

								<Route path="/home-features" element={<HomeFeaturesManager />} />

								<Route path="/ai-enhancements" element={<AIEnhancementPage />} />
								<Route path="/ai-gallery" element={<AIGalleryPage />} />
								<Route path="/ai-menu-theme-background" element={<AIMenuThemeBackgroundPage />} />
								<Route path="/ai-menu-theme-history" element={<AIMenuThemeHistoryPage />} />

								<Route path="/Legacy Content" element={<LegacyContent />} />
								<Route path="/Legacy Signature Dish" element={<LegacySignatureDish />} />
								<Route path="/logistics-hub" element={<LogisticsHub />} />
								<Route path="/restaurant/:restaurantId/payment" element={<Payment />} />
								<Route path="/restaurant/:restaurantId/billing" element={<PaymentSettings />} />
								<Route path="/restaurant/:restaurantId/billing/configure" element={<PaymentConfiguration />} />
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
				<RestaurantProvider>
					<AppContent />
				</RestaurantProvider>
			</ThemeProvider>
		</FrappeProvider>
	)
}

export default App
