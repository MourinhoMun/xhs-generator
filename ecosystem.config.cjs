module.exports = {
  apps: [{
    name: 'xhs-doctor',
    script: 'bash',
    args: '-c "cd /var/www/xhs-doctor && uvicorn app:app --host 127.0.0.1 --port 3007 --workers 2"',
    env: {
      PYTHONPATH: '/var/www/xhs-doctor',
    },
    autorestart: true,
    watch: false,
  }]
};
