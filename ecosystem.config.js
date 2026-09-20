module.exports = {
  apps: [
    {
      name: "daleel-search",
      cwd: "/home/REPLACE_USER/daleel-search",
      script: "/home/REPLACE_USER/daleel-search/.venv/bin/uvicorn",
      args: "app.main:app --host 127.0.0.1 --port 8090",
      interpreter: "none",
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: "700M",
      env: {
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
