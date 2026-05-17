import path from 'path';
import { defineConfig } from 'vite';
import tailwindcss from "@tailwindcss/vite"
import react from '@vitejs/plugin-react'
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
		build: {
			outDir: '../flamezo_backend/public/flamezo_backend',
			emptyOutDir: true,
			target: 'esnext', // Use ESNext for better tree-shaking support
			minify: 'esbuild',
			chunkSizeWarningLimit: 1000,
			rollupOptions: {
				output: {
					manualChunks: {
						// Split core vendor libraries
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
						'vendor-dnd': ['@dnd-kit/core', '@dnd-kit/sortable', '@dnd-kit/utilities']
					}
				}
			}
		},
	};
});
