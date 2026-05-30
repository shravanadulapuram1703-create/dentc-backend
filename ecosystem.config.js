module.exports = {
  apps: [
    {
      name: "dentc-backend",

      script: "/home/kadaridineshkumar/recon-dental-backend/venv/bin/gunicorn",
      args: "app.main:app -c gunicorn_config.py",

      interpreter: "none",   //  MUST BE THIS

      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,

      env: {
        PYTHONUNBUFFERED: "1",
      },

      error_file: "./logs/pm2-error.log",
      out_file: "./logs/pm2-out.log",
      log_file: "./logs/pm2-combined.log",
    }
  ]
};



/**
 * PM2 Ecosystem Configuration for DentC Backend
 * 
 * Usage:
 *   pm2 start ecosystem.config.js
 *   pm2 stop ecosystem.config.js
 *   pm2 restart ecosystem.config.js
 *   pm2 delete ecosystem.config.js
 *   pm2 logs dentc-backend
 *   pm2 monit
 */
// module.exports = {
//   apps: [
//     {
//       name: "dentc-backend",
//       script:  "/home/kadaridineshkumar/recon-dental-backend/venv/bin/gunicorn",
//       args: "app.main:app -c gunicorn_config.py",
//       instances: 1, // PM2 will manage instances, Gunicorn manages workers
//       exec_mode: "fork", // Use fork mode (not cluster) since Gunicorn handles workers
//       autorestart: true,
//       watch: false, // Set to true for development, false for production
//       max_memory_restart: "1G", // Restart if memory exceeds 1GB
//       env: {
//         NODE_ENV: "production",
//         PYTHONUNBUFFERED: "1",
//       },
//       env_production: {
//         NODE_ENV: "production",
//         PYTHONUNBUFFERED: "1",
//         GUNICORN_WORKERS: "4", // Adjust baseYd on CPU cores
//         GUNICORN_BIND: "0.0.0.0:8000",
//         GUNICORN_LOG_LEVEL: "info",
//       },
//       env_development: {
//         NODE_ENV: "development",
//         PYTHONUNBUFFERED: "1",
//         GUNICORN_WORKERS: "2",
//         GUNICORN_BIND: "127.0.0.1:8000",
//         GUNICORN_LOG_LEVEL: "debug",
//       },
//       error_file: "./logs/pm2-error.log",
//       out_file: "./logs/pm2-out.log",
//       log_file: "./logs/pm2-combined.log",
//       time: true, // Prepend timestamp to logs
//       merge_logs: true,
//       log_date_format: "YYYY-MM-DD HH:mm:ss Z",
//       kill_timeout: 5000, // Time to wait before force killing
//       wait_ready: false, // Wait for app to be ready before considering it online
//       listen_timeout: 10000, // Time to wait for app to start
//     },
//     // Optional: Redis worker (if using Celery for background jobs)
//     // {
//     //   name: "dentc-backend-celery",
//     //   script: "celery",
//     //   args: "-A app.core.celery_app worker --loglevel=info --concurrency=4",
//     //   instances: 1,
//     //   exec_mode: "fork",
//     //   autorestart: true,
//     //   watch: false,
//     //   max_memory_restart: "500M",
//     //   env: {
//     //     NODE_ENV: "production",
//     //     PYTHONUNBUFFERED: "1",
//     //   },
//     // },
//   ],
// };
