module.exports = {
  apps: [
    {
      name: "dentc-backend-dev",
      cwd: "/home/ec2-user/dentc-backend",
      script: "/home/ec2-user/dentc-backend/dentc-env/bin/uvicorn",
      args: "app.main:app --host 0.0.0.0 --port 8000 --reload",
      interpreter: "none",
      env: {
        DEV_MODE: "true"
      },
      autorestart: true,
      watch: false
    }
  ]
};
