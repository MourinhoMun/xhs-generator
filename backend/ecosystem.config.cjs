module.exports = {
  apps: [{
    name: 'xhs-generator',
    script: '/var/www/xhs-generator/backend/server.js',
    cwd: '/var/www/xhs-generator/backend',
    env: {
      NODE_ENV: 'production',
      PORT: '3006',
      YUNWU_API_KEY: 'sk-GOthcTYIVEdXznmrcdxs2CDV51lb9qalw5vMbSBxeFaQFG4f',
      YUNWU_BASE_URL: 'https://yunwu.ai',
    }
  }]
};
