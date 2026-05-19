import path from 'path';
import { defineConfig } from 'vite';
import tailwindcss from "@tailwindcss/vite"
import react from '@vitejs/plugin-react';
import proxyOptions from './proxyOptions';

// https://vitejs.dev/config/
export default defineConfig(({ command, mode }) => {
	const isDev = command === 'serve';

	return {
		plugins: [react(), tailwindcss()],
		// Use /flamezo_backend/ for dev, /assets/flamezo_backend/flamezo_backend/ for build
		base: isDev ? '/flamezo_backend/' : '/assets/flamezo_backend/flamezo_backend/',
		server: {
			port: 8081,
			host: '0.0.0.0',
			proxy: proxyOptions,
			hmr: {
				port: 8081,
			},
		},
		resolve: {
			alias: {
				'@': path.resolve(__dirname, './src')
			}
		},
		esbuild: {
			target: 'esnext',
			legalComments: 'none',
		},
		build: {
			outDir: '../flamezo_backend/public/flamezo_backend',
			emptyOutDir: true,
			target: 'esnext',
			minify: 'esbuild',
			chunkSizeWarningLimit: 10000,
			reportCompressedSize: false,
			rollupOptions: {
				output: {
					manualChunks: {
						'vendor-react': ['react', 'react-dom', 'react-router-dom'],
						'vendor-frappe': ['frappe-react-sdk'],
						'vendor-ui': [
							'@radix-ui/react-accordion',
							'@radix-ui/react-alert-dialog',
							'@radix-ui/react-avatar',
							'@radix-ui/react-checkbox',
							'@radix-ui/react-dialog',
							'@radix-ui/react-dropdown-menu',
							'@radix-ui/react-label',
							'@radix-ui/react-popover',
							'@radix-ui/react-select',
							'@radix-ui/react-separator',
							'@radix-ui/react-slot',
							'@radix-ui/react-switch',
							'@radix-ui/react-tabs',
							'@radix-ui/react-tooltip',
							'lucide-react',
							'cmdk',
							'sonner'
						],
						'vendor-utils': ['date-fns', 'clsx', 'tailwind-merge', 'zod', 'react-hook-form'],
						'vendor-dnd': ['@dnd-kit/core', '@dnd-kit/sortable', '@dnd-kit/utilities'],
						'vendor-charts': ['recharts'],
						'vendor-excel': ['xlsx'],
						'vendor-firebase': ['firebase/app', 'firebase/messaging'],
						'vendor-table': ['@tanstack/react-table'],
						'vendor-country': ['country-state-city'],
						'vendor-misc': ['papaparse', 'class-variance-authority', '@hookform/resolvers', 'react-is']
					}
				}
			}
		},
	};
});
