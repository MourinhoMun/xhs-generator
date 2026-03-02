import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { generateCopy } from './routes/generate.js';
import { renderCards } from './routes/render.js';
import { generateBackground } from './routes/background.js';
import { upload, uploadBackground } from './routes/upload.js';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

dotenv.config();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();
const PORT = process.env.PORT || 3006;

// 确保目录存在
['outputs', 'uploads'].forEach(dir => {
  const p = path.join(__dirname, dir);
  if (!fs.existsSync(p)) fs.mkdirSync(p, { recursive: true });
});

app.use(cors());
app.use(express.json({ limit: '20mb' }));
app.use('/outputs', express.static(path.join(__dirname, 'outputs')));
app.use('/uploads', express.static(path.join(__dirname, 'uploads')));

app.post('/api/generate', generateCopy);
app.post('/api/render', renderCards);
app.post('/api/bg/generate', generateBackground);
app.post('/api/bg/upload', upload.single('image'), uploadBackground);
app.get('/api/health', (_, res) => res.json({ ok: true }));

app.listen(PORT, () => console.log(`XHS Generator running on :${PORT}`));
