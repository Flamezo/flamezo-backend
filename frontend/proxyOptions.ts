// @ts-ignore
const common_site_config = require('../../../sites/common_site_config.json');
const { webserver_port } = common_site_config;

export default {
	'^/api/(delivery|ai)': {
		target: `http://127.0.0.1:8001`,
		changeOrigin: true,
	},
	'^/(app|api|assets|files|private)': {
		target: `http://127.0.0.1:${webserver_port}`,
		ws: true,
		router: function(req: any) {
			const site_name = req.headers.host?.split(':')[0] || 'localhost';
			return `http://${site_name}:${webserver_port}`;
		}
	}
};












