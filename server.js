#!/usr/bin/env node
/**
 * МинералКарта — Launcher
 * Starts the Python Flask server
 * Usage: node server.js
 */

const { spawn } = require('child_process');
const path = require('path');

const serverPath = path.join(__dirname, 'server.py');

console.log('🚀 Запуск МинералКарта...');

const proc = spawn('python3', [serverPath], {
  stdio: 'inherit',
  cwd: __dirname
});

proc.on('error', (err) => {
  if (err.code === 'ENOENT') {
    console.error('❌ Python3 не найден. Запустите напрямую: python3 server.py');
  } else {
    console.error('❌ Ошибка запуска:', err.message);
  }
  process.exit(1);
});

proc.on('exit', (code) => {
  if (code !== 0) process.exit(code);
});

process.on('SIGINT', () => {
  proc.kill('SIGINT');
  process.exit(0);
});
